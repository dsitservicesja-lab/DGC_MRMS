from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from datetime import datetime, date
from pathlib import Path

from sqlmodel import Session, select
from .db import init_db, get_session
from .seed import seed_if_empty, get_lists
from .models import MeetingRequest, MessengerRequest
from .utils import next_meeting_booking_id, next_messenger_request_id, staff_autofill, check_meeting_conflict
from .auth import verify_password, is_admin
from .config import SECRET_KEY

app = FastAPI(title="DGC Requests & Approvals")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
LOGO_PATH = Path("cropped-Logo.png")


@app.get("/logo")
def logo():
    if LOGO_PATH.exists():
        return FileResponse(LOGO_PATH)
    raise HTTPException(status_code=404, detail="Logo not found")

@app.on_event("startup")
def startup():
    init_db()
    seed_if_empty()

def lists():
    return get_lists()

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
def meeting_new(request: Request):
    l = lists()
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
    expected_attendee: str = Form(""),
    attendees_details: str = Form(""),
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
        expected_attendee=expected_attendee,
        attendees_details=attendees_details,
        status="Pending",
    )
    session.add(m)
    session.commit()
    return RedirectResponse("/thanks", status_code=303)

@app.get("/messenger/new", response_class=HTMLResponse)
def messenger_new(request: Request):
    l = lists()
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
    return templates.TemplateResponse("admin.html", {"request": request, "admin": True, "pending_meet": pending_meet, "pending_msg": pending_msg})

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
