import json
from pathlib import Path
from sqlmodel import Session, select
from .models import Staff
from .db import engine

LIST_CATEGORIES = {
    "meeting_locations",
    "branches",
    "meeting_types",
    "confidential_opts",
    "urgency_levels",
    "delivery_types",
    "item_types",
    "goj_agencies",
}

DEFAULT_APP_SETTINGS = {
    "email_notifications_enabled": True,
}


def _data_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "seed.json"


def read_seed_data() -> dict:
    data = json.loads(_data_path().read_text(encoding="utf-8"))
    if "app_settings" not in data or not isinstance(data["app_settings"], dict):
        data["app_settings"] = dict(DEFAULT_APP_SETTINGS)
    else:
        for k, v in DEFAULT_APP_SETTINGS.items():
            data["app_settings"].setdefault(k, v)
    return data


def write_seed_data(data: dict) -> None:
    path = _data_path()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def seed_if_empty():
    data = read_seed_data()
    with Session(engine) as session:
        if session.exec(select(Staff)).first():
            return
        for s in data["staff"]:
            session.add(Staff(**s))
        session.commit()

def get_lists(session: Session | None = None):
    data = read_seed_data()

    if session is None:
        with Session(engine) as db_session:
            staff = db_session.exec(select(Staff).order_by(Staff.display)).all()
    else:
        staff = session.exec(select(Staff).order_by(Staff.display)).all()

    data["staff"] = [
        {
            "display": s.display,
            "role": s.role,
            "branch": s.branch,
            "ext": s.ext,
            "mobile": s.mobile,
            "cug": s.cug,
            "office": s.office,
            "floor": s.floor,
            "email": s.email,
        }
        for s in staff
    ]
    return data


def email_notifications_enabled() -> bool:
    data = read_seed_data()
    return bool(data.get("app_settings", {}).get("email_notifications_enabled", True))


def set_email_notifications_enabled(enabled: bool) -> None:
    data = read_seed_data()
    settings = data.get("app_settings", {})
    settings["email_notifications_enabled"] = bool(enabled)
    data["app_settings"] = settings
    write_seed_data(data)


def get_list_categories(session: Session | None = None) -> dict[str, list[str]]:
    data = get_lists(session)
    return {k: list(data.get(k, [])) for k in LIST_CATEGORIES}


def add_list_item(category: str, value: str) -> bool:
    if category not in LIST_CATEGORIES:
        return False
    value_clean = value.strip()
    if not value_clean:
        return False

    data = read_seed_data()
    existing = data.get(category, [])
    if any(str(v).casefold() == value_clean.casefold() for v in existing):
        return False

    existing.append(value_clean)
    data[category] = existing
    write_seed_data(data)
    return True


def remove_list_item(category: str, value: str) -> bool:
    if category not in LIST_CATEGORIES:
        return False

    data = read_seed_data()
    existing = data.get(category, [])
    filtered = [v for v in existing if str(v).casefold() != value.casefold()]
    if len(filtered) == len(existing):
        return False

    data[category] = filtered
    write_seed_data(data)
    return True
