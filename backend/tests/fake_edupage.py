"""Offline stand-in for the synchronous ``edupage_api.Edupage`` client."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from edupage_api.exceptions import BadCredentialsException


@dataclass
class FakeEvent:
    event_id: int
    timestamp: datetime
    text: str
    author: Any = "Lehrer"
    recipient: Any = "Schüler"
    event_type: Any = "sprava"
    additional_data: dict = field(default_factory=dict)
    is_done: bool = False
    done_at: datetime | None = None
    is_starred: bool = False
    reaction_count: int = 0
    other_id: Any = None
    response_to: int | None = None


@dataclass
class FakeLesson:
    period: int
    subject: str
    teacher: str = "Muster"
    classroom: str = "A1"


@dataclass
class FakeTimetable:
    lessons: list[FakeLesson]


@dataclass
class FakeGrade:
    subject: str
    grade: int
    date: datetime
    teacher: str = "Muster"


@dataclass
class FakeTeacher:
    person_id: int
    name: str


@dataclass
class FakeMenu:
    name: str
    allergens: str = "1, 7"
    weight: str = "350g"
    number: str = "A"
    rating: Any = None


@dataclass
class FakeMeal:
    title: str
    menus: list[FakeMenu]
    meal_type: Any = None
    served_from: datetime | None = None
    served_to: datetime | None = None
    chooseable_menus: list[str] = field(default_factory=lambda: ["A", "B"])
    ordered_meal: str | None = "A"


@dataclass
class FakeMealType:
    name: str


@dataclass
class FakeMeals:
    snack: Any = None
    lunch: Any = None
    afternoon_snack: Any = None


class FakeCookies:
    def __init__(self) -> None:
        self._jar: dict[str, str] = {}

    def get_dict(self, domain: str | None = None) -> dict[str, str]:
        return dict(self._jar)

    def set(self, name: str, value: str, domain: str | None = None) -> None:
        self._jar[name] = value


class FakeResponse:
    def __init__(self, status_code: int = 200, text: str = '{"status": "ok"}',
                 content: bytes = b"file-bytes",
                 headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.text = text
        self.content = content
        self.headers = headers or {"content-type": "application/octet-stream"}


class FakeSession:
    def __init__(self) -> None:
        self.cookies = FakeCookies()
        self.posts: list[tuple[str, Any]] = []
        self.gets: list[str] = []
        self.binary_urls: dict[str, bytes] = {}

    def post(self, url: str, data: Any = None, headers: Any = None, parameters: Any = None) -> FakeResponse:
        self.posts.append((url, parameters if parameters is not None else data))
        return FakeResponse()

    def get(self, url: str, stream: bool = False) -> FakeResponse:
        self.gets.append(url)
        if url in self.binary_urls:
            return FakeResponse(content=self.binary_urls[url])
        if "twofactor" in url:
            return FakeResponse(text="<html></html>", content=b"<html></html>")
        return FakeResponse()


class FakeTwoFactorLogin:
    def __init__(self) -> None:
        self.finished_with: str | None = None

    def finish_with_code(self, code: str) -> None:
        if code != "123456":
            from edupage_api.exceptions import SecondFactorFailedException

            raise SecondFactorFailedException("wrong code")
        self.finished_with = code


class FakeEdupage:
    """Minimal client exercising every code path the gateway uses."""

    instances: list["FakeEdupage"] = []
    valid_credentials = {("schueler", "geheim")}
    require_2fa = False
    events: list[FakeEvent] = []
    grades: list[FakeGrade] = []
    meals: Any = None

    def __init__(self, request_timeout: int = 5) -> None:
        self.data = {"userid": "1", "user_meno": "Schüler", "skola": {"nazov": "Testschule"}}
        self.is_logged_in = False
        self.subdomain = None
        self.username = None
        self.session = FakeSession()
        FakeEdupage.instances.append(self)

    def login(self, username: str, password: str, subdomain: str = "login1") -> FakeTwoFactorLogin | None:
        if (username, password) not in self.valid_credentials:
            raise BadCredentialsException()
        self.subdomain = subdomain
        self.username = username
        self.is_logged_in = True
        if self.require_2fa:
            return FakeTwoFactorLogin()
        return None

    # --- data surface used by the wrapper -----------------------------------
    def get_notifications(self) -> list[FakeEvent]:
        return list(self.events)

    def get_notification_history(self, since: date) -> list[FakeEvent]:
        return [e for e in self.events if e.timestamp.date() >= since]

    def get_my_timetable(self, day: date) -> FakeTimetable | None:
        return FakeTimetable(lessons=[FakeLesson(period=1, subject="Mathe")])

    def get_timetable_changes(self, day: date) -> list[dict]:
        return [{"date": day.isoformat(), "period": 2, "subject": "Physik", "action": "entfällt"}]

    def get_grades(self) -> list[FakeGrade]:
        return list(self.grades)

    def get_text_grades(self) -> list[dict]:
        return [{"subject": "Mathe", "text": "Sehr gut mitgearbeitet"}]

    def get_meals(self, day: date) -> Any:
        return self.meals

    def get_teachers(self) -> list[FakeTeacher]:
        return [FakeTeacher(1, "Frau Muster")]

    def get_students(self) -> list[FakeTeacher]:
        return [FakeTeacher(2, "Max Mustermann")]

    def send_message(self, recipients: list[str], body: str) -> int:
        self.session.posts.append(("send", {"recipients": recipients, "body": body}))
        return 4242
