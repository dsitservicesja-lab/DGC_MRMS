from typing import Optional
from datetime import datetime, date, time
from sqlmodel import SQLModel, Field

class Staff(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    display: str = Field(index=True)
    role: str = "requestor"
    branch: str
    ext: str = ""
    mobile: str = ""
    cug: str = ""
    office: str = ""
    floor: str = ""
    email: str = ""

class MeetingRequest(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    booking_id: str = Field(index=True, unique=True)
    request_date: date
    requested_by: str = Field(index=True)
    requester_contact: str = ""
    requester_branch: str = ""
    requester_extension: str = ""
    requester_mobile: str = ""
    requester_cug: str = ""
    requester_office: str = ""
    start_date: date
    end_date: date
    start_time: time
    end_time: time
    location: str
    purpose: str = ""
    meeting_type: str = ""
    confidential: str = "Open"
    expected_attendee: str = ""
    attendees_details: str = ""
    status: str = "Pending"
    submitted_ts: datetime = Field(default_factory=datetime.utcnow)


class MeetingAttendee(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: int = Field(index=True, foreign_key="meetingrequest.id")
    attendee_name: str = Field(index=True)

class MessengerRequest(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    request_id: str = Field(index=True, unique=True)
    request_date: date
    requested_by: str = Field(index=True)
    requester_contact: str = ""
    branch: str = ""
    contact_extension: str = ""
    requester_office: str = ""
    pickup_location: str = ""
    delivery_type: str = ""
    destination_name: str = ""
    destination_area: str = ""
    item_type: str = ""
    urgency_level: str = "Normal"
    required_by_date: Optional[date] = None
    required_by_time: Optional[time] = None
    notes: str = ""
    status: str = "Pending"
    submitted_ts: datetime = Field(default_factory=datetime.utcnow)
