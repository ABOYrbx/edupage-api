"""Regression: schools that send ``udalostid`` as a JSON number.

The library looks the grade details up with a *string* key, so those schools fail
with ``'NoneType' object has no attribute 'get'``. ``_grades_with_id_fix`` rewrites
the ids before the library parses them.
"""

from __future__ import annotations

import json

from app.edupage.wrapper import _grades_with_id_fix


class _Response:
    def __init__(self, body: str) -> None:
        self.content = body.encode()
        self.status_code = 200

    @property
    def text(self) -> str:
        return self.content.decode()


class _Session:
    def __init__(self, body: str) -> None:
        self.body = body
        self.urls: list[str] = []

    def get(self, url: str, *args, **kwargs):
        self.urls.append(url)
        return _Response(self.body)


def _page(payload: dict) -> str:
    return (
        "<script>\r\n\t\t.znamkyStudentViewer("
        + json.dumps(payload)
        + ");\r\n\t\t});\r\n\t\t</script>"
    )


class _ParserThatMimicsTheLibrary:
    """Uses the ids exactly like ``edupage_api.grades`` does."""

    def __init__(self, session: _Session, page_payload: dict) -> None:
        self.session = session
        self.payload = page_payload

    def get_grades(self):
        body = self.session.get("https://x.edupage.org/znamky/").content.decode()
        data = json.loads(body.split(".znamkyStudentViewer(")[1].split(");\r\n\t\t});\r\n\t\t</script>")[0])
        details = data["vsetkyUdalosti"]["edupage"]
        out = []
        for grade in data["vsetkyZnamky"]:
            event_id = grade.get("udalostid")
            if not event_id:
                continue
            # the library's string-keyed lookup
            out.append(details.get(event_id)["p_meno"])
        return out


def _client(body_json_numbers: bool) -> _ParserThatMimicsTheLibrary:
    payload = {
        "vsetkyZnamky": [{"udalostid": 868312 if body_json_numbers else "868312", "data": "1"}],
        "vsetkyUdalosti": {"edupage": {"868312": {"p_meno": "Test"}}},
    }
    session = _Session(_page(payload))
    client = type("C", (), {})()
    client.session = session
    client.get_grades = lambda: _ParserThatMimicsTheLibrary(session, payload).get_grades()
    return client


def test_numeric_ids_are_rewritten():
    client = _client(body_json_numbers=True)
    # without the fix the lookup returns None and indexing raises
    try:
        client.get_grades()
    except (TypeError, AttributeError):
        pass
    else:  # pragma: no cover - guards the premise of this test
        raise AssertionError("fixture no longer reproduces the library bug")

    assert _grades_with_id_fix(client) == ["Test"]


def test_string_ids_are_untouched():
    client = _client(body_json_numbers=False)
    assert _grades_with_id_fix(client) == ["Test"]


def test_other_pages_are_not_rewritten():
    client = _client(body_json_numbers=True)
    session = client.session
    _grades_with_id_fix(client)
    # the patch must be removed again afterwards
    assert session.get.__name__ == "get"
