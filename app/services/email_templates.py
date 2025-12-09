"""
HTML email templates for report delivery.
The templates reuse a single gradient theme and embed per-report summaries.
"""

from __future__ import annotations

from typing import Iterable


BASE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 760px;
            margin: 0 auto;
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
        .summary-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        .summary-table th, .summary-table td {{
            padding: 10px;
            text-align: left;
        }}
        .summary-table th {{
            background-color: #f0f7ff;
            color: #438efc;
        }}
        .summary-table tr:nth-child(even) {{
            background-color: #fafafa;
        }}
        .footer {{
            background-color: #f8f9fa;
            padding: 20px;
            text-align: center;
            font-size: 12px;
            color: #666666;
            border-top: 1px solid #e0e0e0;
        }}
        .badge {{
            background-color: #438efc;
            color: #ffffff;
            padding: 6px 10px;
            border-radius: 5px;
            font-weight: 600;
            display: inline-block;
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
            <div class="greeting">Dear {recipient},</div>
            <div class="message">{body}</div>
            {summary_block}
            <div class="message"><strong>Next steps:</strong> Download attached report for full details.</div>
        </div>
        <div class="footer">
            <p>⚠️ Please do not reply to this email.</p>
            <p>This is an automated notification from HTI AI AGENT system.</p>
            <p class="badge">{report_name}</p>
        </div>
    </div>
</body>
</html>
"""


def _build_summary_table(rows: Iterable[tuple[str, str]]) -> str:
    if not rows:
        return ""
    table_rows = "".join(
        f"<tr><th>{key}</th><td>{value}</td></tr>" for key, value in rows
    )
    return f"""
    <table class="summary-table">
        <tbody>
            {table_rows}
        </tbody>
    </table>
    """


def render_job_overview_email(recipient: str, summary: dict) -> str:
    rows = [(k, v) for k, v in (summary or {}).items()]
    return BASE_TEMPLATE.format(
        title="Jobs Overview Report",
        recipient=recipient,
        body="This is a system generated jobs overview summary. The full report (PDF/XLSX) is attached.",
        summary_block=_build_summary_table(rows),
        report_name="Jobs Overview",
    )


def render_job_funnel_email(recipient: str, summary: dict) -> str:
    rows = [
        ("Sourced", summary.get("sourced", 0)),
        ("Screened", summary.get("screened", 0)),
        ("Offers/Joins", summary.get("offers", 0)),
        ("Join ratio", summary.get("join_ratio", 0)),
    ]
    return BASE_TEMPLATE.format(
        title="Job Funnel Report",
        recipient=recipient,
        body="Here is the requested job funnel snapshot.",
        summary_block=_build_summary_table(rows),
        report_name="Job Funnel",
    )


def render_job_details_email(recipient: str, summary: dict) -> str:
    rows = [(k, v) for k, v in (summary or {}).items()]
    return BASE_TEMPLATE.format(
        title="Job Details Report",
        recipient=recipient,
        body="This is a system generated job details report. Please review the attachment for full metrics, charts, and candidate details.",
        summary_block=_build_summary_table(rows),
        report_name="Job Details",
    )


def render_recruiter_email(recipient: str, summary: dict) -> str:
    rows = [
        ("Total recruiters", summary.get("total_recruiters", 0)),
        ("Total sourced", summary.get("total_sourced", 0)),
        ("Total screened", summary.get("total_screened", 0)),
        ("Total logins", summary.get("total_logins", 0)),
    ]
    return BASE_TEMPLATE.format(
        title="Recruiter Performance Report",
        recipient=recipient,
        body="Login activity has been included alongside performance metrics.",
        summary_block=_build_summary_table(rows),
        report_name="Recruiter Performance",
    )


def render_pipeline_email(recipient: str, summary: dict, title: str) -> str:
    rows = [
        ("Stages observed", summary.get("stages", 0)),
        ("Avg hours", summary.get("avg_hours", 0)),
        ("Median hours", summary.get("p50_hours", 0)),
        ("P90 hours", summary.get("p90_hours", 0)),
    ]
    return BASE_TEMPLATE.format(
        title=title,
        recipient=recipient,
        body="Pipeline health snapshot is attached for review.",
        summary_block=_build_summary_table(rows),
        report_name=title,
    )


def render_clawback_email(recipient: str, summary: dict) -> str:
    rows = [
        ("Cases tracked", summary.get("cases", 0)),
        ("Recovered", summary.get("recovered", 0)),
        ("Pending", summary.get("pending", 0)),
    ]
    return BASE_TEMPLATE.format(
        title="Clawback Overview",
        recipient=recipient,
        body="Clawback report is attached. Values are based on current availability.",
        summary_block=_build_summary_table(rows),
        report_name="Clawback Overview",
    )

