"""Email alert sender for SentinelCare critical alerts via SMTP."""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

logger = logging.getLogger("sentinelcare.email")
last_email_error = ""

# Load .env file from backend directory
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


class EmailConfig:
    """SMTP configuration loaded from environment variables."""

    def __init__(self) -> None:
        self.smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user: str = os.getenv("SMTP_USER", "")
        self.smtp_password: str = os.getenv("SMTP_PASSWORD", "")
        self.from_email: str = os.getenv("SMTP_FROM", self.smtp_user)
        self.from_name: str = os.getenv("SMTP_FROM_NAME", "SentinelCare Alert System")

    @property
    def is_configured(self) -> bool:
        return bool(self.smtp_user and self.smtp_password)


# Singleton config — reads env vars once at import time
email_config = EmailConfig()


def send_alert_email(
    to_emails: list[str],
    alert_type: str,
    severity: str,
    timestamp: str,
    location: str = "",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    nearest_hospital: Optional[dict] = None,
    summary: str = "",
    recommended_action: str = "",
) -> bool:
    """Send a critical alert email to the given recipients.

    Returns True if the email was sent successfully, False otherwise.
    Fails silently (logs error) so it never blocks the vision loop.
    """
    global last_email_error
    last_email_error = ""

    if not email_config.is_configured:
        last_email_error = "SMTP_USER and SMTP_PASSWORD are not configured."
        logger.warning("SMTP not configured — skipping email alert. Set SMTP_USER and SMTP_PASSWORD env vars.")
        return False

    if not to_emails:
        last_email_error = "No recipient emails provided."
        logger.info("No recipient emails provided — skipping email alert.")
        return False

    subject = f"SentinelCare CRITICAL ALERT — {alert_type}"

    # ---- Build plain-text body ----
    lines = [
        "SENTINELCARE EMERGENCY ALERT",
        "=" * 40,
        "",
        f"Event:       {alert_type}",
        f"Severity:    {severity.upper()}",
        f"Detected at: {timestamp}",
    ]

    if location:
        lines.append(f"Location:    {location}")
    if latitude is not None and longitude is not None:
        lines.append(f"Map:         https://www.google.com/maps?q={latitude},{longitude}")

    if summary:
        lines.append("")
        lines.append(f"Summary:     {summary}")
    if recommended_action:
        lines.append(f"Action:      {recommended_action}")

    if nearest_hospital:
        lines.append("")
        lines.append("NEAREST HOSPITAL REFERENCE")
        lines.append("=" * 40)
        lines.append("SentinelCare did not contact this hospital. This is responder reference information only.")
        lines.append(f"Name:        {nearest_hospital.get('name', 'Unknown')}")
        lines.append(f"Address:     {nearest_hospital.get('address', 'Unknown')}")
        if nearest_hospital.get("phone"):
            lines.append(f"Phone:       {nearest_hospital['phone']}")
        if nearest_hospital.get("distance") is not None:
            lines.append(f"Distance:    {nearest_hospital['distance']} mi")
        if latitude is not None and longitude is not None and nearest_hospital.get("address"):
            directions = (
                f"https://www.google.com/maps/dir/{latitude},{longitude}/"
                f"{nearest_hospital['address'].replace(' ', '+')}"
            )
            lines.append(f"Directions:  {directions}")

    lines.append("")
    lines.append("=" * 40)
    lines.append("This alert was generated automatically by SentinelCare.")
    lines.append("Please check on the person immediately or call emergency services.")

    body_text = "\n".join(lines)

    # ---- Build HTML body ----
    map_link = ""
    if latitude is not None and longitude is not None:
        map_url = f"https://www.google.com/maps?q={latitude},{longitude}"
        map_link = f'<a href="{map_url}" style="color:#06b6d4;">View on Google Maps</a>'

    hospital_html = ""
    if nearest_hospital:
        h_name = nearest_hospital.get("name", "Unknown")
        h_addr = nearest_hospital.get("address", "Unknown")
        h_phone = nearest_hospital.get("phone", "")
        h_dist = nearest_hospital.get("distance", "")
        hospital_html = f"""
        <tr><td colspan="2" style="padding:12px 0 4px 0;font-weight:bold;color:#06b6d4;font-size:14px;">
            Nearest Hospital Reference
        </td></tr>
        <tr><td colspan="2" style="color:#facc15;padding:2px 0 6px 0;font-size:12px;">
            SentinelCare did not contact this hospital. This is responder reference information only.
        </td></tr>
        <tr><td style="color:#94a3b8;padding:2px 12px 2px 0;">Name</td><td style="color:#f1f5f9;">{h_name}</td></tr>
        <tr><td style="color:#94a3b8;padding:2px 12px 2px 0;">Address</td><td style="color:#f1f5f9;">{h_addr}</td></tr>
        {"<tr><td style='color:#94a3b8;padding:2px 12px 2px 0;'>Phone</td><td style='color:#f1f5f9;'>" + h_phone + "</td></tr>" if h_phone else ""}
        {"<tr><td style='color:#94a3b8;padding:2px 12px 2px 0;'>Distance</td><td style='color:#f1f5f9;'>" + str(h_dist) + " mi</td></tr>" if h_dist else ""}
        """

    body_html = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;background:#0f172a;border:1px solid #ef4444;border-radius:12px;overflow:hidden;">
        <div style="background:#7f1d1d;padding:20px 24px;">
            <h1 style="margin:0;color:#fca5a5;font-size:20px;">🚨 CRITICAL ALERT</h1>
            <p style="margin:4px 0 0;color:#fecaca;font-size:14px;">{alert_type} Detected</p>
        </div>
        <div style="padding:20px 24px;">
            <table style="width:100%;font-size:13px;border-collapse:collapse;">
                <tr><td style="color:#94a3b8;padding:4px 12px 4px 0;width:100px;">Event</td><td style="color:#f1f5f9;font-weight:600;">{alert_type}</td></tr>
                <tr><td style="color:#94a3b8;padding:4px 12px 4px 0;">Severity</td><td style="color:#ef4444;font-weight:600;">{severity.upper()}</td></tr>
                <tr><td style="color:#94a3b8;padding:4px 12px 4px 0;">Time</td><td style="color:#f1f5f9;">{timestamp}</td></tr>
                {"<tr><td style='color:#94a3b8;padding:4px 12px 4px 0;'>Location</td><td style='color:#f1f5f9;'>" + location + "</td></tr>" if location else ""}
                {"<tr><td style='color:#94a3b8;padding:4px 12px 4px 0;'>Map</td><td>" + map_link + "</td></tr>" if map_link else ""}
                {hospital_html}
            </table>
            {"<p style='margin:16px 0 0;padding:12px;background:#1e293b;border-radius:8px;color:#e2e8f0;font-size:13px;'>" + summary + "</p>" if summary else ""}
            {"<p style='margin:8px 0 0;padding:12px;background:#7f1d1d33;border:1px solid #ef444433;border-radius:8px;color:#fca5a5;font-size:13px;font-weight:600;'>" + recommended_action + "</p>" if recommended_action else ""}
        </div>
        <div style="padding:12px 24px;background:#1e293b;font-size:11px;color:#64748b;">
            Sent automatically by SentinelCare · AI Home Safety Monitor
        </div>
    </div>
    """

    try:
        for recipient in to_emails:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{email_config.from_name} <{email_config.from_email}>"
            msg["To"] = recipient

            msg.attach(MIMEText(body_text, "plain"))
            msg.attach(MIMEText(body_html, "html"))

            with smtplib.SMTP(email_config.smtp_host, email_config.smtp_port) as server:
                server.starttls()
                server.login(email_config.smtp_user, email_config.smtp_password)
                server.sendmail(email_config.from_email, [recipient], msg.as_string())

            logger.info(f"Alert email sent to: {recipient}")

        logger.info(f"Alert emails sent to {len(to_emails)} recipient(s): {', '.join(to_emails)}")
        return True

    except Exception as e:
        last_email_error = str(e)
        logger.error(f"Failed to send alert email: {e}", exc_info=True)
        return False
