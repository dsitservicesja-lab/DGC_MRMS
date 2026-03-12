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

def get_lists():
    data_path = Path(__file__).resolve().parents[1] / "data" / "seed.json"
    return json.loads(data_path.read_text(encoding="utf-8"))
