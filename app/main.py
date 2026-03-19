from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from datetime import datetime, date
import re
from pathlib import Path

from sqlmodel import Session, select
from .db import init_db, get_session
from .seed import (
    seed_if_empty,
    get_lists,
    LIST_CATEGORIES,
    get_list_categories,
    add_list_item,
    remove_list_item,
)
from .models import MeetingRequest, MessengerRequest, MeetingAttendee, Staff
from .utils import next_meeting_booking_id, next_messenger_request_id, staff_autofill, check_meeting_conflict
from .auth import verify_password, is_admin
from .config import SECRET_KEY

app = FastAPI(title="DGC Requests & Approvals")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
LOGO_PATH = Path("cropped-Logo.png")
SYSTEM_LIST_LABELS = {
    "meeting_locations": "Meeting Locations",
    "branches": "Branches",
    "meeting_types": "Meeting Types",
    "confidential_opts": "Confidentiality Options",
    "urgency_levels": "Urgency Levels",
    "delivery_types": "Delivery Types",
    "item_types": "Item Types",
    "goj_agencies": "GOJ Agencies",
}


@app.get("/logo")
def logo():
    if LOGO_PATH.exists():
        return FileResponse(LOGO_PATH)
    raise HTTPException(status_code=404, detail="Logo not found")

@app.on_event("startup")
def startup():
    init_db()
    seed_if_empty()

def lists(session: Session):
    return get_lists(session)


def split_attendees(raw_text: str) -> list[str]:
    if not raw_text:
        return []
    parts = re.split(r"[\n,;]+", raw_text)
    return [p.strip() for p in parts if p.strip()]


def dedupe_keep_order(values: list[str]) -> list[str]:
    seen = set()
    cleaned: list[str] = []
    for v in values:
        key = v.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(v)
    return cleaned


def attendees_from_legacy(m: MeetingRequest) -> list[str]:
    values: list[str] = []
    if m.expected_attendee:
        values.append(m.expected_attendee.strip())
    values.extend(split_attendees(m.attendees_details))
    return dedupe_keep_order([v for v in values if v])


def normalize_form_attendees(raw_attendees: str | list[str], other_attendees: str) -> list[str]:
    selected: list[str]
    if isinstance(raw_attendees, list):
        selected = raw_attendees
    elif raw_attendees.strip():
        selected = [raw_attendees]
    else:
        selected = []

    return dedupe_keep_order([a.strip() for a in selected if a and a.strip()] + split_attendees(other_attendees))


def render_admin_settings(request: Request, session: Session, error: str | None = None):
    return templates.TemplateResponse("admin_system.html", {
        "request": request,
        "admin": True,
        "error": error,
        "labels": SYSTEM_LIST_LABELS,
        "categories": sorted(LIST_CATEGORIES),
        "lists": get_list_categories(session),
    })

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request, "admin": is_admin(request)})

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None, "admin": is_admin(request)})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if verify_password(username, password):
        request.session["role"] = "admin"
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials", "admin": False})

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)

@app.get("/meetings/new", response_class=HTMLResponse)
def meeting_new(request: Request, session: Session = Depends(get_session)):
    l = lists(session)
    return templates.TemplateResponse("meeting_new.html", {
        "request": request,
        "admin": is_admin(request),
        "staff": l["staff"],
        "locations": l["meeting_locations"],
        "meeting_types": l["meeting_types"],
        "confidential_opts": l["confidential_opts"],
    })

@app.post("/meetings/new")
def meeting_create(
    request: Request,
    request_date: date = Form(...),
    requested_by: str = Form(...),
    start_date: date = Form(...),
    end_date: date = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    location: str = Form(...),
    purpose: str = Form(""),
    meeting_type: str = Form(""),
    confidential: str = Form("Open"),
    attendees: str | list[str] = Form(default=[]),
    other_attendees: str = Form(""),
    session: Session = Depends(get_session),
):
    st = datetime.strptime(start_time, "%H:%M").time()
    et = datetime.strptime(end_time, "%H:%M").time()
    start_dt = datetime.combine(start_date, st)
    end_dt = datetime.combine(end_date, et)
    conflict = check_meeting_conflict(session, start_dt, end_dt, location, gap_minutes=15)
    if conflict:
        return templates.TemplateResponse("error.html", {"request": request, "admin": is_admin(request),
            "title":"Meeting Conflict",
            "message": f"Conflict with existing booking {conflict.booking_id} at {conflict.location}. 15-minute gap required."})

    normalized = normalize_form_attendees(attendees, other_attendees)
    if not normalized:
        return templates.TemplateResponse("error.html", {"request": request, "admin": is_admin(request),
            "title":"Missing Attendees",
            "message":"Please choose at least one attendee or provide attendee names."})

    booking_id = next_meeting_booking_id(session)
    auto = staff_autofill(session, requested_by)
    m = MeetingRequest(
        booking_id=booking_id,
        request_date=request_date,
        requested_by=requested_by,
        requester_contact=auto.get("contact",""),
        requester_branch=auto.get("branch",""),
        requester_extension=auto.get("ext",""),
        requester_mobile=auto.get("mobile",""),
        requester_cug=auto.get("cug",""),
        requester_office=auto.get("office",""),
        start_date=start_date, end_date=end_date,
        start_time=st, end_time=et,
        location=location,
        purpose=purpose,
        meeting_type=meeting_type,
        confidential=confidential,
        expected_attendee=normalized[0],
        attendees_details="; ".join(normalized),
        status="Pending",
    )
    session.add(m)
    session.commit()
    session.refresh(m)

    for attendee in normalized:
        session.add(MeetingAttendee(meeting_id=m.id, attendee_name=attendee))
    session.commit()
    return RedirectResponse("/thanks", status_code=303)

@app.get("/messenger/new", response_class=HTMLResponse)
def messenger_new(request: Request, session: Session = Depends(get_session)):
    l = lists(session)
    return templates.TemplateResponse("messenger_new.html", {
        "request": request,
        "admin": is_admin(request),
        "staff": l["staff"],
        "delivery_types": l["delivery_types"],
        "item_types": l["item_types"],
        "urgency_levels": l["urgency_levels"],
        "goj_agencies": l["goj_agencies"],
    })

@app.post("/messenger/new")
def messenger_create(
    request: Request,
    request_date: date = Form(...),
    requested_by: str = Form(...),
    pickup_location: str = Form(""),
    delivery_type: str = Form(""),
    destination_name: str = Form(""),
    destination_area: str = Form(""),
    item_type: str = Form(""),
    urgency_level: str = Form("Normal"),
    required_by_date: str = Form(""),
    required_by_time: str = Form(""),
    notes: str = Form(""),
    session: Session = Depends(get_session),
):
    if urgency_level in ("Urgent","Critical") and (not required_by_date or not required_by_time):
        return templates.TemplateResponse("error.html", {"request": request, "admin": is_admin(request),
            "title":"Missing Required By",
            "message":"Urgent/Critical requests must include Required By Date AND Time."})
    req_id = next_messenger_request_id(session)
    auto = staff_autofill(session, requested_by)
    rbd = datetime.strptime(required_by_date, "%Y-%m-%d").date() if required_by_date else None
    rbt = datetime.strptime(required_by_time, "%H:%M").time() if required_by_time else None
    r = MessengerRequest(
        request_id=req_id,
        request_date=request_date,
        requested_by=requested_by,
        requester_contact=auto.get("contact",""),
        branch=auto.get("branch",""),
        contact_extension=auto.get("ext",""),
        requester_office=auto.get("office",""),
        pickup_location=pickup_location,
        delivery_type=delivery_type,
        destination_name=destination_name,
        destination_area=destination_area,
        item_type=item_type,
        urgency_level=urgency_level,
        required_by_date=rbd,
        required_by_time=rbt,
        notes=notes,
        status="Pending",
    )
    session.add(r)
    session.commit()
    return RedirectResponse("/thanks", status_code=303)

@app.get("/thanks", response_class=HTMLResponse)
def thanks(request: Request):
    return templates.TemplateResponse("thanks.html", {"request": request, "admin": is_admin(request)})

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, session: Session = Depends(get_session)):
    if not is_admin(request):
        return RedirectResponse("/login", status_code=303)
    pending_meet = session.exec(select(MeetingRequest).where(MeetingRequest.status=="Pending").order_by(MeetingRequest.submitted_ts.desc())).all()
    pending_msg = session.exec(select(MessengerRequest).where(MessengerRequest.status=="Pending").order_by(MessengerRequest.submitted_ts.desc())).all()

    attendees = session.exec(select(MeetingAttendee)).all()
    attendee_lookup: dict[int, list[str]] = {}
    for a in attendees:
        attendee_lookup.setdefault(a.meeting_id, []).append(a.attendee_name)

    for m in pending_meet:
        if m.id not in attendee_lookup:
            attendee_lookup[m.id] = attendees_from_legacy(m)

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "admin": True,
        "pending_meet": pending_meet,
        "pending_msg": pending_msg,
        "attendee_lookup": attendee_lookup,
    })


@app.get("/admin/system", response_class=HTMLResponse)
def admin_system_settings(request: Request, session: Session = Depends(get_session)):
    if not is_admin(request):
        return RedirectResponse("/login", status_code=303)
    return render_admin_settings(request, session)


@app.post("/admin/system/add")
def admin_system_add(
    request: Request,
    category: str = Form(...),
    value: str = Form(...),
    session: Session = Depends(get_session),
):
    if not is_admin(request):
        return RedirectResponse("/login", status_code=303)

    if category not in LIST_CATEGORIES:
        return render_admin_settings(request, session, error="Invalid settings category.")

    if not add_list_item(category, value):
        return render_admin_settings(
            request,
            session,
            error="Could not add value. It may be blank or already exists.",
        )

    return RedirectResponse("/admin/system", status_code=303)


@app.post("/admin/system/remove")
def admin_system_remove(
    request: Request,
    category: str = Form(...),
    value: str = Form(...),
    session: Session = Depends(get_session),
):
    if not is_admin(request):
        return RedirectResponse("/login", status_code=303)

    if category not in LIST_CATEGORIES:
        return render_admin_settings(request, session, error="Invalid settings category.")

    if not remove_list_item(category, value):
        return render_admin_settings(
            request,
            session,
            error="Could not remove value. It may no longer exist.",
        )

    return RedirectResponse("/admin/system", status_code=303)


@app.get("/admin/users", response_class=HTMLResponse)
def admin_users(request: Request, session: Session = Depends(get_session)):
    if not is_admin(request):
        return RedirectResponse("/login", status_code=303)
    users = session.exec(select(Staff).order_by(Staff.display)).all()
    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "admin": True,
        "users": users,
        "error": None,
    })


@app.post("/admin/users")
def admin_user_add(
    request: Request,
    display: str = Form(...),
    branch: str = Form(""),
    ext: str = Form(""),
    mobile: str = Form(""),
    cug: str = Form(""),
    office: str = Form(""),
    floor: str = Form(""),
    session: Session = Depends(get_session),
):
    if not is_admin(request):
        return RedirectResponse("/login", status_code=303)

    display_clean = display.strip()
    if not display_clean:
        users = session.exec(select(Staff).order_by(Staff.display)).all()
        return templates.TemplateResponse("admin_users.html", {
            "request": request,
            "admin": True,
            "users": users,
            "error": "Display name is required.",
        })

    existing = session.exec(select(Staff)).all()
    if any(u.display.casefold() == display_clean.casefold() for u in existing):
        users = session.exec(select(Staff).order_by(Staff.display)).all()
        return templates.TemplateResponse("admin_users.html", {
            "request": request,
            "admin": True,
            "users": users,
            "error": f"A user named '{display_clean}' already exists.",
        })

    session.add(Staff(
        display=display_clean,
        branch=branch.strip(),
        ext=ext.strip(),
        mobile=mobile.strip(),
        cug=cug.strip(),
        office=office.strip(),
        floor=floor.strip(),
    ))
    session.commit()
    return RedirectResponse("/admin/users", status_code=303)


@app.post("/admin/users/{uid}/update")
def admin_user_update(
    request: Request,
    uid: int,
    display: str = Form(...),
    branch: str = Form(""),
    ext: str = Form(""),
    mobile: str = Form(""),
    cug: str = Form(""),
    office: str = Form(""),
    floor: str = Form(""),
    session: Session = Depends(get_session),
):
    if not is_admin(request):
        return RedirectResponse("/login", status_code=303)

    user = session.get(Staff, uid)
    if not user:
        return RedirectResponse("/admin/users", status_code=303)

    display_clean = display.strip()
    if not display_clean:
        return RedirectResponse("/admin/users", status_code=303)

    existing = session.exec(select(Staff)).all()
    if any(u.id != uid and u.display.casefold() == display_clean.casefold() for u in existing):
        return RedirectResponse("/admin/users", status_code=303)

    user.display = display_clean
    user.branch = branch.strip()
    user.ext = ext.strip()
    user.mobile = mobile.strip()
    user.cug = cug.strip()
    user.office = office.strip()
    user.floor = floor.strip()
    session.add(user)
    session.commit()
    return RedirectResponse("/admin/users", status_code=303)


@app.post("/admin/users/{uid}/delete")
def admin_user_delete(request: Request, uid: int, session: Session = Depends(get_session)):
    if not is_admin(request):
        return RedirectResponse("/login", status_code=303)
    user = session.get(Staff, uid)
    if user:
        session.delete(user)
        session.commit()
    return RedirectResponse("/admin/users", status_code=303)

@app.post("/admin/meetings/{mid}/status")
def admin_meeting_status(request: Request, mid: int, status: str = Form(...), session: Session = Depends(get_session)):
    if not is_admin(request):
        return RedirectResponse("/login", status_code=303)
    m = session.get(MeetingRequest, mid)
    if m:
        m.status = status
        session.add(m); session.commit()
    return RedirectResponse("/admin", status_code=303)

@app.post("/admin/messenger/{rid}/status")
def admin_messenger_status(request: Request, rid: int, status: str = Form(...), session: Session = Depends(get_session)):
    if not is_admin(request):
        return RedirectResponse("/login", status_code=303)
    r = session.get(MessengerRequest, rid)
    if r:
        r.status = status
        session.add(r); session.commit()
    return RedirectResponse("/admin", status_code=303)
