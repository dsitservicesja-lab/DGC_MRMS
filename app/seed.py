import json
from pathlib import Path
from sqlmodel import Session, select
from .models import Staff
from .db import engine

def seed_if_empty():
    data_path = Path(__file__).resolve().parents[1] / "data" / "seed.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    with Session(engine) as session:
        if session.exec(select(Staff)).first():
            return
        for s in data["staff"]:
            session.add(Staff(**s))
        session.commit()

def get_lists(session: Session | None = None):
    data_path = Path(__file__).resolve().parents[1] / "data" / "seed.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))

    if session is None:
        with Session(engine) as db_session:
            staff = db_session.exec(select(Staff).order_by(Staff.display)).all()
    else:
        staff = session.exec(select(Staff).order_by(Staff.display)).all()

    data["staff"] = [
        {
            "display": s.display,
            "branch": s.branch,
            "ext": s.ext,
            "mobile": s.mobile,
            "cug": s.cug,
            "office": s.office,
            "floor": s.floor,
        }
        for s in staff
    ]
    return data
