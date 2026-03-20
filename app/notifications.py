"""
Email notification helpers for DGC Requests & Approvals.
All sends are async (background thread) so they never block a request.
Configure via environment variables (see config.py).
"""
import smtplib
import logging
from concurrent.futures import ThreadPoolExecutor
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASSWORD, EMAIL_FROM, EMAIL_ENABLED
from .seed import email_notifications_enabled

logger = logging.getLogger(__name__)

# Thread-pool keeps worker threads alive so emails are reliably delivered
# even when the calling request finishes quickly.
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="email")

_BRAND = "#0f5560"


def _base(title: str, body_html: str) -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"/></head>
<body style="margin:0;padding:0;background:#f3f6f4;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:28px 12px;">
    <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">
      <tr><td style="background:{_BRAND};padding:22px 28px;">
        <p style="margin:0;color:#fff;font-size:1.05rem;font-weight:700;">Department of Government Chemist</p>
        <p style="margin:4px 0 0;color:rgba(255,255,255,0.75);font-size:0.84rem;">Requests &amp; Approvals System</p>
      </td></tr>
      <tr><td style="padding:26px 28px 18px;">{body_html}</td></tr>
      <tr><td style="background:#f3f6f4;padding:13px 28px;">
        <p style="margin:0;color:#7a8c8c;font-size:0.81rem;">Automated notification — do not reply to this email.</p>
      </td></tr>
    </table>
  </td></tr></table>
</body></html>"""


def _row(label: str, value: str) -> str:
    return (
        f'<tr><td style="padding:6px 12px 6px 0;color:#536164;font-size:0.88rem;'
        f'white-space:nowrap;width:150px;vertical-align:top;">{label}</td>'
        f'<td style="padding:6px 0;color:#1f2a2a;font-size:0.88rem;">{value}</td></tr>'
    )


def _badge(status: str) -> str:
    COLORS: dict[str, tuple[str, str]] = {
        "Approved":  ("#d1fae5", "#065f46"),
        "Completed": ("#d1fae5", "#065f46"),
        "Delivered": ("#d1fae5", "#065f46"),
        "Declined":  ("#ffe4e6", "#9f1239"),
        "Cancelled": ("#fee2e2", "#b91c1c"),
        "Pending":   ("#fef3c7", "#92400e"),
        "In Transit":("#dbeafe", "#1e40af"),
    }
    bg, fg = COLORS.get(status, ("#e5e7eb", "#374151"))
    return (
        f'<span style="background:{bg};color:{fg};padding:3px 12px;'
        f'border-radius:999px;font-weight:700;font-size:0.85rem;">{status}</span>'
    )


def _send(to_list: list[str], subject: str, html: str) -> None:
    if not EMAIL_ENABLED:
        logger.info("Email globally disabled via EMAIL_ENABLED env var")
        return
    if not email_notifications_enabled():
        logger.info("Email disabled via admin toggle")
        return
    if not to_list:
        logger.info("Email skipped: recipient list is empty")
        return
    if not EMAIL_USER or not EMAIL_PASSWORD:
        logger.warning("Email skipped: EMAIL_USER or EMAIL_PASSWORD not configured")
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = ", ".join(to_list)
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(EMAIL_USER, EMAIL_PASSWORD)
            smtp.sendmail(EMAIL_USER, to_list, msg.as_string())
        logger.info("Email sent → %s | %s", to_list, subject)
    except Exception:
        logger.exception("Email send failed → %s | subject=%s", to_list, subject)


def send_email(to: "str | list[str]", subject: str, html: str) -> None:
    """Send an HTML email in the background. Silently drops invalid addresses."""
    if isinstance(to, str):
        to = [to]
    to = [t.strip() for t in to if t and "@" in t]
    if not to:
        logger.info("send_email: no valid recipients after filtering")
        return
    _pool.submit(_send, to, subject, html)


def send_test_email(to_addr: str) -> str:
    """Send a test email synchronously. Returns 'ok' or an error message."""
    if not EMAIL_USER or not EMAIL_PASSWORD:
        return "EMAIL_USER or EMAIL_PASSWORD not configured in environment."
    to_addr = to_addr.strip()
    if not to_addr or "@" not in to_addr:
        return "Invalid email address."
    subject = "DGC MRMS – Test Email"
    body = (
        '<h2 style="margin:0 0 6px;color:#0f5560;font-size:1.15rem;">'
        "Test Email Successful</h2>"
        '<p style="color:#536164;">If you are reading this, '
        "email notifications from the DGC Requests &amp; Approvals system "
        "are working correctly.</p>"
    )
    html = _base(subject, body)
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = to_addr
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(EMAIL_USER, EMAIL_PASSWORD)
            smtp.sendmail(EMAIL_USER, [to_addr], msg.as_string())
        return "ok"
    except Exception as exc:
        logger.exception("Test email failed → %s", to_addr)
        return str(exc)


# ── Meeting notifications ────────────────────────────────────────────────────

def notify_meeting_submitted(
    *,
    booking_id: str,
    requested_by: str,
    start_date,
    start_time,
    end_date,
    end_time,
    location: str,
    purpose: str,
    meeting_type: str,
    attendees: list[str],
    to_emails: list[str],
) -> None:
    subject = f"Meeting Request Submitted – {booking_id}"
    att_list = ", ".join(attendees) if attendees else "—"
    body = (
        f'<h2 style="margin:0 0 6px;color:{_BRAND};font-size:1.15rem;">Meeting Request Received</h2>'
        f'<p style="margin:0 0 18px;color:#536164;">Your request is pending admin approval.</p>'
        f'<table cellpadding="0" cellspacing="0" style="width:100%;border-top:1px solid #e5e7eb;">'
        + _row("Booking ID",   f"<strong>{booking_id}</strong>")
        + _row("Requested By", requested_by)
        + _row("Date",         f"{start_date} – {end_date}")
        + _row("Time",         f"{start_time} – {end_time}")
        + _row("Location",     location)
        + _row("Type",         meeting_type or "—")
        + _row("Purpose",      purpose or "—")
        + _row("Attendees",    att_list)
        + _row("Status",       _badge("Pending"))
        + "</table>"
        + '<p style="margin:18px 0 0;color:#536164;font-size:0.88rem;">'
          "You will receive another notification when the status is updated.</p>"
    )
    send_email(to_emails, subject, _base(subject, body))


def notify_meeting_status(
    *,
    booking_id: str,
    requested_by: str,
    status: str,
    start_date,
    start_time,
    end_date,
    end_time,
    location: str,
    to_emails: list[str],
) -> None:
    subject = f"Meeting Request {booking_id} – {status}"
    body = (
        f'<h2 style="margin:0 0 6px;color:{_BRAND};font-size:1.15rem;">Meeting Status Updated</h2>'
        f'<p style="margin:0 0 18px;color:#536164;">An admin has updated your meeting request.</p>'
        f'<table cellpadding="0" cellspacing="0" style="width:100%;border-top:1px solid #e5e7eb;">'
        + _row("Booking ID",   f"<strong>{booking_id}</strong>")
        + _row("Requested By", requested_by)
        + _row("Date",         f"{start_date} – {end_date}")
        + _row("Time",         f"{start_time} – {end_time}")
        + _row("Location",     location)
        + _row("New Status",   _badge(status))
        + "</table>"
    )
    send_email(to_emails, subject, _base(subject, body))


# ── Messenger notifications ──────────────────────────────────────────────────

def notify_messenger_submitted(
    *,
    request_id: str,
    requested_by: str,
    pickup_location: str,
    delivery_type: str,
    destination_name: str,
    destination_area: str,
    item_type: str,
    urgency_level: str,
    required_by_date,
    required_by_time,
    to_email: str | list[str],
) -> None:
    subject = f"Messenger Request Submitted – {request_id}"
    rbd = f"{required_by_date} {required_by_time}" if required_by_date else "—"
    dest = f"{destination_name} ({destination_area})" if destination_area else destination_name or "—"
    body = (
        f'<h2 style="margin:0 0 6px;color:{_BRAND};font-size:1.15rem;">Messenger Request Received</h2>'
        f'<p style="margin:0 0 18px;color:#536164;">Your request is pending admin approval.</p>'
        f'<table cellpadding="0" cellspacing="0" style="width:100%;border-top:1px solid #e5e7eb;">'
        + _row("Request ID",      f"<strong>{request_id}</strong>")
        + _row("Requested By",    requested_by)
        + _row("Pickup Location", pickup_location or "—")
        + _row("Delivery Type",   delivery_type or "—")
        + _row("Destination",     dest)
        + _row("Item Type",       item_type or "—")
        + _row("Urgency",         urgency_level)
        + _row("Required By",     rbd)
        + _row("Status",          _badge("Pending"))
        + "</table>"
        + '<p style="margin:18px 0 0;color:#536164;font-size:0.88rem;">'
          "You will receive another notification when the status is updated.</p>"
    )
    send_email(to_email, subject, _base(subject, body))


def notify_messenger_status(
    *,
    request_id: str,
    requested_by: str,
    status: str,
    destination_name: str,
    destination_area: str,
    to_email: str | list[str],
) -> None:
    subject = f"Messenger Request {request_id} – {status}"
    dest = f"{destination_name} ({destination_area})" if destination_area else destination_name or "—"
    body = (
        f'<h2 style="margin:0 0 6px;color:{_BRAND};font-size:1.15rem;">Messenger Status Updated</h2>'
        f'<p style="margin:0 0 18px;color:#536164;">An admin has updated your messenger request.</p>'
        f'<table cellpadding="0" cellspacing="0" style="width:100%;border-top:1px solid #e5e7eb;">'
        + _row("Request ID",   f"<strong>{request_id}</strong>")
        + _row("Requested By", requested_by)
        + _row("Destination",  dest)
        + _row("New Status",   _badge(status))
        + "</table>"
    )
    send_email(to_email, subject, _base(subject, body))
