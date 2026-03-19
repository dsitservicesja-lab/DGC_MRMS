from datetime import datetime, timedelta
from sqlmodel import Session, select
from .models import MeetingRequest, MessengerRequest, Staff

def next_meeting_booking_id(session: Session) -> str:
    last = session.exec(select(MeetingRequest).order_by(MeetingRequest.id.desc())).first()
    n = 1 if not last else last.id + 1
    return f"MEETDGC{n}"

def next_messenger_request_id(session: Session) -> str:
    last = session.exec(select(MessengerRequest).order_by(MessengerRequest.id.desc())).first()
    n = 1 if not last else last.id + 1
    return f"M-NGR-DGC-{n:02d}"

def staff_autofill(session: Session, display_name: str):
    s = session.exec(select(Staff).where(Staff.display == display_name)).first()
    if not s:
        return {}
    phone = (s.mobile or "").strip() or (s.cug or "").strip()
    parts = []
    if phone:
        parts.append(phone)
    if (s.ext or "").strip():
        parts.append(f"Ext: {s.ext.strip()}")
    contact = " / ".join(parts)
    return {
        "contact": contact,
        "branch": s.branch,
        "ext": s.ext,
        "mobile": s.mobile,
        "cug": s.cug,
        "office": s.office,
    }

def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end

def check_meeting_conflict(session: Session, start_dt: datetime, end_dt: datetime, location: str, gap_minutes: int = 15):
    gap = timedelta(minutes=gap_minutes)
    window_start = start_dt - gap
    window_end = end_dt + gap
    q = session.exec(select(MeetingRequest).where(MeetingRequest.location == location).where(MeetingRequest.status != "Declined"))
    for m in q:
        es = datetime.combine(m.start_date, m.start_time)
        ee = datetime.combine(m.end_date, m.end_time)
        if overlaps(window_start, window_end, es, ee):
            return m
    return None


def staff_email(session: Session, display_name: str) -> str:
    s = session.exec(select(Staff).where(Staff.display == display_name)).first()
    return (s.email or "").strip() if s else ""


def staff_emails_for_names(session: Session, names: list[str]) -> list[str]:
    result = []
    for name in names:
        e = staff_email(session, name)
        if e:
            result.append(e)
    return result
