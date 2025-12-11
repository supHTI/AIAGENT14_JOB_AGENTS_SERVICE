"""
Email Service Module

This module handles sending emails for job assignments and notifications.
"""

from __future__ import annotations

import logging
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Iterable, Tuple

from app.core import settings

logger = logging.getLogger("app_logger")

Attachment = Tuple[str, bytes, str]  # filename, content, mime_type


class EmailService:
    """Service for sending emails"""

    def __init__(self):
        self.smtp_server = settings.SMTP_SERVER
        self.smtp_port = int(settings.SMTP_PORT) if getattr(settings, "SMTP_PORT", None) else 587
        self.smtp_email = settings.SMTP_EMAIL
        self.smtp_password = settings.SMTP_PASSWORD
        self.use_tls = getattr(settings, "SMTP_USE_TLS", True)

    def _load_template(self, template_name: str) -> str:
        """Load HTML template from templates folder"""
        template_path = Path(__file__).parent.parent / "templates" / "emails" / f"{template_name}.html"
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()

    def _build_message(self, to_email: str, subject: str, html_content: str, attachments: Iterable[Attachment]) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.smtp_email or settings.REPORT_EMAIL_FROM
        msg["To"] = to_email

        # Add HTML content
        html_part = MIMEText(html_content, "html")
        msg.attach(html_part)

        # Add attachments
        for filename, content, mime_type in attachments or []:
            maintype, subtype = mime_type.split("/", 1)
            part = MIMEBase(maintype, subtype)
            part.set_payload(content)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(part)

        return msg

    def _send_email(self, to_email: str, subject: str, html_content: str, attachments: Iterable[Attachment] = ()) -> bool:
        """Send email using SMTP"""
        if not all([self.smtp_server, self.smtp_email, self.smtp_password]):
            logger.warning(f"SMTP configuration is incomplete. Email not sent. to={to_email} from={self.smtp_email}")
            return False

        msg = self._build_message(to_email, subject, html_content, attachments)

        try:
            logger.info(f"Sending email to {to_email} via {self.smtp_email}@{self.smtp_server}:{self.smtp_port}")
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.smtp_email, self.smtp_password)
                server.send_message(msg)
            logger.info(f"Email sent successfully to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Error sending email to {to_email}: {str(e)}")
            return False

    def send_job_assigned_email(
        self,
        to_email: str,
        recipient_name: str,
        job_id: str,
        job_title: str,
        company_name: str,
        location: str,
        deadline: str,
        job_type: str,
    ) -> bool:
        """Send email when a job is assigned to an internal SPOC"""
        template = self._load_template("job_assigned")
        html_content = template.format(
            recipient_name=recipient_name,
            job_id=job_id,
            job_title=job_title,
            company_name=company_name,
            location=location,
            deadline=deadline,
            job_type=job_type,
        )
        subject = f"Job Assignment: {job_title} - {job_id}"
        return self._send_email(to_email, subject, html_content)


def send_report_email(subject: str, html_body: str, to_email: str, attachments: Iterable[Attachment] = ()):
    """
    Backward-compatible helper for report emails.
    """
    service = EmailService()
    return service._send_email(to_email, subject, html_body, attachments)