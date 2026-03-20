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
    email_notifications_enabled,
    set_email_notifications_enabled,
)
from .models import MeetingRequest, MessengerRequest, MeetingAttendee, Staff
from .utils import (
    next_meeting_booking_id,
    next_messenger_request_id,
    staff_autofill,
    check_meeting_conflict,
    staff_email,
    staff_emails_for_names,
    staff_emails_for_roles,
    staff_can_submit_requests,
)
from .auth import authenticate_user, is_admin, is_superadmin, can_view_requests
from .config import SECRET_KEY
from .notifications import (
    notify_meeting_submitted,
    notify_meeting_status,
    notify_messenger_submitted,
    notify_messenger_status,
)

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
STAFF_ROLES = ["superadmin", "admin", "requestor", "messenger"]


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
        "superadmin": is_superadmin(request),
        "error": error,
        "labels": SYSTEM_LIST_LABELS,
        "categories": sorted(LIST_CATEGORIES),
        "lists": get_list_categories(session),
        "email_notifications_enabled": email_notifications_enabled(),
    })

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("home.html", {
        "request": request,
        "admin": can_view_requests(request),
        "superadmin": is_superadmin(request),
    })

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": None,
        "admin": can_view_requests(request),
        "superadmin": is_superadmin(request),
    })

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    role = authenticate_user(username, password)
    if role:
        request.session["role"] = role
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "Invalid credentials",
        "admin": False,
        "superadmin": False,
    })

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)

@app.get("/meetings/new", response_class=HTMLResponse)
def meeting_new(request: Request, session: Session = Depends(get_session)):
    l = lists(session)
    requestors = [
        s for s in l["staff"]
        if str(s.get("role", "requestor")).strip().casefold() in {"requestor", "admin", "superadmin"}
    ]
    return templates.TemplateResponse("meeting_new.html", {
        "request": request,
        "admin": can_view_requests(request),
        "superadmin": is_superadmin(request),
        "requestors": requestors,
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
    if not staff_can_submit_requests(session, requested_by):
        return templates.TemplateResponse("error.html", {"request": request, "admin": is_admin(request),
            "title":"Invalid Requestor",
            "message":"Selected requester role cannot submit requests. Please choose a user with requestor/admin/superadmin role."})

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

    req_email = staff_email(session, requested_by)
    att_emails = staff_emails_for_names(session, normalized)
    admin_emails = staff_emails_for_roles(session, ["admin", "superadmin"])
    to_emails = list(dict.fromkeys(e for e in [req_email] + att_emails + admin_emails if e))
    notify_meeting_submitted(
        booking_id=m.booking_id,
        requested_by=requested_by,
        start_date=m.start_date,
        start_time=m.start_time,
        end_date=m.end_date,
        end_time=m.end_time,
        location=location,
        purpose=purpose,
        meeting_type=meeting_type,
        attendees=normalized,
        to_emails=to_emails,
    )
    return RedirectResponse("/thanks", status_code=303)

@app.get("/messenger/new", response_class=HTMLResponse)
def messenger_new(request: Request, session: Session = Depends(get_session)):
    l = lists(session)
    requestors = [
        s for s in l["staff"]
        if str(s.get("role", "requestor")).strip().casefold() in {"requestor", "admin", "superadmin"}
    ]
    return templates.TemplateResponse("messenger_new.html", {
        "request": request,
        "admin": can_view_requests(request),
        "superadmin": is_superadmin(request),
        "requestors": requestors,
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
    if not staff_can_submit_requests(session, requested_by):
        return templates.TemplateResponse("error.html", {"request": request, "admin": is_admin(request),
            "title":"Invalid Requestor",
            "message":"Selected requester role cannot submit requests. Please choose a user with requestor/admin/superadmin role."})

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

    req_email = staff_email(session, requested_by)
    ops_emails = staff_emails_for_roles(session, ["messenger", "admin", "superadmin"])
    to_emails = list(dict.fromkeys(e for e in [req_email] + ops_emails if e))
    notify_messenger_submitted(
        request_id=r.request_id,
        requested_by=requested_by,
        pickup_location=pickup_location,
        delivery_type=delivery_type,
        destination_name=destination_name,
        destination_area=destination_area,
        item_type=item_type,
        urgency_level=urgency_level,
        required_by_date=rbd,
        required_by_time=rbt,
        to_email=to_emails,
    )
    return RedirectResponse("/thanks", status_code=303)

@app.get("/thanks", response_class=HTMLResponse)
def thanks(request: Request):
    return templates.TemplateResponse("thanks.html", {
        "request": request,
        "admin": can_view_requests(request),
        "superadmin": is_superadmin(request),
    })

@app.get("/my-requests", response_class=HTMLResponse)
def my_requests(request: Request, name: str = "", session: Session = Depends(get_session)):
    l = lists(session)
    requestors = [
        s for s in l["staff"]
        if str(s.get("role", "requestor")).strip().casefold() in {"requestor", "admin", "superadmin"}
    ]
    meetings: list = []
    messenger_reqs: list = []
    attendee_lookup: dict[int, list[str]] = {}

    if name.strip():
        meetings = session.exec(
            select(MeetingRequest)
            .where(MeetingRequest.requested_by == name.strip())
            .order_by(MeetingRequest.submitted_ts.desc())
        ).all()
        messenger_reqs = session.exec(
            select(MessengerRequest)
            .where(MessengerRequest.requested_by == name.strip())
            .order_by(MessengerRequest.submitted_ts.desc())
        ).all()
        if meetings:
            meeting_ids = [m.id for m in meetings]
            attendees = session.exec(
                select(MeetingAttendee).where(MeetingAttendee.meeting_id.in_(meeting_ids))
            ).all()
            for a in attendees:
                attendee_lookup.setdefault(a.meeting_id, []).append(a.attendee_name)
            for m in meetings:
                if m.id not in attendee_lookup:
                    attendee_lookup[m.id] = attendees_from_legacy(m)

    return templates.TemplateResponse("my_requests.html", {
        "request": request,
        "admin": can_view_requests(request),
        "superadmin": is_superadmin(request),
        "requestors": requestors,
        "selected_name": name.strip(),
        "meetings": meetings,
        "messenger_reqs": messenger_reqs,
        "attendee_lookup": attendee_lookup,
    })

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, session: Session = Depends(get_session)):
    if not can_view_requests(request):
        return RedirectResponse("/login", status_code=303)
    pending_meet = session.exec(select(MeetingRequest).where(MeetingRequest.status=="Pending").order_by(MeetingRequest.submitted_ts.desc())).all()
    pending_msg = session.exec(select(MessengerRequest).where(MessengerRequest.status=="Pending").order_by(MessengerRequest.submitted_ts.desc())).all()

    # Meetings in progress: Approved meetings whose time window includes now
    now = datetime.now()
    approved_meetings = session.exec(select(MeetingRequest).where(MeetingRequest.status=="Approved")).all()
    in_progress_meet = []
    for m in approved_meetings:
        start_dt = datetime.combine(m.start_date, m.start_time)
        end_dt = datetime.combine(m.end_date, m.end_time)
        if start_dt <= now <= end_dt:
            in_progress_meet.append(m)

    # Summary counts
    all_meetings = session.exec(select(MeetingRequest)).all()
    all_messenger = session.exec(select(MessengerRequest)).all()
    meeting_counts: dict[str, int] = {}
    for m in all_meetings:
        meeting_counts[m.status] = meeting_counts.get(m.status, 0) + 1
    messenger_counts: dict[str, int] = {}
    for r in all_messenger:
        messenger_counts[r.status] = messenger_counts.get(r.status, 0) + 1

    # Recent approved/declined/completed meetings and messenger requests
    non_pending_meet = session.exec(
        select(MeetingRequest).where(MeetingRequest.status != "Pending")
        .order_by(MeetingRequest.submitted_ts.desc())
    ).all()
    non_pending_msg = session.exec(
        select(MessengerRequest).where(MessengerRequest.status != "Pending")
        .order_by(MessengerRequest.submitted_ts.desc())
    ).all()

    attendees = session.exec(select(MeetingAttendee)).all()
    attendee_lookup: dict[int, list[str]] = {}
    for a in attendees:
        attendee_lookup.setdefault(a.meeting_id, []).append(a.attendee_name)

    all_meet_ids = set(m.id for m in pending_meet) | set(m.id for m in in_progress_meet) | set(m.id for m in non_pending_meet)
    for mid in all_meet_ids:
        if mid not in attendee_lookup:
            match = next((m for m in all_meetings if m.id == mid), None)
            if match:
                attendee_lookup[mid] = attendees_from_legacy(match)

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "admin": True,
        "superadmin": is_superadmin(request),
        "pending_meet": pending_meet,
        "pending_msg": pending_msg,
        "in_progress_meet": in_progress_meet,
        "non_pending_meet": non_pending_meet,
        "non_pending_msg": non_pending_msg,
        "meeting_counts": meeting_counts,
        "messenger_counts": messenger_counts,
        "total_meetings": len(all_meetings),
        "total_messenger": len(all_messenger),
        "attendee_lookup": attendee_lookup,
    })


@app.get("/admin/system", response_class=HTMLResponse)
def admin_system_settings(request: Request, session: Session = Depends(get_session)):
    if not is_superadmin(request):
        return RedirectResponse("/login", status_code=303)
    return render_admin_settings(request, session)


@app.post("/admin/system/add")
def admin_system_add(
    request: Request,
    category: str = Form(...),
    value: str = Form(...),
    session: Session = Depends(get_session),
):
    if not is_superadmin(request):
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
    if not is_superadmin(request):
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


@app.post("/admin/system/notifications")
def admin_system_notifications_toggle(
    request: Request,
    email_notifications_enabled_value: str = Form("0"),
):
    if not is_superadmin(request):
        return RedirectResponse("/login", status_code=303)
    set_email_notifications_enabled(email_notifications_enabled_value == "1")
    return RedirectResponse("/admin/system", status_code=303)


@app.get("/admin/users", response_class=HTMLResponse)
def admin_users(request: Request, session: Session = Depends(get_session)):
    if not is_superadmin(request):
        return RedirectResponse("/login", status_code=303)
    users = session.exec(select(Staff).order_by(Staff.display)).all()
    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "admin": True,
        "superadmin": True,
        "roles": STAFF_ROLES,
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
    email: str = Form(""),
    role: str = Form("requestor"),
    session: Session = Depends(get_session),
):
    if not is_superadmin(request):
        return RedirectResponse("/login", status_code=303)

    display_clean = display.strip()
    if not display_clean:
        users = session.exec(select(Staff).order_by(Staff.display)).all()
        return templates.TemplateResponse("admin_users.html", {
            "request": request,
            "admin": True,
            "superadmin": True,
            "roles": STAFF_ROLES,
            "users": users,
            "error": "Display name is required.",
        })

    existing = session.exec(select(Staff)).all()
    if any(u.display.casefold() == display_clean.casefold() for u in existing):
        users = session.exec(select(Staff).order_by(Staff.display)).all()
        return templates.TemplateResponse("admin_users.html", {
            "request": request,
            "admin": True,
            "superadmin": True,
            "roles": STAFF_ROLES,
            "users": users,
            "error": f"A user named '{display_clean}' already exists.",
        })

    role_clean = role.strip().casefold()
    if role_clean not in STAFF_ROLES:
        role_clean = "requestor"

    session.add(Staff(
        display=display_clean,
        role=role_clean,
        branch=branch.strip(),
        ext=ext.strip(),
        mobile=mobile.strip(),
        cug=cug.strip(),
        office=office.strip(),
        floor=floor.strip(),
        email=email.strip(),
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
    email: str = Form(""),
    role: str = Form("requestor"),
    session: Session = Depends(get_session),
):
    if not is_superadmin(request):
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

    role_clean = role.strip().casefold()
    if role_clean not in STAFF_ROLES:
        role_clean = "requestor"

    user.display = display_clean
    user.role = role_clean
    user.branch = branch.strip()
    user.ext = ext.strip()
    user.mobile = mobile.strip()
    user.cug = cug.strip()
    user.office = office.strip()
    user.floor = floor.strip()
    user.email = email.strip()
    session.add(user)
    session.commit()
    return RedirectResponse("/admin/users", status_code=303)


@app.post("/admin/users/{uid}/delete")
def admin_user_delete(request: Request, uid: int, session: Session = Depends(get_session)):
    if not is_superadmin(request):
        return RedirectResponse("/login", status_code=303)
    user = session.get(Staff, uid)
    if user:
        session.delete(user)
        session.commit()
    return RedirectResponse("/admin/users", status_code=303)

@app.post("/admin/meetings/{mid}/status")
def admin_meeting_status(request: Request, mid: int, status: str = Form(...), session: Session = Depends(get_session)):
    if not can_view_requests(request):
        return RedirectResponse("/login", status_code=303)
    m = session.get(MeetingRequest, mid)
    if m:
        m.status = status
        session.add(m)
        session.commit()
        att_rows = session.exec(select(MeetingAttendee).where(MeetingAttendee.meeting_id == m.id)).all()
        att_names = [a.attendee_name for a in att_rows]
        to_emails = list(dict.fromkeys(
            e for e in staff_emails_for_names(session, [m.requested_by] + att_names) if e
        ))
        notify_meeting_status(
            booking_id=m.booking_id,
            requested_by=m.requested_by,
            status=status,
            start_date=m.start_date,
            start_time=m.start_time,
            end_date=m.end_date,
            end_time=m.end_time,
            location=m.location,
            to_emails=to_emails,
        )
    return RedirectResponse("/admin", status_code=303)

@app.post("/admin/messenger/{rid}/status")
def admin_messenger_status(request: Request, rid: int, status: str = Form(...), session: Session = Depends(get_session)):
    if not can_view_requests(request):
        return RedirectResponse("/login", status_code=303)
    r = session.get(MessengerRequest, rid)
    if r:
        r.status = status
        session.add(r)
        session.commit()
        req_email = staff_email(session, r.requested_by)
        to_emails = [req_email] if req_email else []
        if status == "Approved":
            ops_emails = staff_emails_for_roles(session, ["messenger", "admin", "superadmin"])
            to_emails = list(dict.fromkeys(e for e in to_emails + ops_emails if e))
        notify_messenger_status(
            request_id=r.request_id,
            requested_by=r.requested_by,
            status=status,
            destination_name=r.destination_name,
            destination_area=r.destination_area,
            to_email=to_emails,
        )
    return RedirectResponse("/admin", status_code=303)
