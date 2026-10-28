from __future__ import annotations

from datetime import datetime, timedelta

from tests.fake_edupage import FakeEdupage, FakeEvent


def _event(event_id: int = 7, extra: dict | None = None, event_type: str = "sprava") -> FakeEvent:
    return FakeEvent(
        event_id=event_id,
        timestamp=datetime(2026, 10, 20, 8, 0, 0),
        text="Mit Anhang",
        event_type=event_type,
        additional_data=extra or {"attachments": [{"name": "plan.pdf", "url": "/files/plan.pdf"}]},
    )


def _seed_attachment(fake_edupage, url: str = "/files/plan.pdf", payload: bytes = b"data") -> None:
    from tests.fake_edupage import FakeSession

    fake_edupage.events = [_event(extra={"attachments": [{"name": "plan.pdf", "url": url}]})]
    original_init = FakeSession.__init__

    def init(self):
        original_init(self)
        self.binary_urls[f"https://login1.edupage.org{url}"] = payload

    FakeSession.__init__ = init
    return original_init


async def _write_key(admin, account):
    response = await admin.post(
        "/api/v1/admin/keys",
        json={"account_id": account["id"], "name": "Schreiber", "can_write": True},
    )
    assert response.status_code == 200
    key = response.json()
    key["headers"] = {"Authorization": f"Bearer {key['key']}"}
    return key


# --------------------------------------------------------------- write gates


async def test_read_only_key_cannot_send(admin, bearer):
    response = await admin.post(
        "/api/v1/messages/send", headers=bearer, json={"recipients": ["1"], "body": "Hallo"}
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_write_key_can_send(admin, account, fake_edupage):
    key = await _write_key(admin, account)
    response = await admin.post(
        "/api/v1/messages/send",
        headers=key["headers"],
        json={"recipients": ["1", "2"], "body": "Hallo Welt"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "id": 4242}

    sent = [post for post in fake_edupage.instances[-1].session.posts if post[0] == "send"]
    assert sent[0][1] == {"recipients": ["1", "2"], "body": "Hallo Welt"}


async def test_send_requires_recipients_and_body(admin, account):
    key = await _write_key(admin, account)
    no_recipients = await admin.post(
        "/api/v1/messages/send", headers=key["headers"], json={"recipients": [], "body": "x"}
    )
    assert no_recipients.status_code == 400

    no_body = await admin.post(
        "/api/v1/messages/send", headers=key["headers"], json={"recipients": ["1"], "body": " "}
    )
    assert no_body.status_code == 400


async def test_reply(admin, account):
    key = await _write_key(admin, account)
    response = await admin.post(
        "/api/v1/messages/7/reply", headers=key["headers"], json={"body": "Danke"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_mark_read(admin, bearer):
    response = await admin.post(
        "/api/v1/messages/read", headers=bearer, json={"event_ids": [1, 2, 3]}
    )
    assert response.status_code == 200
    assert response.json()["marked"] == 3


async def test_homework_done_requires_write(admin, bearer):
    response = await admin.post("/api/v1/homework/5/done", headers=bearer, json={"done": True})
    assert response.status_code == 403


async def test_homework_done_calls_edupage(admin, account, fake_edupage):
    key = await _write_key(admin, account)
    await admin.get("/api/v1/me", headers=key["headers"])
    response = await admin.post("/api/v1/homework/5/done", headers=key["headers"], json={"done": True})
    assert response.status_code == 200
    assert response.json()["done"] is True


async def test_homework_trash_is_local_and_hides_item(admin, account, fake_edupage):
    key = await _write_key(admin, account)
    fake_edupage.events = [_event(event_type="homework")]

    hidden = await admin.post("/api/v1/homework/7/trash", headers=key["headers"], json={"hide": True})
    assert hidden.status_code == 200
    assert hidden.json()["hidden"] is True

    listing = await admin.get("/api/v1/homework", headers=key["headers"])
    assert listing.json()["total"] == 0

    # unhide brings it back
    shown = await admin.post("/api/v1/homework/7/trash", headers=key["headers"], json={"hide": False})
    assert shown.status_code == 200
    assert (await admin.get("/api/v1/homework", headers=key["headers"])).json()["total"] == 1


async def test_homework_trash_never_writes_to_edupage(admin, account, fake_edupage):
    key = await _write_key(admin, account)
    fake_edupage.events = [_event(event_type="homework")]
    await admin.post("/api/v1/homework/7/trash", headers=key["headers"], json={"hide": True})
    # hiding must not be forwarded as "done" upstream
    assert fake_edupage.instances[-1].session.posts == []


# ---------------------------------------------------------------- downloads


async def test_download_with_bearer(admin, bearer, account, fake_edupage):
    fake_edupage.events = [_event()]
    class_ = fake_edupage
    class_.instances  # noqa: B018

    # the fake serves the URL only after login; register it on the session class
    from tests.fake_edupage import FakeSession

    original_init = FakeSession.__init__

    def init(self):
        original_init(self)
        self.binary_urls["https://login1.edupage.org/files/plan.pdf"] = b"%PDF-1.4"

    FakeSession.__init__ = init
    try:
        response = await admin.get("/api/v1/messages/7/attachments/0", headers=bearer)
    finally:
        FakeSession.__init__ = original_init

    assert response.status_code == 200
    assert response.content == b"%PDF-1.4"
    assert response.headers["content-disposition"] == 'attachment; filename="plan.pdf"'


async def test_download_token_flow(admin, bearer, fake_edupage):
    from tests.fake_edupage import FakeSession

    original_init = _seed_attachment(fake_edupage)
    try:
        issued = await admin.post(
            "/api/v1/messages/download-token", headers=bearer, json={"event_id": 7, "idx": 0}
        )
        assert issued.status_code == 200
        token = issued.json()["download_token"]
        assert issued.json()["expires_in"] == 300

        # token alone is not an API credential
        anonymous = await admin.get(f"/api/v1/messages/7/attachments/0?dl={token}")
        assert anonymous.status_code == 401

        ok = await admin.get(f"/api/v1/messages/7/attachments/0?dl={token}", headers=bearer)
        assert ok.status_code == 200
        assert ok.content == b"data"
    finally:
        FakeSession.__init__ = original_init


async def test_download_token_is_bound_to_file(admin, bearer, fake_edupage):
    fake_edupage.events = [_event()]
    issued = await admin.post(
        "/api/v1/messages/download-token", headers=bearer, json={"event_id": 7, "idx": 0}
    )
    token = issued.json()["download_token"]

    wrong_idx = await admin.get(f"/api/v1/messages/7/attachments/1?dl={token}", headers=bearer)
    assert wrong_idx.status_code == 401
    assert wrong_idx.json()["code"] == "TOKEN_INVALID"

    wrong_event = await admin.get(f"/api/v1/messages/8/attachments/0?dl={token}", headers=bearer)
    assert wrong_event.status_code == 401


async def test_download_token_rejects_missing_attachment(admin, bearer, fake_edupage):
    fake_edupage.events = [_event(extra={"attachments": []})]
    response = await admin.post(
        "/api/v1/messages/download-token", headers=bearer, json={"event_id": 7, "idx": 0}
    )
    assert response.status_code == 404


async def test_download_token_expires(admin, bearer, fake_edupage):
    from sqlalchemy import update

    from app.core.time import utcnow
    from app.db import get_session_factory
    from app.models import ResourceCache

    fake_edupage.events = [_event()]
    issued = await admin.post(
        "/api/v1/messages/download-token", headers=bearer, json={"event_id": 7, "idx": 0}
    )
    token = issued.json()["download_token"]

    async with get_session_factory()() as db:
        await db.execute(update(ResourceCache).values(expires_at=utcnow() - timedelta(seconds=1)))
        await db.commit()

    response = await admin.get(f"/api/v1/messages/7/attachments/0?dl={token}", headers=bearer)
    assert response.status_code == 401
    assert response.json()["code"] == "TOKEN_INVALID"


async def test_attachment_rejects_foreign_url(admin, bearer, fake_edupage):
    fake_edupage.events = [_event(extra={"attachments": [{"name": "x", "url": "https://evil.example/x"}]})]
    response = await admin.get("/api/v1/messages/7/attachments/0", headers=bearer)
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION"


async def test_attachment_filename_is_sanitised(admin, bearer, fake_edupage):
    from tests.fake_edupage import FakeSession

    fake_edupage.events = [
        _event(extra={"attachments": [{"name": 'bad"na\r\nme.pdf', "url": "/files/a.pdf"}]})
    ]
    original_init = FakeSession.__init__

    def init(self):
        original_init(self)
        self.binary_urls["https://login1.edupage.org/files/a.pdf"] = b"x"

    FakeSession.__init__ = init
    try:
        response = await admin.get("/api/v1/messages/7/attachments/0", headers=bearer)
    finally:
        FakeSession.__init__ = original_init

    assert response.status_code == 200
    assert "\n" not in response.headers["content-disposition"]
    assert 'filename="badname.pdf"' in response.headers["content-disposition"]


async def test_download_token_validation(admin, bearer):
    bad = await admin.post(
        "/api/v1/messages/download-token", headers=bearer, json={"event_id": "abc", "idx": 0}
    )
    assert bad.status_code == 400
    assert bad.json()["code"] == "VALIDATION"

    negative = await admin.post(
        "/api/v1/messages/download-token", headers=bearer, json={"event_id": 1, "idx": -1}
    )
    assert negative.status_code == 400
