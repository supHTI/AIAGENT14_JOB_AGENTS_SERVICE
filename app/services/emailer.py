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
        to_email = "shivamkgupta135@gmail.com"
        if not all([self.smtp_server, self.smtp_email, self.smtp_password]):
            logger.warning(f"SMTP configuration is incomplete. Email not sent. to={to_email} from={self.smtp_email}")
            return False

        # msg = self._build_message(to_email, subject, html_content, attachments)
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

    def send_cooling_period_reminder(
        self,
        to_email: str,
        recipient_name: str,
        candidates: list[dict],
    ) -> bool:
        """Send email with cooling period reminders for multiple candidates"""
        # Build candidate rows HTML
        candidate_rows = ""
        for idx, candidate in enumerate(candidates, 1):
            remaining_days = candidate.get('cooling_period_remaining_days', 'N/A')
            status_color = "#28a745" if remaining_days and remaining_days > 30 else "#ffc107" if remaining_days and remaining_days > 7 else "#dc3545"
            
            candidate_rows += f"""
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #e0e0e0;">{idx}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e0e0e0;"><strong>{candidate.get('candidate_name', 'N/A')}</strong></td>
                <td style="padding: 12px; border-bottom: 1px solid #e0e0e0;">{candidate.get('candidate_email', 'N/A')}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e0e0e0;">{candidate.get('candidate_phone_number', 'N/A')}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e0e0e0;">
                    <span style="background-color: {status_color}; color: white; padding: 4px 8px; border-radius: 4px; font-weight: 600;">
                        {remaining_days} days
                    </span>
                </td>
            </tr>
            """
        
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cooling Period Reminder</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 900px;
            margin: 20px auto;
            background-color: #ffffff;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}
        .header {{
            background: linear-gradient(90deg, #438efc, #7558e6 47.4%, #be08c7);
            padding: 30px 20px;
            text-align: center;
            color: #ffffff;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
            font-weight: 600;
        }}
        .content {{
            padding: 30px 20px;
            color: #333333;
        }}
        .greeting {{
            font-size: 18px;
            color: #438efc;
            margin-bottom: 20px;
        }}
        .message {{
            font-size: 16px;
            line-height: 1.6;
            color: #555555;
            margin-bottom: 25px;
        }}
        .candidate-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }}
        .candidate-table th {{
            background-color: #438efc;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}
        .candidate-table td {{
            padding: 12px;
            border-bottom: 1px solid #e0e0e0;
        }}
        .candidate-table tr:hover {{
            background-color: #f8f9fa;
        }}
        .footer {{
            background-color: #f8f9fa;
            padding: 20px;
            text-align: center;
            font-size: 12px;
            color: #666666;
            border-top: 1px solid #e0e0e0;
        }}
        .info-box {{
            background-color: #e7f3ff;
            border-left: 4px solid #438efc;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>HTI AI AGENT</h1>
            <p style="margin: 5px 0 0 0; font-size: 14px;">High Tech Infosystems</p>
        </div>
        <div class="content">
            <div class="greeting">Dear {recipient_name},</div>
            <div class="message">
                This is a reminder about candidates in their cooling period that you are managing. 
                Please review the following candidates and their remaining cooling period days:
            </div>
            
            <div class="info-box">
                <strong>📋 Total Candidates:</strong> {len(candidates)}
            </div>
            
            <table class="candidate-table">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Candidate Name</th>
                        <th>Email</th>
                        <th>Phone Number</th>
                        <th>Cooling Period Remaining</th>
                    </tr>
                </thead>
                <tbody>
                    {candidate_rows}
                </tbody>
            </table>
            
            <div class="message">
                Please ensure timely follow-up with these candidates as their cooling period progresses.
            </div>
        </div>
        <div class="footer">
            <p>This is an automated reminder from HTI AI Agent System</p>
            <p>&copy; 2024 High Tech Infosystems. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
        """
        
        subject = f"Cooling Period Reminder - {len(candidates)} Candidate(s) Assigned to You"
        return self._send_email(to_email, subject, html_content)


def send_report_email(subject: str, html_body: str, to_email: str, attachments: Iterable[Attachment] = ()):
    """
    Backward-compatible helper for report emails.
    """
    service = EmailService()
    return service._send_email(to_email, subject, html_body, attachments)