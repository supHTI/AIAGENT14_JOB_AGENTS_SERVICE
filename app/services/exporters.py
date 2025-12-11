""" 
Export utilities for XLSX and PDF generation with richer layouts.
JSON/CSV outputs were removed to keep delivery focused on shareable formats.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Dict, List, Mapping, Tuple

import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def _safe_dataframe(items: List[Mapping]):
    return pd.DataFrame(items or [])


def export_xlsx(items: List[Mapping]) -> bytes:
    df = _safe_dataframe(items)
    with io.BytesIO() as buffer:
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False)
        return buffer.getvalue()


def export_multi_sheet_xlsx(sheets: Dict[str, List[Mapping]]) -> bytes:
    """
    Export multiple logical sections into separate sheets.
    Each sheet name is truncated to 28 chars to stay Excel-safe.
    """
    with io.BytesIO() as buffer:
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            for name, rows in (sheets or {}).items():
                safe_name = (name or "Sheet")[:28]
                df = _safe_dataframe(rows)
                df.to_excel(writer, sheet_name=safe_name, index=False)
        return buffer.getvalue()


def _build_chart_image(items: List[Mapping], x_key: str, y_key: str) -> bytes:
    if not items:
        return b""
    x = [str(i.get(x_key, "")) for i in items][:10]
    y = [i.get(y_key, 0) or 0 for i in items][:10]
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.bar(x, y, color="#438efc")
    ax.set_xlabel(x_key.replace("_", " ").title())
    ax.set_ylabel(y_key.replace("_", " ").title())
    ax.set_title(f"{y_key.replace('_', ' ').title()} by {x_key.replace('_', ' ').title()}")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format="png")
    plt.close(fig)
    return img_buffer.getvalue()


def export_pdf(title: str, summary: Mapping, items: List[Mapping], x_key: str = "title", y_key: str = "openings") -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    c.setTitle(title)

    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, height - 50, title)
    c.setFont("Helvetica", 10)
    c.drawString(40, height - 70, f"Generated at: {datetime.utcnow().isoformat()}")

    # Summary block
    y_pos = height - 100
    for key, val in (summary or {}).items():
        c.drawString(40, y_pos, f"{key.replace('_', ' ').title()}: {val}")
        y_pos -= 14

    # Chart
    chart = _build_chart_image(items, x_key, y_key)
    if chart:
        img = ImageReader(io.BytesIO(chart))
        c.drawImage(img, 40, y_pos - 220, width=520, height=200, preserveAspectRatio=True, anchor="nw")
        y_pos -= 240

    # Table header
    headers = list(items[0].keys()) if items else []
    if headers:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(40, y_pos, "Top records")
        y_pos -= 12
        c.setFont("Helvetica", 8)
        max_rows = 12
        for row in items[:max_rows]:
            row_text = " | ".join(f"{h}: {row.get(h)}" for h in headers[:5])
            c.drawString(40, y_pos, row_text[:150])
            y_pos -= 12

    c.showPage()
    c.save()
    return buffer.getvalue()


def _draw_header_footer(c: canvas.Canvas, title: str, subtitle: str = ""):
    width, height = letter
    c.setFillColor(colors.HexColor("#0f172a"))
    c.rect(0, height - 90, width, 90, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(40, height - 55, title)
    c.setFont("Helvetica", 10)
    footer_text = subtitle or "System generated report • Please do not reply"
    c.drawString(40, 30, footer_text)
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.line(40, 45, width - 40, 45)


def _draw_tiles(c: canvas.Canvas, tiles: List[Tuple[str, str]], y_start: float):
    """
    Render simple statistic tiles in two columns.
    """
    width, _ = letter
    x = 40
    box_width = (width - 100) / 2
    y = y_start
    colors_cycle = ["#2563eb", "#0ea5e9", "#10b981", "#f59e0b", "#a855f7", "#ef4444"]
    for idx, (label, value) in enumerate(tiles):
        c.setFillColor(colors.HexColor(colors_cycle[idx % len(colors_cycle)]))
        c.roundRect(x, y - 40, box_width, 36, 6, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x + 10, y - 18, label)
        c.setFont("Helvetica", 13)
        c.drawRightString(x + box_width - 10, y - 18, str(value))
        if x + box_width * 2 + 20 <= width:
            x += box_width + 20
        else:
            x = 40
            y -= 48
    return y - 10


def _draw_chart(c: canvas.Canvas, y_pos: float, img_bytes: bytes, caption: str):
    if not img_bytes:
        return y_pos
    width, _ = letter
    img = ImageReader(io.BytesIO(img_bytes))
    c.drawImage(img, 40, y_pos - 180, width=width - 80, height=160, preserveAspectRatio=True, anchor="nw")
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y_pos - 190, caption)
    return y_pos - 200


def export_jobs_overview_pdf(
    title: str,
    summary_tiles: List[Tuple[str, str]],
    positions_at_risk: List[Mapping],
    charts: Mapping[str, List[Mapping]],
    table_rows: List[Mapping],
) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    c.setTitle(title)

    _draw_header_footer(c, title, "System generated report • Jobs overview")
    y = height - 110
    c.setFillColor(colors.HexColor("#475569"))
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Generated at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    y -= 20

    # Summary tiles
    y = _draw_tiles(c, summary_tiles, y)

    # Charts
    job_company_chart = _build_chart_image(charts.get("jobs_per_company", []), "name", "jobs")
    y = _draw_chart(c, y, job_company_chart, "Jobs per company")
    new_jobs_chart = _build_chart_image(charts.get("new_jobs_daily", []), "label", "count")
    y = _draw_chart(c, y, new_jobs_chart, "New jobs created (timeline)")

    # Positions at risk section
    if positions_at_risk:
        if y < 180:
            c.showPage()
            _draw_header_footer(c, title, "System generated report • Jobs overview")
            y = height - 110
        c.setFillColor(colors.HexColor("#0f172a"))
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, "Positions at risk (> threshold days)")
        y -= 16
        c.setFont("Helvetica", 9)
        for row in positions_at_risk[:12]:
            txt = f"{row.get('job_id')} • {row.get('title')} • {row.get('aging_days')} days open"
            c.drawString(40, y, txt[:120])
            y -= 12

    # Job table preview
    if table_rows:
        if y < 120:
            c.showPage()
            _draw_header_footer(c, title, "System generated report • Jobs overview")
            y = height - 110
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, "Job snapshot")
        y -= 16
        headers = ["Job", "Company", "Status", "Openings", "Candidates"]
        c.setFont("Helvetica-Bold", 9)
        c.drawString(40, y, " | ".join(headers))
        y -= 12
        c.setFont("Helvetica", 9)
        for row in table_rows[:14]:
            line = f"{row.get('job_public_id')} {row.get('title')} | {row.get('company_name','-')} | {row.get('status')} | {row.get('openings')} | {row.get('candidate_count')}"
            c.drawString(40, y, line[:140])
            y -= 12

    c.showPage()
    c.save()
    return buffer.getvalue()


def export_job_details_pdf(
    title: str,
    summary_tiles: List[Tuple[str, str]],
    stage_flow: List[Mapping],
    stage_times: List[Mapping],
    hr_activities: List[Mapping],
    candidate_rows: List[Mapping],
    funnel: Mapping,
    extras: Mapping,
) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    c.setTitle(title)

    _draw_header_footer(c, title, "System generated report • Job details")
    y = height - 110
    c.setFillColor(colors.HexColor("#475569"))
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Generated at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    y -= 20

    y = _draw_tiles(c, summary_tiles, y)

    if funnel:
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(40, y, "Pipeline funnel")
        y -= 14
        c.setFont("Helvetica", 9)
        funnel_line = f"Sourced: {funnel.get('sourced',0)} • Screened: {funnel.get('screened',0)} • Offers: {funnel.get('offers',0)} • Joins: {funnel.get('joins',0)} (Join ratio {funnel.get('join_ratio',0)})"
        c.drawString(40, y, funnel_line[:150])
        y -= 18

    if stage_flow:
        flow_chart = _build_chart_image(stage_flow, "stage_name", "candidates")
        y = _draw_chart(c, y, flow_chart, "Pipeline stage distribution")

    if stage_times:
        time_chart = _build_chart_image(stage_times, "stage_name", "avg_hours")
        y = _draw_chart(c, y, time_chart, "Time spent per stage (avg hours)")

    if hr_activities:
        if y < 140:
            c.showPage()
            _draw_header_footer(c, title, "System generated report • Job details")
            y = height - 110
        c.setFont("Helvetica-Bold", 11)
        c.drawString(40, y, "HR activity summary")
        y -= 14
        c.setFont("Helvetica", 9)
        for row in hr_activities[:12]:
            c.drawString(40, y, f"{row.get('user_name','HR')} • {row.get('activity_type','-')} : {row.get('count',0)}")
            y -= 12

    if candidate_rows:
        if y < 140:
            c.showPage()
            _draw_header_footer(c, title, "System generated report • Job details")
            y = height - 110
        c.setFont("Helvetica-Bold", 11)
        c.drawString(40, y, "Candidate details by stage")
        y -= 14
        c.setFont("Helvetica", 8)
        for row in candidate_rows[:18]:
            line = f"{row.get('candidate_name','N/A')} ({row.get('candidate_phone_number','-')}) • Stage: {row.get('stage_name','-')} • Status: {row.get('status','-')}"
            c.drawString(40, y, line[:160])
            y -= 11

    if extras:
        if y < 120:
            c.showPage()
            _draw_header_footer(c, title, "System generated report • Job details")
            y = height - 110
        c.setFont("Helvetica-Bold", 11)
        c.drawString(40, y, "Other insights")
        y -= 14
        c.setFont("Helvetica", 9)
        for key, val in extras.items():
            c.drawString(40, y, f"{key.replace('_',' ').title()}: {val}")
            y -= 12

    c.showPage()
    c.save()
    return buffer.getvalue()


def export_with_format(
    fmt: str,
    title: str,
    summary: Mapping,
    items: List[Mapping],
    x_key: str = "title",
    y_key: str = "openings",
) -> Tuple[bytes, str, str]:
    fmt_lower = fmt.lower()
    if fmt_lower == "xlsx":
        data = export_xlsx(items)
        return data, f"{title.replace(' ', '_').lower()}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if fmt_lower == "pdf":
        data = export_pdf(title, summary, items, x_key=x_key, y_key=y_key)
        return data, f"{title.replace(' ', '_').lower()}.pdf", "application/pdf"
    raise ValueError(f"Unsupported export format: {fmt}")

