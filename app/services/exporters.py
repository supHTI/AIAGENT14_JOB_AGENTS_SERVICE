""" 
Export utilities for XLSX and PDF generation with richer layouts.
JSON/CSV outputs were removed to keep delivery focused on shareable formats.
"""

from __future__ import annotations

import io
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Mapping, Tuple

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import matplotlib.dates as mdates
import seaborn as sns
from matplotlib.figure import Figure
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from app.core import settings
import os

# Use a clean, dashboard-like style for charts
sns.set_theme(style="whitegrid")

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


def _build_company_bar_chart(items: List[Mapping]) -> bytes:
    if not items:
        return b""
    
    # Sort and take top 10
    items = sorted(items, key=lambda x: x.get("jobs", 0), reverse=True)[:10]
    
    names = []
    values = []
    for i in items:
        name = i.get("name", "Unknown")
        # Truncate logic
        if len(name) > 10:
            name = name[:10] + "..."
        names.append(name)
        values.append(i.get("jobs", 0))

    fig = plt.figure(figsize=(6, 4))
    ax = fig.add_subplot(111)
    
    # Grid
    ax.grid(axis='y', linestyle='--', alpha=0.5, zorder=0)

    # Distinct colors
    colors_list = sns.color_palette("husl", len(items))

    # Shadow effect (draw offset bars first)
    offset = 0.05
    for i, (n, v) in enumerate(zip(names, values)):
        # Shadow
        ax.bar(i + offset, v, color='gray', alpha=0.3, width=0.6, zorder=2)
        # Main bar
        ax.bar(i, v, color=colors_list[i], width=0.6, zorder=3, label=n)

    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=45, ha='right', fontsize=9)
    ax.set_ylabel("No of Jobs")
    ax.set_title("Job Openings per Company", pad=20, fontweight='bold', fontsize=11)
    ax.set_ylim(bottom=0)
    
    plt.tight_layout()
    
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format="png", dpi=100)
    plt.close(fig)
    return img_buffer.getvalue()


def _build_timeline_chart(items: List[Mapping], date_range: Tuple[date, date] = (None, None)) -> bytes:
    if not items:
        return b""
        
    df = pd.DataFrame(items)
    if "label" not in df.columns or "count" not in df.columns:
        return b"" # Safety check

    df["dt"] = pd.to_datetime(df["label"])
    df.set_index("dt", inplace=True)
    df.sort_index(inplace=True)
    
    # Resample logic
    start, end = date_range
    total_days = 365 # Default
    if start and end:
         total_days = (end - start).days
    
    if total_days <= 30:
        rule = 'D' # Daily
        marker = 'o'
    elif total_days <= 90:
        rule = 'W' # Weekly
        marker = 's'
    else:
        rule = 'M' # Monthly
        marker = '^'
        
    resampled = df.resample(rule)["count"].sum().fillna(0)
    
    fig = plt.figure(figsize=(6, 4))
    ax = fig.add_subplot(111)
    
    ax.grid(True, linestyle='--', alpha=0.5)
    
    ax.plot(resampled.index, resampled.values, marker=marker, color='#2563eb', linewidth=2, markersize=6)
    
    # Format x-axis
    if total_days <= 90:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    else:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        
    fig.autofmt_xdate()
    
    ax.set_ylabel("New Jobs")
    ax.set_title(f"New Jobs Created (Interval: {rule})", pad=20, fontweight='bold', fontsize=11)
    ax.set_ylim(bottom=0)
    
    plt.tight_layout()
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format="png", dpi=100)
    plt.close(fig)
    return img_buffer.getvalue()

def _build_line_chart_by_title(items: List[Mapping], title: str, x_key: str = "title", y_key: str = "count") -> bytes:
    if not items:
        return b""
        
    # Take top 10
    top_items = items[:10]
    
    names = []
    values = []
    for i in top_items:
        name = str(i.get(x_key, "Unknown"))
        if len(name) > 10:
            name = name[:10] + "..."
        names.append(name)
        values.append(i.get(y_key, 0))
        
    fig = plt.figure(figsize=(6, 4))
    ax = fig.add_subplot(111)
    
    ax.grid(True, linestyle='--', alpha=0.5)
    
    ax.plot(names, values, marker='D', color='#f59e0b', linewidth=2, markersize=6)
    
    ax.set_xticklabels(names, rotation=45, ha='right', fontsize=9)
    ax.set_ylabel("Count")
    ax.set_title(title, pad=20, fontweight='bold', fontsize=11)
    ax.set_ylim(bottom=0)
    
    plt.tight_layout()
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format="png", dpi=100)
    plt.close(fig)
    return img_buffer.getvalue()

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
    
    # Header Background
    c.setFillColor(colors.HexColor("#0f172a"))
    c.rect(0, height - 90, width, 90, fill=1, stroke=0)
    
    # Header Text
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    
    title_x = 40
    # Include Logo (Left)
    if settings.LOGO_PATH and os.path.exists(settings.LOGO_PATH):
        try:
             # Basic check to avoid crashes
             img = ImageReader(settings.LOGO_PATH)
             c.drawImage(img, 40, height - 70, width=50, height=50, preserveAspectRatio=True, mask='auto', anchor="w")
             title_x = 100 # Shift title
        except Exception:
             pass
             
    c.drawString(title_x, height - 45, title)
    
    # Subtitle
    c.setFont("Helvetica", 10)
    c.drawString(title_x, height - 75, subtitle) # Adjusted Y to be visible inside blue rect
    
    # Footer
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.black)
    
    # Footer Lines
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.line(40, 40, width - 40, 40)
    
    # Footer Text 
    # Left: System Generated
    c.drawString(40, 25, "System Generated PDF")
    
    # Right: All Rights Reserved
    right_text = "All Rights Reserved with High Tech Infosystems Pvt Ltd"
    c.drawRightString(width - 40, 25, right_text)
    
    # Center: Page Number
    page_num_text = f"Page {c.getPageNumber()}"
    c.drawCentredString(width / 2, 25, page_num_text)


def _draw_tiles(c: canvas.Canvas, tiles: List[Tuple[str, str]], y_start: float) -> float:
    """
    Render statistic tiles in 5 columns (square style).
    """
    width, _ = letter
    margin = 40
    cols = 5
    # Smaller footprint tiles with tighter text fit
    gap = 18
    box_width = (width - (2 * margin) - ((cols - 1) * gap)) / cols
    box_height = min(box_width * 0.65, 68)  # shorter tiles
    
    x = margin
    y = y_start
    
    colors_cycle = ["#2563eb", "#0ea5e9", "#10b981", "#f59e0b", "#a855f7", "#ef4444"]
    
    # Draw logic
    for idx, (label, value) in enumerate(tiles):
        tile_color = colors.HexColor(colors_cycle[idx % len(colors_cycle)])
        
        # Check if we need a new row (though user asked for 1 row, we handle overflow just in case)
        if x + box_width > width - margin:
             x = margin
             y -= (box_height + gap + 20)

        # Shadow
        c.setFillColor(colors.HexColor("#cbd5e1"))
        c.roundRect(x + 3, y - box_height - 3, box_width, box_height, 8, fill=1, stroke=0)
        
        # Main Box
        c.setFillColor(tile_color)
        c.roundRect(x, y - box_height, box_width, box_height, 8, fill=1, stroke=0)
        
        # Text
        c.setFillColor(colors.white)
        
        # Label (Top Center-ish) - handle long labels
        c.setFont("Helvetica-Bold", 8)
        # Truncate long labels to stay inside box
        label_trim = (label[:18] + "...") if len(label) > 21 else label
        c.drawCentredString(x + box_width/2, y - 18, label_trim)
        
        # Value (Center) - smaller font for Deadline
        if label == "Deadline":
            c.setFont("Helvetica-Bold", 11)
        else:
            c.setFont("Helvetica-Bold", 14)
        value_str = str(value)
        value_trim = (value_str[:12] + "...") if len(value_str) > 15 else value_str
        c.drawCentredString(x + box_width/2, y - box_height/2 - 2, value_trim)
        
        x += box_width + gap
        
    # Divider line below tiles
    final_y = y - box_height - 30
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.setLineWidth(1)
    c.line(margin, final_y + 15, width - margin, final_y + 15)
            
    return final_y


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


def _draw_pipeline_funnel_graph(
    c: canvas.Canvas,
    y_pos: float,
    stage_flow: List[Mapping],
    joined_count: int,
    rejected_count: int,
) -> float:
    """
    Draw a bar graph for pipeline funnel with stages, joined, and rejected.
    Full width of the page with grid, values above bars, and truncated labels.
    """
    width, _ = letter
    margin = 40
    chart_width = width - (2 * margin)
    chart_height = 250
    bar_width = 30
    bar_gap = 15
    
    # Calculate positions
    x_start = margin
    y_bottom = y_pos - chart_height
    y_top = y_pos - 40  # Space for header
    
    # Get all data
    all_stages = stage_flow or []
    total_items = len(all_stages)
    
    # Calculate max value for Y-axis
    max_value = 0
    for stage in all_stages:
        max_value = max(max_value, stage.get("candidates", 0))
    max_value = max(max_value, joined_count, rejected_count)
    max_value = max(max_value, 1)  # At least 1 to avoid division by zero
    
    # Y-axis scaling
    y_range = y_top - y_bottom
    y_scale = y_range / max_value if max_value > 0 else y_range
    
    # Draw header
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_start, y_pos - 20, "Pipeline Funnel")
    y_pos -= 35
    
    # Draw grid lines
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.setLineWidth(0.5)
    grid_lines = 5
    for i in range(grid_lines + 1):
        y_grid = y_bottom + (i * y_range / grid_lines)
        c.line(x_start, y_grid, x_start + chart_width, y_grid)
        # Y-axis labels (0 at bottom, max at top)
        value = (i * max_value / grid_lines)
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.black)
        c.drawRightString(x_start - 5, y_grid - 3, str(int(value)))
    
    # Calculate bar positions - dynamically size to use available width
    desired_slot = chart_width / max(total_items, 1)
    bar_width = min(40, max(12, desired_slot * 0.6))
    bar_gap = min(30, max(6, desired_slot * 0.4))
    total_bar_width = (total_items * bar_width) + ((total_items - 1) * bar_gap)
    if total_bar_width > chart_width:
        scale = chart_width / total_bar_width
        bar_width = max(10, bar_width * scale)
        bar_gap = max(4, bar_gap * scale)
        total_bar_width = (total_items * bar_width) + ((total_items - 1) * bar_gap)
    x_offset = max((chart_width - total_bar_width) / 2, 0)
    
    # Draw bars for stages
    x_current = x_start + x_offset
    for stage in all_stages:
        stage_name = stage.get("stage_name", "Unknown")
        count = stage.get("candidates", 0)
        color_code = stage.get("color_code", "#2563eb")
        
        # Ensure color_code is valid
        if not color_code or not isinstance(color_code, str):
            color_code = "#2563eb"
        color_code = str(color_code).strip()
        if not color_code.startswith("#"):
            color_code = "#" + color_code
        
        # Truncate stage name
        max_name_len = 12
        if len(stage_name) > max_name_len:
            stage_name = stage_name[:max_name_len - 3] + "..."
        
        # Draw bar with error handling for invalid colors
        bar_height = count * y_scale
        try:
            c.setFillColor(colors.HexColor(color_code))
        except (ValueError, AttributeError):
            # Fallback to default blue if color is invalid
            c.setFillColor(colors.HexColor("#2563eb"))
        c.rect(x_current, y_bottom, bar_width, bar_height, fill=1, stroke=0)
        
        # Draw value above bar
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(colors.black)
        value_y = y_bottom + bar_height + 5
        c.drawCentredString(x_current + bar_width/2, value_y, str(count))
        
        # Draw label below (rotate if many items)
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.black)
        if total_items > 8:
            c.saveState()
            c.translate(x_current + bar_width/2, y_bottom - 18)
            c.rotate(-45)
            c.drawString(0, 0, stage_name)
            c.restoreState()
        else:
            c.drawCentredString(x_current + bar_width/2, y_bottom - 12, stage_name)
        
        x_current += bar_width + bar_gap
    
    # # Draw Joined bar (green)
    # joined_bar_height = joined_count * y_scale
    # c.setFillColor(colors.HexColor("#10b981"))  # Green
    # c.rect(x_current, y_bottom, bar_width, joined_bar_height, fill=1, stroke=0)
    
    # # Value above Joined bar
    # c.setFont("Helvetica-Bold", 9)
    # c.setFillColor(colors.black)
    # joined_value_y = y_bottom + joined_bar_height + 5
    # c.drawCentredString(x_current + bar_width/2, joined_value_y, str(joined_count))
    
    # # Label below
    # c.setFont("Helvetica", 8)
    # c.setFillColor(colors.black)
    # c.drawCentredString(x_current + bar_width/2, y_bottom - 15, "Joined")
    
    # x_current += bar_width + bar_gap
    
    # # Draw Rejected bar (red)
    # rejected_bar_height = rejected_count * y_scale
    # c.setFillColor(colors.HexColor("#ef4444"))  # Red
    # c.rect(x_current, y_bottom, bar_width, rejected_bar_height, fill=1, stroke=0)
    
    # # Value above Rejected bar
    # c.setFont("Helvetica-Bold", 9)
    # c.setFillColor(colors.black)
    # rejected_value_y = y_bottom + rejected_bar_height + 5
    # c.drawCentredString(x_current + bar_width/2, rejected_value_y, str(rejected_count))
    
    # # Label below
    # c.setFont("Helvetica", 8)
    # c.setFillColor(colors.black)
    # c.drawCentredString(x_current + bar_width/2, y_bottom - 15, "Rejected")
    
    # Draw Y-axis line
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(x_start, y_bottom, x_start, y_top)
    
    # Draw X-axis line
    c.line(x_start, y_bottom, x_start + chart_width, y_bottom)
    
    # Return new Y position (below graph)
    final_y = y_bottom - 30
    
    return final_y - 20


def _draw_avg_time_line_graph(
    c: canvas.Canvas,
    y_pos: float,
    stage_times: List[Mapping],
    avg_accepted_days: float,
    avg_rejected_days: float,
    chart_width: float,
    chart_height: float,
    x_start: float = 40,
    is_daily_report: bool = False,
) -> float:
    """
    Draw a line graph showing average time in days/hours for each pipeline stage, Accepted, and Rejected.
    For daily reports, values are in hours; for regular reports, values are in days.
    """
    y_bottom = y_pos - chart_height
    y_top = y_pos - 40
    
    # Prepare data: stages + Accepted + Rejected
    all_labels = []
    all_values = []
    
    # Add stages
    for stage in (stage_times or []):
        stage_name = stage.get("stage_name", "Unknown")
        # Truncate stage name more aggressively to avoid overlap
        max_len = 8  # Reduced from 10 to prevent overlap
        if len(stage_name) > max_len:
            stage_name = stage_name[:max_len - 3] + "..."
        all_labels.append(stage_name)
        all_values.append(stage.get("avg_days", 0))
    
    # Add Accepted and Rejected
    all_labels.append("Joined")
    all_values.append(avg_accepted_days)
    all_labels.append("Rejected")
    all_values.append(avg_rejected_days)
    
    # Always show graph, even if no data (show empty graph)
    if not all_labels or not any(all_values):
        # Draw empty graph with axes
        y_bottom = y_pos - chart_height
        y_top = y_pos - 40
        c.setStrokeColor(colors.black)
        c.setLineWidth(1)
        c.line(x_start, y_bottom, x_start, y_top)
        c.line(x_start, y_bottom, x_start + chart_width, y_bottom)
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#666666"))
        c.drawCentredString(x_start + chart_width / 2, y_bottom - 20, "No data available")
        return y_bottom - 30
    
    # Calculate max value for Y-axis
    max_value = max(all_values) if all_values else 1
    max_value = max(max_value, 1)  # At least 1
    
    # Y-axis scaling
    y_range = y_top - y_bottom
    y_scale = y_range / max_value if max_value > 0 else y_range
    
    # Draw grid lines
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.setLineWidth(0.5)
    grid_lines = 5
    for i in range(grid_lines + 1):
        y_grid = y_bottom + (i * y_range / grid_lines)
        c.line(x_start, y_grid, x_start + chart_width, y_grid)
        # Y-axis labels
        value = (i * max_value / grid_lines)
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.black)
        c.drawRightString(x_start - 5, y_grid - 3, f"{value:.1f}")
    
    # Calculate X positions
    num_points = len(all_labels)
    x_spacing = chart_width / max(num_points - 1, 1)
    
    # Draw line
    c.setStrokeColor(colors.HexColor("#2563eb"))
    c.setLineWidth(2)
    points = []
    for i, value in enumerate(all_values):
        x = x_start + (i * x_spacing)
        y = y_bottom + (value * y_scale)
        points.append((x, y))
        # Draw marker
        c.setFillColor(colors.HexColor("#2563eb"))
        c.circle(x, y, 3, fill=1, stroke=0)
        # Draw value above point
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.black)
        c.drawCentredString(x, y + 8, f"{value:.1f}")
    
    # Draw line connecting points
    if len(points) > 1:
        for i in range(len(points) - 1):
            c.line(points[i][0], points[i][1], points[i+1][0], points[i+1][1])
    
    # Draw X-axis labels (with rotation if too many points to avoid overlap)
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.black)
    for i, label in enumerate(all_labels):
        x = x_start + (i * x_spacing)
        # Rotate labels if too many points or if labels are long
        if num_points > 8 or any(len(l) > 6 for l in all_labels):
            # Rotate text to prevent overlap
            c.saveState()
            c.translate(x, y_bottom - 20)
            c.rotate(-45)
            c.drawString(0, 0, label)
            c.restoreState()
        else:
            c.drawCentredString(x, y_bottom - 15, label)
    
    # Draw Y-axis line
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(x_start, y_bottom, x_start, y_top)
    
    # Draw X-axis line
    c.line(x_start, y_bottom, x_start + chart_width, y_bottom)
    
    return y_bottom - 30


def _draw_velocity_line_graph(
    c: canvas.Canvas,
    y_pos: float,
    velocity_data: List[Mapping],
    chart_width: float,
    chart_height: float,
    x_start: float = 40,
    is_daily_report: bool = False,
) -> float:
    """
    Draw a line graph showing pipeline velocity (movement per day/hour).
    For daily reports, shows hourly data; for regular reports, shows daily data.
    """
    y_bottom = y_pos - chart_height
    y_top = y_pos - 40
    
    # Always show graph, even if no data (show empty graph)
    if not velocity_data:
        c.setStrokeColor(colors.black)
        c.setLineWidth(1)
        c.line(x_start, y_bottom, x_start, y_top)
        c.line(x_start, y_bottom, x_start + chart_width, y_bottom)
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#666666"))
        c.drawCentredString(x_start + chart_width / 2, y_bottom - 20, "No data available")
        return y_bottom - 30
    
    # Sort by label (date or hour)
    # For proper sorting, we need to handle different label formats
    def sort_key(item):
        label = item.get("label", "")
        # For hourly labels (HH:00), sort by hour number
        if ":" in label:
            try:
                hour = int(label.split(":")[0])
                return (0, hour)  # Type 0 for hourly
            except:
                return (1, label)  # Type 1 for others
        # For date labels (DD-MM), sort by date
        elif "-" in label and len(label) == 5:  # DD-MM format
            try:
                parts = label.split("-")
                day, month = int(parts[0]), int(parts[1])
                return (1, month, day)  # Type 1, sort by month then day
            except:
                return (2, label)  # Type 2 for others
        else:
            return (2, label)
    
    sorted_data = sorted(velocity_data, key=sort_key)
    
    # Prepare labels and values (already limited to max 15 by data generation)
    labels = []
    values = []
    for item in sorted_data:
        label = item.get("label", "")
        labels.append(label)
        values.append(item.get("moves", 0))
    
    # Calculate max value for Y-axis
    max_value = max(values) if values else 1
    max_value = max(max_value, 1)
    
    # Y-axis scaling
    y_range = y_top - y_bottom
    y_scale = y_range / max_value if max_value > 0 else y_range
    
    # Draw grid lines
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.setLineWidth(0.5)
    grid_lines = 5
    for i in range(grid_lines + 1):
        y_grid = y_bottom + (i * y_range / grid_lines)
        c.line(x_start, y_grid, x_start + chart_width, y_grid)
        # Y-axis labels
        value = (i * max_value / grid_lines)
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.black)
        c.drawRightString(x_start - 5, y_grid - 3, str(int(value)))
    
    # Calculate X positions
    num_points = len(labels)
    x_spacing = chart_width / max(num_points - 1, 1)
    
    # Draw line
    c.setStrokeColor(colors.HexColor("#10b981"))
    c.setLineWidth(2)
    points = []
    for i, value in enumerate(values):
        x = x_start + (i * x_spacing)
        y = y_bottom + (value * y_scale)
        points.append((x, y))
        # Draw marker
        c.setFillColor(colors.HexColor("#10b981"))
        c.circle(x, y, 3, fill=1, stroke=0)
        # Draw value above point
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.black)
        c.drawCentredString(x, y + 8, str(value))
    
    # Draw line connecting points
    if len(points) > 1:
        for i in range(len(points) - 1):
            c.line(points[i][0], points[i][1], points[i+1][0], points[i+1][1])
    
    # Draw X-axis labels
    # Data is already grouped to max 15 labels, so show all labels
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.black)
    
    # Always rotate labels if more than 8 points to prevent overlap
    if num_points > 8:
        # Rotate labels to prevent overlap
        for i, label in enumerate(labels):
            x = x_start + (i * x_spacing)
            c.saveState()
            c.translate(x, y_bottom - 25)
            c.rotate(-45)
            c.drawString(0, 0, label)
            c.restoreState()
    else:
        # Show all labels normally for 8 or fewer points
        for i, label in enumerate(labels):
            x = x_start + (i * x_spacing)
            c.drawCentredString(x, y_bottom - 15, label)
    
    # Draw Y-axis line
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(x_start, y_bottom, x_start, y_top)
    
    # Draw X-axis line
    c.line(x_start, y_bottom, x_start + chart_width, y_bottom)
    
    return y_bottom - 30


def _draw_pipeline_flow_graph(
    c: canvas.Canvas,
    y_pos: float,
    joined_data: List[Mapping],
    rejected_data: List[Mapping],
    chart_width: float,
    chart_height: float,
    x_start: float = 40,
) -> float:
    """
    Draw a dual-line graph for joined vs rejected/drop over time.
    """
    y_bottom = y_pos - chart_height
    y_top = y_pos - 40

    label_set = set()
    for d in joined_data or []:
        label_set.add(d.get("label"))
    for d in rejected_data or []:
        label_set.add(d.get("label"))
    labels = sorted(label_set)
    # Always show graph, even if no data
    if not labels:
        # Draw empty graph with axes
        c.setStrokeColor(colors.black)
        c.setLineWidth(1)
        c.line(x_start, y_bottom, x_start, y_top)
        c.line(x_start, y_bottom, x_start + chart_width, y_bottom)
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#666666"))
        c.drawCentredString(x_start + chart_width / 2, y_bottom - 20, "No data available")
        return y_bottom - 30

    joined_map = {d.get("label"): d.get("count", 0) for d in (joined_data or [])}
    rejected_map = {d.get("label"): d.get("count", 0) for d in (rejected_data or [])}
    joined_vals = [joined_map.get(lbl, 0) for lbl in labels]
    rejected_vals = [rejected_map.get(lbl, 0) for lbl in labels]

    max_value = max(joined_vals + rejected_vals) if (joined_vals or rejected_vals) else 1
    max_value = max(max_value, 1)

    y_range = y_top - y_bottom
    y_scale = y_range / max_value if max_value > 0 else y_range

    num_points = len(labels)
    x_spacing = chart_width / max(num_points - 1, 1)

    def _build_points(vals):
        pts = []
        for i, val in enumerate(vals):
            x = x_start + (i * x_spacing)
            y = y_bottom + (val * y_scale)
            pts.append((x, y, val))
        return pts

    joined_points = _build_points(joined_vals)
    rejected_points = _build_points(rejected_vals)

    # Grid
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.setLineWidth(0.5)
    for i in range(6):
        y_grid = y_bottom + (i * y_range / 5)
        c.line(x_start, y_grid, x_start + chart_width, y_grid)

    # Joined line (blue)
    c.setStrokeColor(colors.HexColor("#2563eb"))
    c.setFillColor(colors.HexColor("#2563eb"))
    c.setLineWidth(2)
    for i in range(len(joined_points) - 1):
        c.line(joined_points[i][0], joined_points[i][1], joined_points[i+1][0], joined_points[i+1][1])
    for x, y, val in joined_points:
        c.circle(x, y, 3, fill=1, stroke=0)
        c.setFont("Helvetica", 7)
        c.drawString(x - 3, y + 6, str(val))

    # Rejected line (red)
    c.setStrokeColor(colors.HexColor("#dc2626"))
    c.setFillColor(colors.HexColor("#dc2626"))
    c.setLineWidth(2)
    for i in range(len(rejected_points) - 1):
        c.line(rejected_points[i][0], rejected_points[i][1], rejected_points[i+1][0], rejected_points[i+1][1])
    for x, y, val in rejected_points:
        c.circle(x, y, 3, fill=1, stroke=0)
        c.setFont("Helvetica", 7)
        c.drawString(x - 3, y + 6, str(val))

    # X labels
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.black)
    for i, label in enumerate(labels):
        x = x_start + (i * x_spacing)
        c.drawCentredString(x, y_bottom - 15, str(label)[:10])

    # Axes
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(x_start, y_bottom, x_start, y_top)
    c.line(x_start, y_bottom, x_start + chart_width, y_bottom)
    
    return y_bottom - 30


def _draw_joined_datewise_graph(
    c: canvas.Canvas,
    y_pos: float,
    joined_datewise: List[Mapping],
    chart_width: float,
    chart_height: float,
    x_start: float = 40,
) -> float:
    """
    Draw a line graph showing total joined candidates datewise.
    Full width line graph with dates on X-axis and count on Y-axis.
    """
    y_bottom = y_pos - chart_height
    y_top = y_pos - 40
    
    if not joined_datewise:
        return y_pos
    
    # Sort by date
    sorted_data = sorted(joined_datewise, key=lambda x: x.get("label", ""))
    
    # Prepare labels and values
    labels = []
    values = []
    for item in sorted_data:
        label = item.get("label", "")
        # Format date label (e.g., "2024-01-15" -> "01-15" or "Jan 15")
        try:
            from datetime import datetime as dt
            date_obj = dt.strptime(label, "%Y-%m-%d")
            label = date_obj.strftime("%m-%d")  # Format as MM-DD
        except:
            # If parsing fails, use last 5 chars
            if len(label) > 5:
                label = label[-5:]
        labels.append(label)
        values.append(item.get("count", 0))
    
    # Calculate max value for Y-axis
    max_value = max(values) if values else 1
    max_value = max(max_value, 1)
    
    # Y-axis scaling
    y_range = y_top - y_bottom
    y_scale = y_range / max_value if max_value > 0 else y_range
    
    # Draw grid lines
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.setLineWidth(0.5)
    grid_lines = 5
    for i in range(grid_lines + 1):
        y_grid = y_bottom + (i * y_range / grid_lines)
        c.line(x_start, y_grid, x_start + chart_width, y_grid)
        # Y-axis labels
        value = (i * max_value / grid_lines)
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.black)
        c.drawRightString(x_start - 5, y_grid - 3, str(int(value)))
    
    # Calculate X positions
    num_points = len(labels)
    x_spacing = chart_width / max(num_points - 1, 1)
    
    # Draw line
    c.setStrokeColor(colors.HexColor("#10b981"))  # Green color for joined
    c.setLineWidth(2)
    points = []
    for i, value in enumerate(values):
        x = x_start + (i * x_spacing)
        y = y_bottom + (value * y_scale)
        points.append((x, y))
        # Draw marker
        c.setFillColor(colors.HexColor("#10b981"))
        c.circle(x, y, 3, fill=1, stroke=0)
        # Draw value above point
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.black)
        c.drawCentredString(x, y + 8, str(value))
    
    # Draw line connecting points
    if len(points) > 1:
        for i in range(len(points) - 1):
            c.line(points[i][0], points[i][1], points[i+1][0], points[i+1][1])
    
    # Draw X-axis labels (rotate if needed to avoid overlap)
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.black)
    for i, label in enumerate(labels):
        x = x_start + (i * x_spacing)
        # Rotate labels if too many points
        if num_points > 10:
            # Rotate text
            c.saveState()
            c.translate(x, y_bottom - 20)
            c.rotate(-45)
            c.drawString(0, 0, label)
            c.restoreState()
        else:
            c.drawCentredString(x, y_bottom - 15, label)
    
    # Draw Y-axis line
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(x_start, y_bottom, x_start, y_top)
    
    # Draw X-axis line
    c.line(x_start, y_bottom, x_start + chart_width, y_bottom)
    
    return y_bottom - 40  # Extra space for rotated labels


def _draw_recovery_line_graph(
    c: canvas.Canvas,
    y_pos: float,
    data: List[Mapping],
    chart_width: float,
    chart_height: float,
    x_start: float = 40,
) -> float:
    """
    Draw a simple line graph for recovery/pending values.
    """
    if not data:
        return y_pos

    y_bottom = y_pos - chart_height
    y_top = y_pos - 40

    labels = [str(d.get("label", "")) for d in data]
    values = [d.get("value", 0) or 0 for d in data]

    num_points = len(values)
    if num_points == 0:
        return y_pos

    max_value = max(values) if values else 1
    max_value = max(max_value, 1)

    y_range = y_top - y_bottom
    y_scale = y_range / max_value if max_value > 0 else y_range

    # X spacing
    x_spacing = chart_width / max(num_points - 1, 1)
    points = []
    for i, val in enumerate(values):
        x = x_start + (i * x_spacing)
        y = y_bottom + (val * y_scale)
        points.append((x, y))

    # Grid lines
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.setLineWidth(0.5)
    for i in range(6):
        y_grid = y_bottom + (i * y_range / 5)
        c.line(x_start, y_grid, x_start + chart_width, y_grid)

    # Draw lines
    c.setStrokeColor(colors.HexColor("#2563eb"))
    c.setLineWidth(2)
    for i in range(len(points) - 1):
        c.line(points[i][0], points[i][1], points[i+1][0], points[i+1][1])

    # Draw points
    c.setFillColor(colors.HexColor("#2563eb"))
    for x, y in points:
        c.circle(x, y, 3, fill=1, stroke=0)

    # Labels
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.black)
    for i, (x, y) in enumerate(points):
        c.drawString(x - 4, y + 6, str(values[i]))

    # X labels
    c.setFont("Helvetica", 7)
    for i, label in enumerate(labels):
        x = x_start + (i * x_spacing)
        c.drawCentredString(x, y_bottom - 15, label[:10])

    # Axes
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(x_start, y_bottom, x_start, y_top)
    c.line(x_start, y_bottom, x_start + chart_width, y_bottom)

    return y_bottom - 30


def _draw_recruiter_bar_graph(
    c: canvas.Canvas,
    y_pos: float,
    data: List[Mapping],
    value_key: str,
    y_label: str,
    chart_width: float,
    chart_height: float,
    x_start: float = 40,
) -> float:
    """
    Draw a bar graph for recruiter metrics (candidates per recruiter or rejected/dropped).
    """
    y_bottom = y_pos - chart_height
    y_top = y_pos - 40
    
    if not data:
        return y_pos
    
    # Take top items if too many
    display_data = data[:15]  # Limit to 15 for readability
    
    # Prepare labels and values
    labels = []
    values = []
    for item in display_data:
        name = item.get("recruiter_name", "Unknown")
        # Truncate name
        if len(name) > 15:
            name = name[:12] + "..."
        labels.append(name)
        values.append(item.get(value_key, 0))
    
    # Calculate max value for Y-axis
    max_value = max(values) if values else 1
    max_value = max(max_value, 1)
    
    # Y-axis scaling
    y_range = y_top - y_bottom
    y_scale = y_range / max_value if max_value > 0 else y_range
    
    # Draw grid lines
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.setLineWidth(0.5)
    grid_lines = 5
    for i in range(grid_lines + 1):
        y_grid = y_bottom + (i * y_range / grid_lines)
        c.line(x_start, y_grid, x_start + chart_width, y_grid)
        # Y-axis labels
        value = (i * max_value / grid_lines)
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.black)
        c.drawRightString(x_start - 5, y_grid - 3, str(int(value)))
    
    # Calculate bar positions
    num_bars = len(labels)
    bar_width = (chart_width - ((num_bars - 1) * 10)) / num_bars if num_bars > 0 else 20
    bar_width = min(bar_width, 40)  # Max bar width
    bar_gap = 10
    
    # Draw bars
    x_current = x_start
    colors_cycle = ["#2563eb", "#0ea5e9", "#10b981", "#f59e0b", "#a855f7", "#ef4444"]
    for i, (label, value) in enumerate(zip(labels, values)):
        bar_height = value * y_scale
        bar_color = colors.HexColor(colors_cycle[i % len(colors_cycle)])
        
        # Draw bar
        c.setFillColor(bar_color)
        c.rect(x_current, y_bottom, bar_width, bar_height, fill=1, stroke=0)
        
        # Draw value above bar
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.black)
        value_y = y_bottom + bar_height + 5
        c.drawCentredString(x_current + bar_width/2, value_y, str(value))
        
        # Draw label below (rotate if needed)
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.black)
        if num_bars > 8:
            # Rotate labels
            c.saveState()
            c.translate(x_current + bar_width/2, y_bottom - 20)
            c.rotate(-45)
            c.drawString(0, 0, label)
            c.restoreState()
        else:
            c.drawCentredString(x_current + bar_width/2, y_bottom - 15, label)
        
        x_current += bar_width + bar_gap
    
    # Draw Y-axis line
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(x_start, y_bottom, x_start, y_top)
    
    # Draw X-axis line
    c.line(x_start, y_bottom, x_start + chart_width, y_bottom)
    
    return y_bottom - 40


def export_jobs_overview_pdf(
    title: str,
    summary_tiles: List[Tuple[str, str]],
    positions_at_risk: List[Mapping],
    charts: Mapping[str, List[Mapping]],
    table_rows: List[Mapping],
    generated_by: str = "",
    date_range: Tuple[date, date] = (None, None),
) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    c.setTitle(title)

    # IST Conversion
    utc_now = datetime.utcnow()
    ist_now = utc_now + timedelta(hours=5, minutes=30)
    date_str = ist_now.strftime('%d-%b-%Y %I:%M %p IST')
    
    subtitle = f"Generated: {date_str}"
    
    # Date Range sub-text
    d_start, d_end = date_range
    if d_start and d_end:
        range_str = f"{d_start.strftime('%d %b %Y')} - {d_end.strftime('%d %b %Y')}"
    else:
        range_str = "All Time"
        
    subtitle += f" | Range: {range_str}"
    
    if generated_by:
        subtitle += f" | By: {generated_by}"

    _draw_header_footer(c, title, subtitle)
    y = height - 110

    # Summary tiles
    y = _draw_tiles(c, summary_tiles, y)

    # Charts Section
    # Side-by-side: Width approx 50% each
    chart_y = y - 20 # Gap
    
    # 1. Bar Chart
    job_company_chart = _build_company_bar_chart(charts.get("jobs_per_company", []))
    
    # 2. Line Chart
    new_jobs_chart = _build_timeline_chart(charts.get("new_jobs_daily", []), date_range)
    
    if job_company_chart or new_jobs_chart:
        # Draw images side-by-side
        # Available width = width - 2*margin
        # Each chart = ~45% width?
        chart_width = (width - 100) / 2
        chart_height = 200 # Fixed height
        
        if job_company_chart:
            img = ImageReader(io.BytesIO(job_company_chart))
            c.drawImage(img, 40, chart_y - chart_height, width=chart_width, height=chart_height, preserveAspectRatio=True, anchor="nw")
            
        if new_jobs_chart:
            img = ImageReader(io.BytesIO(new_jobs_chart))
            c.drawImage(img, width/2 + 10, chart_y - chart_height, width=chart_width, height=chart_height, preserveAspectRatio=True, anchor="nw")
            
        y = chart_y - chart_height - 20
        
        # Line Separator below first charts
        c.setStrokeColor(colors.HexColor("#e2e8f0"))
        c.line(40, y + 5, width - 40, y + 5)
        y -= 25 # Gap for next charts
        
        # --- Second Row Charts ---
        chart2_y = y - 20 
        
        # 3. Candidates per Job
        cand_job_chart = _build_line_chart_by_title(charts.get("candidates_per_job", []), "Candidates per Job", y_key="count")

        # 4. Clawback per Job
        clawback_job_chart = _build_line_chart_by_title(charts.get("clawback_per_job", []), "Clawback Cases (>Today) per Job", y_key="cases")
        
        if cand_job_chart or clawback_job_chart:
             if y < 220: # Ensure space for row 2
                  c.showPage()
                  _draw_header_footer(c, title, subtitle)
                  y = height - 110
                  chart2_y = y - 20
                  
             if cand_job_chart:
                 img = ImageReader(io.BytesIO(cand_job_chart))
                 c.drawImage(img, 40, chart2_y - chart_height, width=chart_width, height=chart_height, preserveAspectRatio=True, anchor="nw")
             
             if clawback_job_chart:
                 img = ImageReader(io.BytesIO(clawback_job_chart))
                 c.drawImage(img, width/2 + 10, chart2_y - chart_height, width=chart_width, height=chart_height, preserveAspectRatio=True, anchor="nw")
            
             y = chart2_y - chart_height - 20
             
             # Line Separator below second charts
             c.setStrokeColor(colors.HexColor("#e2e8f0"))
             c.line(40, y + 5, width - 40, y + 5)
             y -= 25

    # Move to a dedicated second page for tabular sections
    c.showPage()
    _draw_header_footer(c, title, subtitle)
    y = height - 110

    # --- Jobs at risk table ---
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Jobs at risk (deadline < 5 days)")
    y -= 18

    headers_risk = ["Job ID", "Job Title", "Company", "Openings", "Closed", "Deadline", "Days"]
    # Tighter widths to stay within page
    col_widths_risk = [130, 115, 95, 45, 45, 80, 60]
    x_start = 40

    c.setFont("Helvetica-Bold", 9)
    current_x = x_start
    for i, h in enumerate(headers_risk):
        c.drawString(current_x, y, h)
        current_x += col_widths_risk[i]

    y -= 10
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.line(40, y, width - 40, y)
    y -= 12
    c.setFont("Helvetica", 9)

    if positions_at_risk:
        for row in positions_at_risk:
            if y < 70:
                c.showPage()
                _draw_header_footer(c, title, subtitle)
                y = height - 110
                c.setFont("Helvetica-Bold", 12)
                c.drawString(40, y, "Jobs at risk (deadline < 5 days)")
                y -= 18
                c.setFont("Helvetica-Bold", 9)
                current_x = x_start
                for i, h in enumerate(headers_risk):
                    c.drawString(current_x, y, h)
                    current_x += col_widths_risk[i]
                y -= 10
                c.setStrokeColor(colors.HexColor("#e2e8f0"))
                c.line(40, y, width - 40, y)
                y -= 12
                c.setFont("Helvetica", 9)

            deadline = row.get("deadline")
            deadline_str = deadline.strftime("%Y-%m-%d") if isinstance(deadline, (date, datetime)) else str(deadline or "-")
            vals = [
                str(row.get("job_public_id", "")),
                (str(row.get("title", ""))[:18] + "...") if len(str(row.get("title", ""))) > 20 else str(row.get("title", "")),
                (str(row.get("company_name", ""))[:15] + "...") if len(str(row.get("company_name", ""))) > 17 else str(row.get("company_name", "")),
                str(row.get("openings", 0)),
                str(row.get("joined_count", 0)),
                deadline_str,
                str(row.get("days_remaining", "-")),
            ]
            current_x = x_start
            for i, v in enumerate(vals):
                c.drawString(current_x, y, v)
                current_x += col_widths_risk[i]
            y -= 14
    else:
        c.drawString(40, y, "No jobs meet the risk criteria.")
        y -= 14

    y -= 12
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.line(40, y, width - 40, y)
    y -= 22

    # --- Job Summary Table (with status) ---
    if table_rows:
        headers = ["Job ID", "Job Title", "Company Name", "Openings", "Closed", "Total Candidates"]
        
        if y < 170:
            c.showPage()
            _draw_header_footer(c, title, subtitle)
            y = height - 110
             
        c.setFillColor(colors.HexColor("#0f172a"))
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, "Job Summary Table")
        y -= 18
        
        c.setFont("Helvetica-Bold", 9)
        col_widths = [140, 120, 110, 55, 55, 80]
        x_start = 40
        
        current_x = x_start
        for i, h in enumerate(headers):
             c.drawString(current_x, y, h)
             current_x += col_widths[i]
             
        y -= 10
        c.setStrokeColor(colors.HexColor("#e2e8f0"))
        c.line(40, y, width - 40, y)
        y -= 12
        
        c.setFont("Helvetica", 9)
        
        for row in table_rows:
            if y < 60:
                c.showPage()
                _draw_header_footer(c, title, subtitle)
                y = height - 110
                c.setFillColor(colors.HexColor("#0f172a"))
                c.setFont("Helvetica-Bold", 12)
                c.drawString(40, y, "Job Summary Table")
                y -= 18
                c.setFont("Helvetica-Bold", 9)
                current_x = x_start
                for i, h in enumerate(headers):
                    c.drawString(current_x, y, h)
                    current_x += col_widths[i]
                y -= 10
                c.setStrokeColor(colors.HexColor("#e2e8f0"))
                c.line(40, y, width - 40, y)
                y -= 12
                c.setFont("Helvetica", 9)

            # Status dot at row start
            status_val = str(row.get("status", "")).lower()
            if status_val in {"active", "open"}:
                dot_color = colors.HexColor("#16a34a")  # green
            elif status_val == "inactive":
                dot_color = colors.HexColor("#eab308")  # yellow
            elif status_val == "closed":
                dot_color = colors.HexColor("#dc2626")  # red
            else:
                dot_color = colors.HexColor("#94a3b8")  # gray fallback
            c.setFillColor(dot_color)
            c.circle(x_start - 10, y + 3, 3, fill=1, stroke=0)

            vals = [
                str(row.get("job_public_id", "")),  # no truncation for Job ID
                (str(row.get("title", ""))[:20] + "...") if len(str(row.get("title", ""))) > 23 else str(row.get("title", "")),
                (str(row.get("company_name", ""))[:20] + "...") if len(str(row.get("company_name", ""))) > 23 else str(row.get("company_name", "")),
                str(row.get("openings", 0)),
                str(row.get("joined_count", 0)),
                str(row.get("candidate_count", 0)),
            ]
            
            current_x = x_start
            for i, v in enumerate(vals):
                 c.drawString(current_x, y, v)
                 current_x += col_widths[i]
            
            y -= 14

        y -= 18
        c.setStrokeColor(colors.HexColor("#000000"))
        c.setLineWidth(1)
        c.line(40, y, width - 40, y)
        y -= 14
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(width/2, y, "END OF REPORT")

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
    job_metadata: Mapping = None,
    generated_by: str = "",
    date_range: Tuple[date, date] = (None, None),
) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    c.setTitle(title)

    # Date Range sub-text (removed "Generated" date as requested)
    subtitle = ""
    d_start, d_end = date_range
    if d_start and d_end:
        range_str = f"{d_start.strftime('%d %b %Y')} - {d_end.strftime('%d %b %Y')}"
        subtitle = f"Range: {range_str}"
    else:
        subtitle = "All Time"
    
    if generated_by:
        subtitle += f" | By: {generated_by}"

    _draw_header_footer(c, title, subtitle)
    y = height - 110

    # Job info section (below header, above tiles)
    if job_metadata:
        # Job ID and Created By in top right corner (small, dark grey)
        job_id = job_metadata.get("job_id", "N/A")
        created_by = job_metadata.get("created_by", "N/A")
        c.setFillColor(colors.HexColor("#475569"))  # Dark grey
        c.setFont("Helvetica", 8)
        info_text = f"Job ID: {job_id} | Created By: {created_by}"
        c.drawRightString(width - 40, y, info_text)
        y -= 20
        
        c.setFillColor(colors.HexColor("#0f172a"))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(40, y, "Job Information")
        y -= 18
        
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.black)
        
        # Job Title (left) and Company Name (right) on same line
        job_title = job_metadata.get("job_title", "N/A")
        company_name = job_metadata.get("company_name", "N/A")
        c.drawString(40, y, f"Job Title: {job_title}")
        c.drawRightString(width - 40, y, f"Company Name: {company_name}")
        y -= 16
        
        # Job Creation Date (left) and Status (right) on same line
        created_at = job_metadata.get("created_at")
        if created_at:
            if isinstance(created_at, datetime):
                created_at_str = created_at.strftime("%d %b %Y")
            else:
                created_at_str = str(created_at)
        else:
            created_at_str = "N/A"
        status = job_metadata.get("status", "N/A")
        c.drawString(40, y, f"Job Creation Date: {created_at_str}")
        c.drawRightString(width - 40, y, f"Status: {status}")
        y -= 20
        
        # Line separator
        c.setStrokeColor(colors.HexColor("#e2e8f0"))
        c.setLineWidth(1)
        c.line(40, y, width - 40, y)
        y -= 20

    y = _draw_tiles(c, summary_tiles, y)

    # Draw Pipeline Funnel graph
    funnel_counts = extras.get("funnel_counts", {}) if extras else {}
    joined_count = funnel_counts.get("joined", 0)
    rejected_count = funnel_counts.get("rejected", 0)
    
    # Draw Pipeline Funnel graph (always show if pipeline stages exist)
    if stage_flow and len(stage_flow) > 0:
        y = _draw_pipeline_funnel_graph(c, y, stage_flow, joined_count, rejected_count)
        
        # Start new page for Pipeline Statistics section
        c.showPage()
        _draw_header_footer(c, title, subtitle)
        y = height - 110
        
        # Draw Pipeline Statistics section with two side-by-side graphs
        width, _ = letter
        margin = 40
        chart_width = (width - (3 * margin)) / 2  # Two charts with gap
        chart_height = 200
        
        # Section header
        c.setFillColor(colors.HexColor("#0f172a"))
        c.setFont("Helvetica-Bold", 12)
        c.drawString(margin, y, "Pipeline Statistics")
        y -= 30
        
        # Get data for graphs
        # stage_times is already a parameter, use it directly
        avg_times = extras.get("avg_times", {}) if extras else {}
        avg_accepted = avg_times.get("accepted_days", 0)
        avg_rejected = avg_times.get("rejected_days", 0)
        velocity_data = extras.get("pipeline_velocity", []) if extras else []
        
        # Detect graph type from extras
        graph_type = extras.get("graph_type", "daily") if extras else "daily"
        is_daily_report = extras.get("is_daily", False) if extras else False
        
        # Determine time unit and velocity title based on graph type
        if graph_type == "hourly":
            time_unit = "Hours"
            velocity_title = "Pipeline Velocity (Movement per Hour)"
        elif graph_type == "weekly":
            time_unit = "Days"
            velocity_title = "Pipeline Velocity (Movement per Week)"
        else:
            time_unit = "Days"
            velocity_title = "Pipeline Velocity (Movement per Day)"
        
        # Left graph: Avg Time per Stage
        graph_y = y
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, graph_y, f"Avg Time in Each Stage ({time_unit})")
        graph_y -= 15
        y_left = _draw_avg_time_line_graph(c, graph_y, stage_times, avg_accepted, avg_rejected, chart_width, chart_height, margin, is_daily_report=(graph_type == "hourly"))
        
        # Right graph: Pipeline Velocity
        x_right_start = margin + chart_width + margin
        graph_y = y
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(x_right_start, graph_y, velocity_title)
        graph_y -= 15
        y_right = _draw_velocity_line_graph(c, graph_y, velocity_data, chart_width, chart_height, x_right_start, is_daily_report=(graph_type == "hourly"))
        
        # Use the lower Y position
        y = min(y_left, y_right) - 20
        
        # Draw line after graphs
        c.setStrokeColor(colors.HexColor("#e2e8f0"))
        c.setLineWidth(1)
        c.line(margin, y, width - margin, y)
        y -= 30
        
        # Draw Pipeline Flow graph (Joined vs Rejected) - Always show, even if no data
        joined_datewise_data = extras.get("joined_datewise", []) if extras else []
        rejected_datewise_data = extras.get("rejected_datewise", []) if extras else []
        # Always show the graph, even if no data
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, y, "Pipeline Flow (Joined vs Rejected/Drop)")
        y -= 15
        full_chart_width = width - (2 * margin)
        y = _draw_pipeline_flow_graph(c, y, joined_datewise_data, rejected_datewise_data, full_chart_width, chart_height, margin)
        
        # Draw line after graph
        c.setStrokeColor(colors.HexColor("#e2e8f0"))
        c.setLineWidth(1)
        c.line(margin, y, width - margin, y)
        y -= 20

    # Draw Recruiter Metrics page (3rd page)
    recruiter_metrics = extras.get("recruiter_metrics", {}) if extras else {}
    # Always show recruiter metrics page if recruiter_metrics exists in extras
    if extras and "recruiter_metrics" in extras:
        c.showPage()
        _draw_header_footer(c, title, subtitle)
        y = height - 110
        
        # Heading
        c.setFillColor(colors.HexColor("#0f172a"))
        c.setFont("Helvetica-Bold", 18)
        c.drawString(margin, y, "Recruiter Metrics")
        y -= 48
        
        # Tiles
        top_name = recruiter_metrics.get("top_recruiter", {}).get("name", "N/A") or "N/A"
        # Insert line break if long
        if len(top_name) > 18:
            split_idx = len(top_name) // 2
            top_name = top_name[:split_idx] + "\n" + top_name[split_idx:]
        recruiter_tiles = [
            ("Total Recruiter", recruiter_metrics.get("total_recruiters", 0)),
            ("Active Recruiter", recruiter_metrics.get("active_recruiters", 0)),
            ("Inactive Recruiter", recruiter_metrics.get("inactive_recruiters", 0)),
        ]
        y = _draw_tiles(c, recruiter_tiles, y)
        
        # Best performer block
        y -= 10
        c.setStrokeColor(colors.HexColor("#e2e8f0"))
        c.setLineWidth(1)
        c.line(margin, y, width - margin, y)
        y -= 16
        c.setFillColor(colors.HexColor("#0f172a"))
        c.setFont("Helvetica-Bold", 12)
        c.drawString(margin, y, "Best Performer")
        y -= 14
        c.setFont("Helvetica-Bold", 11)
        c.drawString(margin, y, top_name)
        y -= 18
        
        # Top Recruiters Ranking Table
        top_recruiters = recruiter_metrics.get("top_recruiters_ranking", [])
        # Get recruiter_assignments from extras first (for daily report), then from recruiter_metrics
        recruiter_assignments = extras.get("recruiter_assignments") or recruiter_metrics.get("recruiter_assignments") or []
        assignment_map = {a.get("recruiter_name"): a for a in recruiter_assignments if a.get("recruiter_name")}
        if top_recruiters:
            y -= 20
            c.setFillColor(colors.HexColor("#0f172a"))
            c.setFont("Helvetica-Bold", 12)
            table_title = f"Ranking of Top {len(top_recruiters)} Recruiters"
            c.drawString(margin, y, table_title)
            y -= 25
            
            # Table header
            c.setFont("Helvetica-Bold", 10)
            c.drawString(margin, y, "Rank")
            c.drawString(margin + 60, y, "Recruiter Name")
            c.drawString(width - 210, y, "Total Candidates")
            c.drawString(width - 90, y, "No Of Closed")
            y -= 12
            c.setStrokeColor(colors.HexColor("#e2e8f0"))
            c.line(margin, y, width - margin, y)
            y -= 15
            
            # Table rows
            c.setFont("Helvetica", 9)
            for idx, recruiter in enumerate(top_recruiters, 1):
                if y < 80:
                    c.showPage()
                    _draw_header_footer(c, title, subtitle)
                    y = height - 110
                name = recruiter.get("recruiter_name", "N/A")
                # Truncate name if too long
                if len(name) > 30:
                    name = name[:27] + "..."
                closed = recruiter.get("closed_count", 0)
                c.drawString(margin, y, str(idx))
                c.drawString(margin + 60, y, name)
                # Get total candidates assigned for this recruiter (from recruiter_assignments)
                total_assigned = assignment_map.get(recruiter.get("recruiter_name")) or {}
                assigned_val = total_assigned.get("candidates", 0)
                c.drawString(width - 210, y, str(assigned_val))
                c.drawString(width - 90, y, str(closed))
                y -= 15
            
            y -= 10
            c.setStrokeColor(colors.HexColor("#e2e8f0"))
            c.line(margin, y, width - margin, y)
            y -= 20
        
        # Recruiter Details table
        if recruiter_assignments:
            if y < 180:
                c.showPage()
                _draw_header_footer(c, title, subtitle)
                y = height - 110
            
            # Check if this is a daily report or date range report (has tag_based_candidates_daily)
            # For date ranges, we also show tag-based candidate tables
            is_daily_report = extras.get("tag_based_candidates_daily") is not None
            
            c.setFillColor(colors.HexColor("#0f172a"))
            c.setFont("Helvetica-Bold", 12)
            c.drawString(margin, y, "Recruiter Details")
            y -= 18
            c.setFont("Helvetica-Bold", 9)
            
            if is_daily_report:
                # Daily report: include tag-based fields
                # Adjust widths to fit page (total width ~532 with margins, using smaller font)
                headers = ["Recruiter", "Candidates", "Sourced", "Screened", "Lined Up", "Turned Up", "Offer Accepted", "Joined", "Rejected", "Active"]
                col_widths = [85, 55, 42, 42, 42, 55, 70, 42, 45, 38]
            else:
                # Regular report: original headers
                headers = ["Recruiter", "Candidates", "Joined", "Rejected", "Active"]
                col_widths = [150, 80, 70, 110, 60]
            
            current_x = margin
            for w, h in zip(col_widths, headers):
                c.drawString(current_x, y, h)
                current_x += w
            y -= 10
            c.setStrokeColor(colors.HexColor("#e2e8f0"))
            c.line(margin, y, width - margin, y)
            y -= 12
            c.setFont("Helvetica", 8)  # Smaller font for more columns
            for row in recruiter_assignments:
                if y < 70:
                    c.showPage()
                    _draw_header_footer(c, title, subtitle)
                    y = height - 110
                    c.setFillColor(colors.HexColor("#0f172a"))
                    c.setFont("Helvetica-Bold", 12)
                    c.drawString(margin, y, "Recruiter Details")
                    y -= 18
                    c.setFont("Helvetica-Bold", 9)
                    current_x = margin
                    for w, h in zip(col_widths, headers):
                        c.drawString(current_x, y, h)
                        current_x += w
                    y -= 10
                    c.setStrokeColor(colors.HexColor("#e2e8f0"))
                    c.line(margin, y, width - margin, y)
                    y -= 12
                    c.setFont("Helvetica", 8)
                active_status = "Yes" if row.get("active", False) else "No"
                recruiter_name = row.get("recruiter_name", "N/A")
                # Truncate based on whether it's daily report (more columns = less space)
                max_len = 12 if is_daily_report else 20
                if len(recruiter_name) > max_len:
                    recruiter_name = recruiter_name[:max_len-3] + "..."
                
                if is_daily_report:
                    vals = [
                        recruiter_name,
                        str(row.get("candidates", 0)),
                        str(row.get("sourced", 0)),
                        str(row.get("screened", 0)),
                        str(row.get("lined_up", 0)),
                        str(row.get("turned_up", 0)),
                        str(row.get("offer_accepted", 0)),
                        str(row.get("joined", 0)),
                        str(row.get("rejected", 0)),
                        active_status,
                    ]
                else:
                    vals = [
                        recruiter_name,
                        str(row.get("candidates", 0)),
                        str(row.get("joined", 0)),
                        str(row.get("rejected", 0)),
                        active_status,
                    ]
                current_x = margin
                for w, v in zip(col_widths, vals):
                    c.drawString(current_x, y, v)
                    current_x += w
                y -= 12
            y -= 16
            c.setStrokeColor(colors.HexColor("#e2e8f0"))
            c.line(margin, y, width - margin, y)
            y -= 18
            
            # Add tag-based candidate detail tables (for daily reports and date ranges)
            tag_based_candidates = extras.get("tag_based_candidates_daily") or {}
            if tag_based_candidates:  # Show tables if we have tag-based candidate data
                tag_configs = [
                    ("sourced", "Sourced Candidates"),
                    ("screened", "Screened Candidates"),
                    ("lined_up", "Lined Up Candidates"),
                    ("turned_up", "Turned Up Candidates"),
                    ("offer_accepted", "Offer Accepted Candidates"),
                ]
                
                for tag_key, tag_title in tag_configs:
                    candidates_list = tag_based_candidates.get(tag_key, [])
                    # Always show the table, even if empty (to show structure)
                    if True:  # Always render the table
                        if y < 180:
                            c.showPage()
                            _draw_header_footer(c, title, subtitle)
                            y = height - 110
                        c.setFillColor(colors.HexColor("#0f172a"))
                        c.setFont("Helvetica-Bold", 12)
                        c.drawString(margin, y, tag_title)
                        y -= 18
                        c.setFont("Helvetica-Bold", 9)
                        detail_headers = ["Candidate ID", "Candidate Name", "HR Name", "Date & Time"]
                        # Adjusted widths to fit page: [80, 125, 95, 135] = 435 points (within 532 limit)
                        # Candidate ID gets 80 to prevent overlap, names can be cropped
                        detail_col_widths = [180, 125, 120, 135]
                        current_x = margin
                        for w, h in zip(detail_col_widths, detail_headers):
                            c.drawString(current_x, y, h)
                            current_x += w
                        y -= 10
                        c.setStrokeColor(colors.HexColor("#e2e8f0"))
                        c.line(margin, y, width - margin, y)
                        y -= 12
                        c.setFont("Helvetica", 8)  # Smaller font for better fit
                        if candidates_list:
                            for candidate in candidates_list:
                                if y < 70:
                                    c.showPage()
                                    _draw_header_footer(c, title, subtitle)
                                    y = height - 110
                                    c.setFillColor(colors.HexColor("#0f172a"))
                                    c.setFont("Helvetica-Bold", 12)
                                    c.drawString(margin, y, tag_title)
                                    y -= 18
                                    c.setFont("Helvetica-Bold", 9)
                                    current_x = margin
                                    for w, h in zip(detail_col_widths, detail_headers):
                                        c.drawString(current_x, y, h)
                                        current_x += w
                                    y -= 10
                                    c.setStrokeColor(colors.HexColor("#e2e8f0"))
                                    c.line(margin, y, width - margin, y)
                                    y -= 12
                                    c.setFont("Helvetica", 8)
                                # Get values and crop names if needed, but keep candidate_id intact
                                candidate_id_str = str(candidate.get("candidate_id", "N/A"))
                                candidate_name = candidate.get("candidate_name", "N/A")
                                hr_name = candidate.get("hr_name", "N/A")
                                date_time = candidate.get("created_at", "N/A")
                                
                                # Crop candidate name if too long (max ~17 chars for 125 width)
                                if len(candidate_name) > 17:
                                    candidate_name = candidate_name[:14] + "..."
                                
                                # Crop HR name if too long (max ~13 chars for 95 width)
                                if len(hr_name) > 13:
                                    hr_name = hr_name[:10] + "..."
                                
                                detail_vals = [
                                    candidate_id_str,  # Keep candidate_id intact, no cropping
                                    candidate_name,
                                    hr_name,
                                    date_time,
                                ]
                                current_x = margin
                                for w, v in zip(detail_col_widths, detail_vals):
                                    c.drawString(current_x, y, v)
                                    current_x += w
                                y -= 12
                        else:
                            # Show "No candidates" message if list is empty
                            c.setFont("Helvetica", 9)
                            c.setFillColor(colors.HexColor("#666666"))
                            c.drawString(margin, y, "No candidates found for this tag in the selected date range.")
                            y -= 14
                        y -= 16
                        c.setStrokeColor(colors.HexColor("#e2e8f0"))
                        c.line(margin, y, width - margin, y)
                        y -= 20

        # Clawback total cases graph removed per request
        
        # Candidates Per Recruiter Bar Graph
        candidates_per_recruiter = recruiter_metrics.get("candidates_per_recruiter", [])
        if candidates_per_recruiter and y > 250:
            c.setFont("Helvetica-Bold", 12)
            c.setFillColor(colors.HexColor("#0f172a"))
            c.drawString(margin, y, "Candidates Per Recruiter")
            y -= 20
            y = _draw_recruiter_bar_graph(c, y, candidates_per_recruiter, "candidate_count", "Candidates", width - (2 * margin), 200, margin)
            y -= 10
            c.setStrokeColor(colors.HexColor("#e2e8f0"))
            c.line(margin, y, width - margin, y)
            y -= 20
        elif candidates_per_recruiter:
            # Not enough space, go to next page
            c.showPage()
            _draw_header_footer(c, title, subtitle)
            y = height - 110
            c.setFont("Helvetica-Bold", 12)
            c.setFillColor(colors.HexColor("#0f172a"))
            c.drawString(margin, y, "Candidates Per Recruiter")
            y -= 20
            y = _draw_recruiter_bar_graph(c, y, candidates_per_recruiter, "candidate_count", "Candidates", width - (2 * margin), 200, margin)
            y -= 10
            c.setStrokeColor(colors.HexColor("#e2e8f0"))
            c.line(margin, y, width - margin, y)
            y -= 20
        
        # Rejected or Dropped by Recruiter Bar Graph
        rejected_dropped = recruiter_metrics.get("rejected_dropped_by_recruiter", [])
        if rejected_dropped and y > 250:
            c.setFont("Helvetica-Bold", 12)
            c.setFillColor(colors.HexColor("#0f172a"))
            c.drawString(margin, y, "Rejected or Dropped by Recruiter")
            y -= 20
            y = _draw_recruiter_bar_graph(c, y, rejected_dropped, "rejected_count", "Rejected/Dropped", width - (2 * margin), 200, margin)
        elif rejected_dropped:
            # Not enough space, go to next page
            c.showPage()
            _draw_header_footer(c, title, subtitle)
            y = height - 110
            c.setFont("Helvetica-Bold", 12)
            c.setFillColor(colors.HexColor("#0f172a"))
            c.drawString(margin, y, "Rejected or Dropped by Recruiter")
            y -= 20
            y = _draw_recruiter_bar_graph(c, y, rejected_dropped, "rejected_count", "Rejected/Dropped", width - (2 * margin), 200, margin)

    # --- Clawback Metrics page ---
    # Always show clawback metrics page, even if no data
    clawback_metrics = extras.get("clawback_metrics", {}) if extras else {}
    # Always show the page
    c.showPage()
    _draw_header_footer(c, title, subtitle)
    y = height - 110

    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin, y, "Clawback Metrics")
    y -= 48

    clawback_tiles = [
        ("Total Clawback Cases", clawback_metrics.get("total_cases", 0)),
        ("Clawback Completed", clawback_metrics.get("completed", 0)),
        ("Clawback Dropped", clawback_metrics.get("dropped", 0)),
        ("Clawback Pending", clawback_metrics.get("pending", 0)),
    ]
    y = _draw_tiles(c, clawback_tiles, y)

    # Recovery rate line graph (pending_vs_recovered kept for recovery vs pending/dropped)
    # Always show, even if no data
    pending_vs_rec = clawback_metrics.get("pending_vs_recovered", [])
    if pending_vs_rec:
        line_data = []
        for item in pending_vs_rec:
            label = item.get("label", "")
            value = item.get("value", 0)
            line_data.append({"label": label, "value": value})
        if line_data:
            if y < 260:
                c.showPage()
                _draw_header_footer(c, title, subtitle)
                y = height - 110
            c.setFont("Helvetica-Bold", 12)
            c.setFillColor(colors.HexColor("#0f172a"))
            c.drawString(margin, y, "Clawback Recovery Rate")
            y -= 20
            y = _draw_recovery_line_graph(c, y, line_data, width - (2 * margin), 180, margin)
            y -= 12
    else:
        # Show empty graph if no data
        if y < 260:
            c.showPage()
            _draw_header_footer(c, title, subtitle)
            y = height - 110
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, y, "Clawback Recovery Rate")
        y -= 20
        # Draw empty graph
        chart_width = width - (2 * margin)
        chart_height = 180
        y_bottom = y - chart_height
        y_top = y - 40
        c.setStrokeColor(colors.black)
        c.setLineWidth(1)
        c.line(margin, y_bottom, margin, y_top)
        c.line(margin, y_bottom, margin + chart_width, y_bottom)
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#666666"))
        c.drawCentredString(margin + chart_width / 2, y_bottom - 20, "No data available")
        y = y_bottom - 30

    # Clawback Completed Today table - Always show, even if no data
    completed_today = clawback_metrics.get("completed_today", [])
    if y < 180:
        c.showPage()
        _draw_header_footer(c, title, subtitle)
        y = height - 110
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, y, "Clawback Completed Today")
    y -= 18
    headers = ["Candidate", "Recruiter", "Joined On", "Completion Date"]
    col_widths = [150, 150, 100, 110]
    c.setFont("Helvetica-Bold", 9)
    current_x = margin
    for w, h in zip(col_widths, headers):
        c.drawString(current_x, y, h)
        current_x += w
    y -= 10
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.line(margin, y, width - margin, y)
    y -= 12
    c.setFont("Helvetica", 9)
    if completed_today:
            if y < 180:
                c.showPage()
                _draw_header_footer(c, title, subtitle)
                y = height - 110
            c.setFillColor(colors.HexColor("#0f172a"))
            c.setFont("Helvetica-Bold", 12)
            c.drawString(margin, y, "Clawback Completed Today")
            y -= 18
            headers = ["Candidate", "Recruiter", "Joined On", "Completion Date"]
            col_widths = [150, 150, 100, 110]
            c.setFont("Helvetica-Bold", 9)
            current_x = margin
            for w, h in zip(col_widths, headers):
                c.drawString(current_x, y, h)
                current_x += w
            y -= 10
            c.setStrokeColor(colors.HexColor("#e2e8f0"))
            c.line(margin, y, width - margin, y)
            y -= 12
            c.setFont("Helvetica", 9)
            for row in completed_today:
                if y < 60:
                    c.showPage()
                    _draw_header_footer(c, title, subtitle)
                    y = height - 110
                    c.setFillColor(colors.HexColor("#0f172a"))
                    c.setFont("Helvetica-Bold", 12)
                    c.drawString(margin, y, "Clawback Completed Today")
                    y -= 18
                    c.setFont("Helvetica-Bold", 9)
                    current_x = margin
                    for w, h in zip(col_widths, headers):
                        c.drawString(current_x, y, h)
                        current_x += w
                    y -= 10
                    c.setStrokeColor(colors.HexColor("#e2e8f0"))
                    c.line(margin, y, width - margin, y)
                    y -= 12
                    c.setFont("Helvetica", 9)
                vals = [
                    (row.get("candidate_name") or row.get("candidate_id", "N/A"))[:22],
                    (row.get("recruiter_name") or "N/A")[:22],
                    str(row.get("joined_on", "")),
                    str(row.get("completion_date", "")),
                ]
                current_x = margin
                for w, v in zip(col_widths, vals):
                    c.drawString(current_x, y, v)
                    current_x += w
                y -= 14
    else:
        c.drawString(margin, y, "No data available")
        y -= 14
    y -= 14

    # Clawback Drop or Rejected Today - Always show, even if no data
    drop_today = clawback_metrics.get("drop_today", [])
    if y < 160:
        c.showPage()
        _draw_header_footer(c, title, subtitle)
        y = height - 110
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, y, "Clawback Drop or Rejected Today")
    y -= 18
    headers = ["Candidate", "Status", "Date"]
    col_widths = [180, 140, 100]
    c.setFont("Helvetica-Bold", 9)
    current_x = margin
    for w, h in zip(col_widths, headers):
        c.drawString(current_x, y, h)
        current_x += w
    y -= 10
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.line(margin, y, width - margin, y)
    y -= 12
    c.setFont("Helvetica", 9)
    if drop_today:
        for row in drop_today:
                if y < 60:
                    c.showPage()
                    _draw_header_footer(c, title, subtitle)
                    y = height - 110
                    c.setFillColor(colors.HexColor("#0f172a"))
                    c.setFont("Helvetica-Bold", 12)
                    c.drawString(margin, y, "Clawback Drop or Rejected Today")
                    y -= 18
                    c.setFont("Helvetica-Bold", 9)
                    current_x = margin
                    for w, h in zip(col_widths, headers):
                        c.drawString(current_x, y, h)
                        current_x += w
                    y -= 10
                    c.setStrokeColor(colors.HexColor("#e2e8f0"))
                    c.line(margin, y, width - margin, y)
                    y -= 12
                    c.setFont("Helvetica", 9)
                vals = [
                    (row.get("candidate_name") or row.get("candidate_id", "N/A"))[:24],
                    str(row.get("status", ""))[:18],
                    str(row.get("date", "")),
                ]
                current_x = margin
                for w, v in zip(col_widths, vals):
                    c.drawString(current_x, y, v)
                    current_x += w
                y -= 14
    else:
        c.drawString(margin, y, "No data available")
        y -= 14
    y -= 14

    # Clawback candidate details table (all cases) - Always show, even if no data
    clawback_details = clawback_metrics.get("all_cases", [])
    if y < 200:
        c.showPage()
        _draw_header_footer(c, title, subtitle)
        y = height - 110
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, y, "Clawback Candidate Details")
    y -= 18
    headers = ["Candidate", "Recruiter", "Joined On", "Completion", "Status"]
    col_widths = [120, 120, 90, 90, 80]
    c.setFont("Helvetica-Bold", 9)
    current_x = margin
    for w, h in zip(col_widths, headers):
        c.drawString(current_x, y, h)
        current_x += w
    y -= 10
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.line(margin, y, width - margin, y)
    y -= 12
    c.setFont("Helvetica", 9)
    if clawback_details:
            if y < 200:
                c.showPage()
                _draw_header_footer(c, title, subtitle)
                y = height - 110
            c.setFillColor(colors.HexColor("#0f172a"))
            c.setFont("Helvetica-Bold", 12)
            c.drawString(margin, y, "Clawback Candidate Details")
            y -= 18
            headers = ["Candidate", "Recruiter", "Joined On", "Completion", "Status"]
            col_widths = [140, 140, 90, 90, 90]
            c.setFont("Helvetica-Bold", 9)
            current_x = margin
            for w, h in zip(col_widths, headers):
                c.drawString(current_x, y, h)
                current_x += w
            y -= 10
            c.setStrokeColor(colors.HexColor("#e2e8f0"))
            c.line(margin, y, width - margin, y)
            y -= 12
            c.setFont("Helvetica", 9)
            for row in clawback_details:
                if y < 60:
                    c.showPage()
                    _draw_header_footer(c, title, subtitle)
                    y = height - 110
                    c.setFillColor(colors.HexColor("#0f172a"))
                    c.setFont("Helvetica-Bold", 12)
                    c.drawString(margin, y, "Clawback Candidate Details")
                    y -= 18
                    c.setFont("Helvetica-Bold", 9)
                    current_x = margin
                    for w, h in zip(col_widths, headers):
                        c.drawString(current_x, y, h)
                        current_x += w
                    y -= 10
                    c.setStrokeColor(colors.HexColor("#e2e8f0"))
                    c.line(margin, y, width - margin, y)
                    y -= 12
                    c.setFont("Helvetica", 9)
                vals = [
                    (row.get("candidate_name") or row.get("candidate_id", "N/A"))[:20],
                    (row.get("recruiter_name") or "N/A")[:20],
                    str(row.get("joined_on", "")),
                    str(row.get("completion_date", "")),
                    str(row.get("status", ""))[:12],
                ]
                current_x = margin
                for w, v in zip(col_widths, vals):
                    c.drawString(current_x, y, v)
                    current_x += w
                y -= 14
    c.showPage()
    c.save()
    return buffer.getvalue()


def export_jobs_summary_pdf(
    title: str,
    summary_tiles: List[Tuple[str, str]],
    jobs_summary: List[Mapping],
    company_summary: List[Mapping],
    hr_summary: List[Mapping],
    daily_breakdown: List[Mapping],
    charts: Mapping[str, List[Mapping]],
    generated_by: str = "",
    date_range: Tuple[date, date] = (None, None),
    jobs_and_recruiters: List[Mapping] = None,
) -> bytes:
    """
    Export jobs summary report to PDF with tag-based statuses, company details, and daily breakdowns.
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    c.setTitle(title)

    # IST Conversion
    utc_now = datetime.utcnow()
    ist_now = utc_now + timedelta(hours=5, minutes=30)
    date_str = ist_now.strftime('%d-%b-%Y %I:%M %p IST')
    
    subtitle = f"Generated: {date_str}"
    
    # Date Range sub-text
    d_start, d_end = date_range
    if d_start and d_end:
        range_str = f"{d_start.strftime('%d %b %Y')} - {d_end.strftime('%d %b %Y')}"
    else:
        range_str = "All Time"
        
    subtitle += f" | Range: {range_str}"
    
    if generated_by:
        subtitle += f" | By: {generated_by}"

    _draw_header_footer(c, title, subtitle)
    y = height - 110
    margin = 40

    # Summary tiles
    y = _draw_tiles(c, summary_tiles, y)
    y -= 20

    # Daily Status Chart - Dynamic based on date range
    daily_tag_trends = charts.get("daily_tag_trends", [])
    if daily_tag_trends:
        if y < 300:
            c.showPage()
            _draw_header_footer(c, title, subtitle)
            y = height - 110
        
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, y, "Daily Status")
        y -= 20
        
        # Build multi-line chart for daily status trends
        fig = Figure(figsize=(10, 4))
        ax = fig.add_subplot(111)
        
        # Parse dates and prepare data
        dates_raw = [item.get("date", "") for item in daily_tag_trends]
        sourced = [item.get("sourced", 0) for item in daily_tag_trends]
        screened = [item.get("screened", 0) for item in daily_tag_trends]
        lined_up = [item.get("lined_up", 0) for item in daily_tag_trends]
        turned_up = [item.get("turned_up", 0) for item in daily_tag_trends]
        offer_accepted = [item.get("offer_accepted", 0) for item in daily_tag_trends]
        
        # Determine group type from date range
        d_start, d_end = date_range
        total_days = 365  # Default
        group_type = "daily"
        if d_start and d_end:
            total_days = (d_end - d_start).days + 1
            if total_days == 1:
                group_type = "hourly"
            elif total_days <= 30:
                group_type = "daily"
            elif total_days <= 365:
                group_type = "weekly"
            else:
                group_type = "monthly"
        
        # Format labels based on group type
        date_labels = []
        for d_str in dates_raw:
            if group_type == "hourly":
                # Already in HH:00 format
                date_labels.append(str(d_str))
            elif group_type == "daily":
                try:
                    if isinstance(d_str, str):
                        d = pd.to_datetime(d_str).date()
                        date_labels.append(d.strftime('%d-%m'))
                    elif isinstance(d_str, date):
                        date_labels.append(d_str.strftime('%d-%m'))
                    else:
                        date_labels.append(str(d_str)[:5])
                except:
                    date_labels.append(str(d_str)[:5])
            elif group_type == "weekly":
                try:
                    if isinstance(d_str, str):
                        d = pd.to_datetime(d_str).date()
                        date_labels.append(d.strftime('%d-%m'))
                    elif isinstance(d_str, date):
                        date_labels.append(d_str.strftime('%d-%m'))
                    else:
                        date_labels.append(str(d_str)[:5])
                except:
                    date_labels.append(str(d_str)[:5])
            else:  # monthly
                try:
                    if isinstance(d_str, str):
                        d = pd.to_datetime(d_str).date()
                        date_labels.append(d.strftime('%b-%Y'))
                    elif isinstance(d_str, date):
                        date_labels.append(d_str.strftime('%b-%Y'))
                    else:
                        date_labels.append(str(d_str)[:7])
                except:
                    date_labels.append(str(d_str)[:7])
        
        # Use numeric positions for plotting
        x_positions = range(len(dates_raw))
        
        ax.plot(x_positions, sourced, marker='o', label='Sourced', linewidth=2, markersize=4)
        ax.plot(x_positions, screened, marker='s', label='Screened', linewidth=2, markersize=4)
        ax.plot(x_positions, lined_up, marker='^', label='Lined Up', linewidth=2, markersize=4)
        ax.plot(x_positions, turned_up, marker='v', label='Turned Up', linewidth=2, markersize=4)
        ax.plot(x_positions, offer_accepted, marker='d', label='Offer Accepted', linewidth=2, markersize=4)
        
        ax.set_xlabel('Date' if group_type != "hourly" else 'Hour', fontsize=10)
        ax.set_ylabel('Count', fontsize=10)
        ax.set_title('Daily Status', fontsize=12, fontweight='bold')
        ax.legend(loc='best', fontsize=8)
        ax.grid(True, alpha=0.3)
        
        # Set X-axis labels with dynamic formatting
        rotation = 45 if len(date_labels) > 10 else (45 if group_type == "hourly" and len(date_labels) > 12 else 0)
        # Show every Nth label to prevent overlap (max 15 labels)
        if len(date_labels) > 15:
            step = max(1, len(date_labels) // 15)
            ax.set_xticks(x_positions[::step])
            ax.set_xticklabels(date_labels[::step], rotation=rotation, ha='right' if rotation else 'center', fontsize=8)
        else:
            ax.set_xticks(x_positions)
            ax.set_xticklabels(date_labels, rotation=rotation, ha='right' if rotation else 'center', fontsize=8)
        
        fig.tight_layout()
        
        img_buffer = io.BytesIO()
        fig.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
        img_buffer.seek(0)
        plt.close(fig)
        
        img = ImageReader(img_buffer)
        chart_height = 200
        c.drawImage(img, margin, y - chart_height, width=width - (2 * margin), height=chart_height, preserveAspectRatio=True, anchor="nw")
        y -= chart_height - 20

    # Page 2: Company Performance and Daily Joined vs Rejected Charts
    daily_joined_rejected = charts.get("daily_joined_rejected", [])
    company_performance = charts.get("company_performance", [])
    if company_performance or daily_joined_rejected:
        c.showPage()
        _draw_header_footer(c, title, subtitle)
        y = height - 110
    
    # Company Performance Chart
    if company_performance:
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, y, "Company Performance")
        y -= 20
        
        fig = Figure(figsize=(10, 4))
        ax = fig.add_subplot(111)
        
        # Truncate company names to prevent overlap
        companies_full = [item.get("company_name", "") for item in company_performance]
        # Determine max length based on number of companies
        num_companies = len(companies_full)
        if num_companies <= 5:
            max_len = 20
        elif num_companies <= 10:
            max_len = 15
        else:
            max_len = 12
        
        companies = [name[:max_len] + "..." if len(name) > max_len else name for name in companies_full]
        joined = [item.get("total_joined", 0) for item in company_performance]
        sourced = [item.get("total_sourced", 0) for item in company_performance]
        screened = [item.get("total_screened", 0) for item in company_performance]
        
        x_pos = range(len(companies))
        width_bar = 0.25
        
        ax.bar([x - width_bar for x in x_pos], joined, width_bar, label='Joined', color='#10b981')
        ax.bar(x_pos, sourced, width_bar, label='Sourced', color='#2563eb')
        ax.bar([x + width_bar for x in x_pos], screened, width_bar, label='Screened', color='#0ea5e9')
        
        ax.set_xlabel('Company', fontsize=10)
        ax.set_ylabel('Count', fontsize=10)
        ax.set_title('Company Performance', fontsize=12, fontweight='bold')
        ax.set_xticks(x_pos)
        
        # Dynamic rotation and spacing for company names
        if num_companies > 8:
            # Rotate labels and show every Nth to prevent overlap
            step = max(1, num_companies // 15) if num_companies > 15 else 1
            ax.set_xticks(x_pos[::step])
            ax.set_xticklabels(companies[::step], rotation=45, ha='right', fontsize=8)
        elif num_companies > 5:
            # Rotate but show all
            ax.set_xticklabels(companies, rotation=45, ha='right', fontsize=8)
        else:
            # Show all without rotation
            ax.set_xticklabels(companies, rotation=0, ha='center', fontsize=9)
        
        ax.legend(loc='best', fontsize=8)
        ax.grid(True, alpha=0.3, axis='y')
        
        fig.tight_layout()
        
        img_buffer = io.BytesIO()
        fig.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
        img_buffer.seek(0)
        plt.close(fig)
        
        img = ImageReader(img_buffer)
        chart_height = 200
        c.drawImage(img, margin, y - chart_height, width=width - (2 * margin), height=chart_height, preserveAspectRatio=True, anchor="nw")
        y -= chart_height - 20
    
    # Daily Joined vs Rejected Chart - On same page as Company Performance
    if daily_joined_rejected and len(daily_joined_rejected) > 0:
        # Add vertical separation
        y -= 30
        
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, y, "Daily Joined vs Rejected")
        y -= 20
        
        fig = Figure(figsize=(10, 4))
        ax = fig.add_subplot(111)
        
        dates_raw = [item.get("date", "") for item in daily_joined_rejected]
        joined = [item.get("joined", 0) for item in daily_joined_rejected]
        rejected = [item.get("rejected", 0) for item in daily_joined_rejected]
        
        # Determine group type from date range
        d_start, d_end = date_range
        total_days = 365  # Default
        group_type = "daily"
        if d_start and d_end:
            total_days = (d_end - d_start).days + 1
            if total_days == 1:
                group_type = "hourly"
            elif total_days <= 30:
                group_type = "daily"
            elif total_days <= 365:
                group_type = "weekly"
            else:
                group_type = "monthly"
        
        # Format labels based on group type
        date_labels = []
        for d_str in dates_raw:
            if group_type == "hourly":
                date_labels.append(str(d_str))
            elif group_type == "daily":
                try:
                    if isinstance(d_str, str):
                        d = pd.to_datetime(d_str).date()
                        date_labels.append(d.strftime('%d-%m'))
                    elif isinstance(d_str, date):
                        date_labels.append(d_str.strftime('%d-%m'))
                    else:
                        date_labels.append(str(d_str)[:5])
                except:
                    date_labels.append(str(d_str)[:5])
            elif group_type == "weekly":
                try:
                    if isinstance(d_str, str):
                        d = pd.to_datetime(d_str).date()
                        date_labels.append(d.strftime('%d-%m'))
                    elif isinstance(d_str, date):
                        date_labels.append(d_str.strftime('%d-%m'))
                    else:
                        date_labels.append(str(d_str)[:5])
                except:
                    date_labels.append(str(d_str)[:5])
            else:  # monthly
                try:
                    if isinstance(d_str, str):
                        d = pd.to_datetime(d_str).date()
                        date_labels.append(d.strftime('%b-%Y'))
                    elif isinstance(d_str, date):
                        date_labels.append(d_str.strftime('%b-%Y'))
                    else:
                        date_labels.append(str(d_str)[:7])
                except:
                    date_labels.append(str(d_str)[:7])
        
        x_pos = range(len(dates_raw))
        width_bar = 0.35
        
        ax.bar([x - width_bar/2 for x in x_pos], joined, width_bar, label='Joined', color='#10b981')
        ax.bar([x + width_bar/2 for x in x_pos], rejected, width_bar, label='Rejected', color='#ef4444')
        
        ax.set_xlabel('Date' if group_type != "hourly" else 'Hour', fontsize=10)
        ax.set_ylabel('Count', fontsize=10)
        ax.set_title('Daily Joined vs Rejected', fontsize=12, fontweight='bold')
        
        # Set X-axis labels with dynamic formatting (max 15 labels)
        rotation = 45 if len(date_labels) > 10 else (45 if group_type == "hourly" and len(date_labels) > 12 else 0)
        if len(date_labels) > 15:
            step = max(1, len(date_labels) // 15)
            ax.set_xticks(x_pos[::step])
            ax.set_xticklabels(date_labels[::step], rotation=rotation, ha='right' if rotation else 'center', fontsize=8)
        else:
            ax.set_xticks(x_pos)
            ax.set_xticklabels(date_labels, rotation=rotation, ha='right' if rotation else 'center', fontsize=8)
        
        ax.legend(loc='best', fontsize=8)
        ax.grid(True, alpha=0.3, axis='y')
        
        fig.tight_layout()
        
        img_buffer = io.BytesIO()
        fig.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
        img_buffer.seek(0)
        plt.close(fig)
        
        img = ImageReader(img_buffer)
        chart_height = 200
        c.drawImage(img, margin, y - chart_height, width=width - (2 * margin), height=chart_height, preserveAspectRatio=True, anchor="nw")
        y -= chart_height - 20
    
    # Best Performing Jobs Graph - After Daily Joined vs Rejected
    # Filter jobs with activities (only show jobs that have activity)
    jobs_with_activity = [j for j in jobs_summary if j.get("total_activity", 0) > 0]
    
    if jobs_with_activity:
        # Limit to top 15 jobs to prevent overcrowding
        jobs_with_activity = jobs_with_activity[:15]
        
        # Add vertical separation
        y -= 30
        
        # Check if we need a new page
        if y < 300:
            c.showPage()
            _draw_header_footer(c, title, subtitle)
            y = height - 110
        
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, y, "Best Performing Jobs")
        y -= 20
        
        # Build multi-line chart similar to Daily Status graph
        fig = Figure(figsize=(10, 4))
        ax = fig.add_subplot(111)
        
        # Prepare job labels (truncate with "..." to fit)
        job_labels_full = [j.get("job_title", f"Job {j.get('job_id', 'N/A')}") for j in jobs_with_activity]
        # Determine max length based on number of jobs
        num_jobs = len(job_labels_full)
        if num_jobs <= 5:
            max_len = 25
        elif num_jobs <= 10:
            max_len = 18
        else:
            max_len = 12
        
        job_labels = [label[:max_len] + "..." if len(label) > max_len else label for label in job_labels_full]
        
        # Prepare data for each status
        sourced = [j.get("sourced", 0) for j in jobs_with_activity]
        screened = [j.get("screened", 0) for j in jobs_with_activity]
        lined_up = [j.get("lined_up", 0) for j in jobs_with_activity]
        turned_up = [j.get("turned_up", 0) for j in jobs_with_activity]
        offer_accepted = [j.get("offer_accepted", 0) for j in jobs_with_activity]
        joined = [j.get("joined", 0) for j in jobs_with_activity]
        rejected = [j.get("rejected", 0) for j in jobs_with_activity]
        
        # Use numeric positions for plotting
        x_positions = range(len(job_labels))
        
        # Plot multiple lines for each status
        ax.plot(x_positions, sourced, marker='o', label='Sourced', linewidth=2, markersize=4, color='#2563eb')
        ax.plot(x_positions, screened, marker='s', label='Screened', linewidth=2, markersize=4, color='#0ea5e9')
        ax.plot(x_positions, lined_up, marker='^', label='Lined Up', linewidth=2, markersize=4, color='#10b981')
        ax.plot(x_positions, turned_up, marker='v', label='Turned Up', linewidth=2, markersize=4, color='#f59e0b')
        ax.plot(x_positions, offer_accepted, marker='d', label='Offer Accepted', linewidth=2, markersize=4, color='#8b5cf6')
        ax.plot(x_positions, joined, marker='*', label='Joined', linewidth=2, markersize=5, color='#10b981')
        ax.plot(x_positions, rejected, marker='x', label='Rejected', linewidth=2, markersize=5, color='#ef4444')
        
        ax.set_xlabel('Jobs', fontsize=10)
        ax.set_ylabel('Count', fontsize=10)
        ax.set_title('Best Performing Jobs - Activity by Status', fontsize=12, fontweight='bold')
        ax.legend(loc='best', fontsize=8)
        ax.grid(True, alpha=0.3)
        
        # Set X-axis labels with rotation and truncation
        rotation = 45 if num_jobs > 5 else (45 if num_jobs > 3 else 0)
        # Show every Nth label to prevent overlap (max 15 labels)
        if num_jobs > 15:
            step = max(1, num_jobs // 15)
            ax.set_xticks(x_positions[::step])
            ax.set_xticklabels(job_labels[::step], rotation=rotation, ha='right' if rotation else 'center', fontsize=8)
        else:
            ax.set_xticks(x_positions)
            ax.set_xticklabels(job_labels, rotation=rotation, ha='right' if rotation else 'center', fontsize=8)
        
        fig.tight_layout()
        
        img_buffer = io.BytesIO()
        fig.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
        img_buffer.seek(0)
        plt.close(fig)
        
        img = ImageReader(img_buffer)
        chart_height = 200
        c.drawImage(img, margin, y - chart_height, width=width - (2 * margin), height=chart_height, preserveAspectRatio=True, anchor="nw")
        y -= chart_height - 20

    # Jobs and Recruiters Table - Before Jobs Summary on page 3
    if jobs_and_recruiters:
        c.showPage()
        _draw_header_footer(c, title, subtitle)
        y = height - 110
        
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, y, "Jobs and Recruiters")
        y -= 20
        
        # Table headers - Job Id column wide enough to show full IDs without truncation
        # Total width: 612 (letter) - 80 (margins) = 532 available
        headers = ["Job Id", "Job Title", "Company", "No of Recruiters"]
        col_widths = [200, 140, 120, 72]
        
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(colors.HexColor("#0f172a"))
        x = margin
        for i, header in enumerate(headers):
            c.drawString(x, y, header)
            x += col_widths[i]
        y -= 15
        
        c.setStrokeColor(colors.HexColor("#e2e8f0"))
        c.line(margin, y, width - margin, y)
        y -= 12
        
        # Table rows
        c.setFont("Helvetica", 9)
        c.setFillColor(colors.black)
        for row in jobs_and_recruiters:
            if y < 60:
                c.showPage()
                _draw_header_footer(c, title, subtitle)
                y = height - 110
                # Redraw headers
                c.setFont("Helvetica-Bold", 9)
                c.setFillColor(colors.HexColor("#0f172a"))
                x = margin
                for i, header in enumerate(headers):
                    c.drawString(x, y, header)
                    x += col_widths[i]
                y -= 15
                c.setStrokeColor(colors.HexColor("#e2e8f0"))
                c.line(margin, y, width - margin, y)
                y -= 12
                c.setFont("Helvetica", 9)
                c.setFillColor(colors.black)
            
            job_id = str(row.get("job_id", "N/A"))
            job_title = str(row.get("job_title", "N/A"))
            company_name = str(row.get("company_name", "N/A"))
            num_recruiters = str(row.get("num_recruiters", 0))
            
            x = margin
            # Job ID - NEVER truncate, always show full ID
            c.drawString(x, y, job_id)
            x += col_widths[0]
            
            # Job Title - truncate if too long to fit in column (max ~18 chars for 140 width)
            if len(job_title) > 18:
                job_title = job_title[:15] + "..."
            c.drawString(x, y, job_title)
            x += col_widths[1]
            
            # Company - truncate if too long (max ~16 chars for 120 width)
            if len(company_name) > 16:
                company_name = company_name[:13] + "..."
            c.drawString(x, y, company_name)
            x += col_widths[2]
            
            c.drawString(x, y, num_recruiters)
            y -= 14
        
        y -= 20

    # Jobs Summary Table - Start on page 3
    if jobs_summary:
        if y < 200:  # If not enough space, start new page
            c.showPage()
            _draw_header_footer(c, title, subtitle)
            y = height - 110
        
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, y, "Jobs Summary")
        y -= 20
        
        # Table headers
        headers = ["Job Title", "Company", "Sourced", "Screened", "Lined Up", "Turned Up", "Offer Accepted", "Joined", "Rejected"]
        col_widths = [120, 100, 50, 50, 50, 50, 60, 50, 50]
        
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.HexColor("#0f172a"))
        x = margin
        for i, header in enumerate(headers):
            c.drawString(x, y, header[:15])
            x += col_widths[i]
        y -= 15
        
        c.setStrokeColor(colors.HexColor("#e2e8f0"))
        c.line(margin, y, width - margin, y)
        y -= 10
        
        # Table rows - Show ALL data (no truncation)
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.black)
        for row in jobs_summary:
            if y < 60:
                c.showPage()
                _draw_header_footer(c, title, subtitle)
                y = height - 110
                # Redraw headers
                c.setFont("Helvetica-Bold", 8)
                c.setFillColor(colors.HexColor("#0f172a"))
                x = margin
                for i, header in enumerate(headers):
                    c.drawString(x, y, header[:15])
                    x += col_widths[i]
                y -= 15
                c.setStrokeColor(colors.HexColor("#e2e8f0"))
                c.line(margin, y, width - margin, y)
                y -= 10
                c.setFont("Helvetica", 7)
                c.setFillColor(colors.black)
            
            x = margin
            job_title = str(row.get("job_title", ""))[:18]
            company = str(row.get("company_name", ""))[:15]
            c.drawString(x, y, job_title)
            x += col_widths[0]
            c.drawString(x, y, company)
            x += col_widths[1]
            c.drawString(x, y, str(row.get("sourced", 0)))
            x += col_widths[2]
            c.drawString(x, y, str(row.get("screened", 0)))
            x += col_widths[3]
            c.drawString(x, y, str(row.get("lined_up", 0)))
            x += col_widths[4]
            c.drawString(x, y, str(row.get("turned_up", 0)))
            x += col_widths[5]
            c.drawString(x, y, str(row.get("offer_accepted", 0)))
            x += col_widths[6]
            c.drawString(x, y, str(row.get("joined", 0)))
            x += col_widths[7]
            c.drawString(x, y, str(row.get("rejected", 0)))
            y -= 12

    # Company Summary Table - Add vertical gap from previous content
    if company_summary:
        if y < 200:
            c.showPage()
            _draw_header_footer(c, title, subtitle)
            y = height - 110
        else:
            # Add vertical gap
            y -= 40
        
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, y, "Company Summary")
        y -= 20
        
        # Table headers
        headers = ["Company", "Jobs", "Openings", "Sourced", "Screened", "Lined Up", "Turned Up", "Offer Accepted", "Joined", "Rejected"]
        col_widths = [120, 40, 50, 50, 50, 50, 50, 60, 50, 50]
        
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.HexColor("#0f172a"))
        x = margin
        for i, header in enumerate(headers):
            c.drawString(x, y, header[:12])
            x += col_widths[i]
        y -= 15
        
        c.setStrokeColor(colors.HexColor("#e2e8f0"))
        c.line(margin, y, width - margin, y)
        y -= 10
        
        # Table rows - Show ALL data (no truncation)
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.black)
        for row in company_summary:
            if y < 60:
                c.showPage()
                _draw_header_footer(c, title, subtitle)
                y = height - 110
                # Redraw headers
                c.setFont("Helvetica-Bold", 8)
                c.setFillColor(colors.HexColor("#0f172a"))
                x = margin
                for i, header in enumerate(headers):
                    c.drawString(x, y, header[:12])
                    x += col_widths[i]
                y -= 15
                c.setStrokeColor(colors.HexColor("#e2e8f0"))
                c.line(margin, y, width - margin, y)
                y -= 10
                c.setFont("Helvetica", 7)
                c.setFillColor(colors.black)
            
            x = margin
            company = str(row.get("company_name", ""))[:18]
            c.drawString(x, y, company)
            x += col_widths[0]
            c.drawString(x, y, str(row.get("total_jobs", 0)))
            x += col_widths[1]
            c.drawString(x, y, str(row.get("total_openings", 0)))
            x += col_widths[2]
            c.drawString(x, y, str(row.get("total_sourced", 0)))
            x += col_widths[3]
            c.drawString(x, y, str(row.get("total_screened", 0)))
            x += col_widths[4]
            c.drawString(x, y, str(row.get("total_lined_up", 0)))
            x += col_widths[5]
            c.drawString(x, y, str(row.get("total_turned_up", 0)))
            x += col_widths[6]
            c.drawString(x, y, str(row.get("total_offer_accepted", 0)))
            x += col_widths[7]
            c.drawString(x, y, str(row.get("total_joined", 0)))
            x += col_widths[8]
            c.drawString(x, y, str(row.get("total_rejected", 0)))
            y -= 12

    # HR Summary Table - Add vertical gap from Company Summary
    if hr_summary:
        if y < 200:
            c.showPage()
            _draw_header_footer(c, title, subtitle)
            y = height - 110
        else:
            # Add vertical gap from previous table
            y -= 40
        
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, y, "HR Summary")
        y -= 20
        
        # Table headers - Include all statuses with Jobs Assigned, better column widths
        # Total width: 612 (letter) - 80 (margins) = 532 available
        headers = ["HR Name", "Jobs", "Candidates", "Act...", "Sourced", "Scrr..", "Lined", "Turned", "Offer...", "Joined", "Rejected", "Total..."]
        col_widths = [85, 38, 38, 38, 38, 38, 38, 38, 42, 38, 38, 42]
        
        c.setFont("Helvetica-Bold", 7)
        c.setFillColor(colors.HexColor("#0f172a"))
        x = margin
        for i, header in enumerate(headers):
            c.drawString(x, y, header)
            x += col_widths[i]
        y -= 12
        
        c.setStrokeColor(colors.HexColor("#e2e8f0"))
        c.line(margin, y, width - margin, y)
        y -= 10
        
        # Table rows - Show all statuses with truncation
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.black)
        for row in hr_summary:
            if y < 60:
                c.showPage()
                _draw_header_footer(c, title, subtitle)
                y = height - 110
                # Redraw headers
                c.setFont("Helvetica-Bold", 7)
                c.setFillColor(colors.HexColor("#0f172a"))
                x = margin
                for i, header in enumerate(headers):
                    c.drawString(x, y, header)
                    x += col_widths[i]
                y -= 12
                c.setStrokeColor(colors.HexColor("#e2e8f0"))
                c.line(margin, y, width - margin, y)
                y -= 10
                c.setFont("Helvetica", 7)
                c.setFillColor(colors.black)
            
            x = margin
            hr_name = str(row.get("hr_name", ""))
            # Truncate HR name if too long
            if len(hr_name) > 12:
                hr_name = hr_name[:9] + "..."
            jobs_assigned = str(row.get("jobs_assigned", 0))
            candidates = str(row.get("candidate_count", 0))
            activities = str(row.get("activity_count", 0))
            sourced = str(row.get("sourced", 0))
            screened = str(row.get("screened", 0))
            lined_up = str(row.get("lined_up", 0))
            turned_up = str(row.get("turned_up", 0))
            offer_accepted = str(row.get("offer_accepted", 0))
            joined = str(row.get("joined", 0))
            rejected = str(row.get("rejected", 0))
            total_activity = str(row.get("total_activity", 0))
            
            # Draw all values
            c.drawString(x, y, hr_name)
            x += col_widths[0]
            c.drawString(x, y, jobs_assigned)
            x += col_widths[1]
            c.drawString(x, y, candidates)
            x += col_widths[2]
            c.drawString(x, y, activities)
            x += col_widths[3]
            c.drawString(x, y, sourced)
            x += col_widths[4]
            c.drawString(x, y, screened)
            x += col_widths[5]
            c.drawString(x, y, lined_up)
            x += col_widths[6]
            c.drawString(x, y, turned_up)
            x += col_widths[7]
            c.drawString(x, y, offer_accepted)
            x += col_widths[8]
            c.drawString(x, y, joined)
            x += col_widths[9]
            c.drawString(x, y, rejected)
            x += col_widths[10]
            c.drawString(x, y, total_activity)
            y -= 11

    c.showPage()
    _draw_header_footer(c, title, subtitle)
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.HexColor("#666666"))
    c.drawCentredString(width/2, height/2, "END OF REPORT")

    c.save()
    return buffer.getvalue()


def export_recruiters_summary_pdf(
    title: str,
    summary_tiles: List[Tuple[str, str]],
    recruiters_summary: List[Mapping],
    daily_breakdown: List[Mapping],
    charts: Mapping[str, List[Mapping]],
    generated_by: str = "",
    date_range: Tuple[date, date] = (None, None),
) -> bytes:
    """
    Export recruiters summary report to PDF with tag-based statuses and daily breakdowns.
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    c.setTitle(title)

    # IST Conversion
    utc_now = datetime.utcnow()
    ist_now = utc_now + timedelta(hours=5, minutes=30)
    date_str = ist_now.strftime('%d-%b-%Y %I:%M %p IST')
    
    subtitle = f"Generated: {date_str}"
    
    # Date Range sub-text
    d_start, d_end = date_range
    if d_start and d_end:
        range_str = f"{d_start.strftime('%d %b %Y')} - {d_end.strftime('%d %b %Y')}"
    else:
        range_str = "All Time"
        
    subtitle += f" | Range: {range_str}"
    
    if generated_by:
        subtitle += f" | By: {generated_by}"

    _draw_header_footer(c, title, subtitle)
    y = height - 110
    margin = 40

    # Summary tiles
    y = _draw_tiles(c, summary_tiles, y)
    y -= 20

    # Daily Status Chart - Dynamic based on date range
    daily_status_trends = charts.get("daily_status_trends", [])
    if daily_status_trends:
        if y < 300:
            c.showPage()
            _draw_header_footer(c, title, subtitle)
            y = height - 110
        
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, y, "Daily Status")
        y -= 20
        
        # Build multi-line chart
        fig = Figure(figsize=(10, 4))
        ax = fig.add_subplot(111)
        
        dates_raw = [item.get("date", "") for item in daily_status_trends]
        sourced = [item.get("sourced", 0) for item in daily_status_trends]
        screened = [item.get("screened", 0) for item in daily_status_trends]
        lined_up = [item.get("lined_up", 0) for item in daily_status_trends]
        turned_up = [item.get("turned_up", 0) for item in daily_status_trends]
        offer_accepted = [item.get("offer_accepted", 0) for item in daily_status_trends]
        
        # Determine group type from date range
        d_start, d_end = date_range
        total_days = 365
        group_type = "daily"
        if d_start and d_end:
            total_days = (d_end - d_start).days + 1
            if total_days == 1:
                group_type = "hourly"
            elif total_days <= 30:
                group_type = "daily"
            elif total_days <= 365:
                group_type = "weekly"
            else:
                group_type = "monthly"
        
        # Format labels based on group type
        date_labels = []
        for d_str in dates_raw:
            if group_type == "hourly":
                date_labels.append(str(d_str))
            elif group_type == "daily":
                try:
                    if isinstance(d_str, str):
                        d = pd.to_datetime(d_str).date()
                        date_labels.append(d.strftime('%d-%m'))
                    elif isinstance(d_str, date):
                        date_labels.append(d_str.strftime('%d-%m'))
                    else:
                        date_labels.append(str(d_str)[:5])
                except:
                    date_labels.append(str(d_str)[:5])
            elif group_type == "weekly":
                try:
                    if isinstance(d_str, str):
                        d = pd.to_datetime(d_str).date()
                        date_labels.append(d.strftime('%d-%m'))
                    elif isinstance(d_str, date):
                        date_labels.append(d_str.strftime('%d-%m'))
                    else:
                        date_labels.append(str(d_str)[:5])
                except:
                    date_labels.append(str(d_str)[:5])
            else:  # monthly
                try:
                    if isinstance(d_str, str):
                        d = pd.to_datetime(d_str).date()
                        date_labels.append(d.strftime('%b-%Y'))
                    elif isinstance(d_str, date):
                        date_labels.append(d_str.strftime('%b-%Y'))
                    else:
                        date_labels.append(str(d_str)[:7])
                except:
                    date_labels.append(str(d_str)[:7])
        
        x_positions = range(len(dates_raw))
        
        ax.plot(x_positions, sourced, marker='o', label='Sourced', linewidth=2, markersize=4)
        ax.plot(x_positions, screened, marker='s', label='Screened', linewidth=2, markersize=4)
        ax.plot(x_positions, lined_up, marker='^', label='Lined Up', linewidth=2, markersize=4)
        ax.plot(x_positions, turned_up, marker='v', label='Turned Up', linewidth=2, markersize=4)
        ax.plot(x_positions, offer_accepted, marker='d', label='Offer Accepted', linewidth=2, markersize=4)
        
        ax.set_xlabel('Date' if group_type != "hourly" else 'Hour', fontsize=10)
        ax.set_ylabel('Count', fontsize=10)
        ax.set_title('Daily Status', fontsize=12, fontweight='bold')
        ax.legend(loc='best', fontsize=8)
        ax.grid(True, alpha=0.3)
        
        # Set X-axis labels with dynamic formatting (max 15 labels)
        rotation = 45 if len(date_labels) > 10 else (45 if group_type == "hourly" and len(date_labels) > 12 else 0)
        if len(date_labels) > 15:
            step = max(1, len(date_labels) // 15)
            ax.set_xticks(x_positions[::step])
            ax.set_xticklabels(date_labels[::step], rotation=rotation, ha='right' if rotation else 'center', fontsize=8)
        else:
            ax.set_xticks(x_positions)
            ax.set_xticklabels(date_labels, rotation=rotation, ha='right' if rotation else 'center', fontsize=8)
        
        fig.tight_layout()
        
        img_buffer = io.BytesIO()
        fig.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
        img_buffer.seek(0)
        plt.close(fig)
        
        img = ImageReader(img_buffer)
        chart_height = 200
        c.drawImage(img, margin, y - chart_height, width=width - (2 * margin), height=chart_height, preserveAspectRatio=True, anchor="nw")
        y -= chart_height - 20

    # Page 2: Daily Joined vs Rejected and Top Recruiters Performance Charts
    daily_joined_rejected = charts.get("daily_joined_rejected", [])
    top_recruiters_performance = charts.get("top_recruiters_performance", [])
    
    # Check if we have actual data
    has_page2_charts = (daily_joined_rejected and len(daily_joined_rejected) > 0) or \
                       (top_recruiters_performance and len(top_recruiters_performance) > 0)
    
    if has_page2_charts:
        c.showPage()
        _draw_header_footer(c, title, subtitle)
        y = height - 110
    
    # Daily Joined vs Rejected Chart
    if daily_joined_rejected and len(daily_joined_rejected) > 0:
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, y, "Daily Joined vs Rejected")
        y -= 20
        
        fig = Figure(figsize=(10, 4))
        ax = fig.add_subplot(111)
        
        dates_raw = [item.get("date", "") for item in daily_joined_rejected]
        joined = [item.get("joined", 0) for item in daily_joined_rejected]
        rejected = [item.get("rejected", 0) for item in daily_joined_rejected]
        
        # Determine group type from date range
        d_start, d_end = date_range
        total_days = 365
        group_type = "daily"
        if d_start and d_end:
            total_days = (d_end - d_start).days + 1
            if total_days == 1:
                group_type = "hourly"
            elif total_days <= 30:
                group_type = "daily"
            elif total_days <= 365:
                group_type = "weekly"
            else:
                group_type = "monthly"
        
        # Format labels based on group type
        date_labels = []
        for d_str in dates_raw:
            if group_type == "hourly":
                date_labels.append(str(d_str))
            elif group_type == "daily":
                try:
                    if isinstance(d_str, str):
                        d = pd.to_datetime(d_str).date()
                        date_labels.append(d.strftime('%d-%m'))
                    elif isinstance(d_str, date):
                        date_labels.append(d_str.strftime('%d-%m'))
                    else:
                        date_labels.append(str(d_str)[:5])
                except:
                    date_labels.append(str(d_str)[:5])
            elif group_type == "weekly":
                try:
                    if isinstance(d_str, str):
                        d = pd.to_datetime(d_str).date()
                        date_labels.append(d.strftime('%d-%m'))
                    elif isinstance(d_str, date):
                        date_labels.append(d_str.strftime('%d-%m'))
                    else:
                        date_labels.append(str(d_str)[:5])
                except:
                    date_labels.append(str(d_str)[:5])
            else:  # monthly
                try:
                    if isinstance(d_str, str):
                        d = pd.to_datetime(d_str).date()
                        date_labels.append(d.strftime('%b-%Y'))
                    elif isinstance(d_str, date):
                        date_labels.append(d.strftime('%b-%Y'))
                    else:
                        date_labels.append(str(d_str)[:7])
                except:
                    date_labels.append(str(d_str)[:7])
        
        x_pos = range(len(dates_raw))
        width_bar = 0.35
        
        ax.bar([x - width_bar/2 for x in x_pos], joined, width_bar, label='Joined', color='#10b981')
        ax.bar([x + width_bar/2 for x in x_pos], rejected, width_bar, label='Rejected', color='#ef4444')
        
        ax.set_xlabel('Date' if group_type != "hourly" else 'Hour', fontsize=10)
        ax.set_ylabel('Count', fontsize=10)
        ax.set_title('Daily Joined vs Rejected', fontsize=12, fontweight='bold')
        
        # Set X-axis labels with dynamic formatting (max 15 labels)
        rotation = 45 if len(date_labels) > 10 else (45 if group_type == "hourly" and len(date_labels) > 12 else 0)
        if len(date_labels) > 15:
            step = max(1, len(date_labels) // 15)
            ax.set_xticks(x_pos[::step])
            ax.set_xticklabels(date_labels[::step], rotation=rotation, ha='right' if rotation else 'center', fontsize=8)
        else:
            ax.set_xticks(x_pos)
            ax.set_xticklabels(date_labels, rotation=rotation, ha='right' if rotation else 'center', fontsize=8)
        
        ax.legend(loc='best', fontsize=8)
        ax.grid(True, alpha=0.3, axis='y')
        
        fig.tight_layout()
        
        img_buffer = io.BytesIO()
        fig.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
        img_buffer.seek(0)
        plt.close(fig)
        
        img = ImageReader(img_buffer)
        chart_height = 200
        c.drawImage(img, margin, y - chart_height, width=width - (2 * margin), height=chart_height, preserveAspectRatio=True, anchor="nw")
        y -= chart_height - 20
    
    # Top Recruiters Performance Chart
    if top_recruiters_performance and len(top_recruiters_performance) > 0:
        # Add vertical separation
        y -= 30
        
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, y, "Top Recruiters Performance")
        y -= 20
        
        fig = Figure(figsize=(10, 4))
        ax = fig.add_subplot(111)
        
        recruiters_full = [item.get("recruiter_name", "") for item in top_recruiters_performance]
        num_recruiters = len(recruiters_full)
        if num_recruiters <= 5:
            max_len = 20
        elif num_recruiters <= 10:
            max_len = 15
        else:
            max_len = 12
        
        recruiters = [name[:max_len] + "..." if len(name) > max_len else name for name in recruiters_full]
        joined = [item.get("joined", 0) for item in top_recruiters_performance]
        sourced = [item.get("sourced", 0) for item in top_recruiters_performance]
        screened = [item.get("screened", 0) for item in top_recruiters_performance]
        
        x_pos = range(len(recruiters))
        width_bar = 0.25
        
        ax.bar([x - width_bar for x in x_pos], joined, width_bar, label='Joined', color='#10b981')
        ax.bar(x_pos, sourced, width_bar, label='Sourced', color='#2563eb')
        ax.bar([x + width_bar for x in x_pos], screened, width_bar, label='Screened', color='#0ea5e9')
        
        ax.set_xlabel('Recruiter', fontsize=10)
        ax.set_ylabel('Count', fontsize=10)
        ax.set_title('Top Recruiters Performance', fontsize=12, fontweight='bold')
        ax.set_xticks(x_pos)
        
        # Dynamic rotation and spacing for recruiter names
        if num_recruiters > 8:
            step = max(1, num_recruiters // 15) if num_recruiters > 15 else 1
            ax.set_xticks(x_pos[::step])
            ax.set_xticklabels(recruiters[::step], rotation=45, ha='right', fontsize=8)
        elif num_recruiters > 5:
            ax.set_xticklabels(recruiters, rotation=45, ha='right', fontsize=8)
        else:
            ax.set_xticklabels(recruiters, rotation=0, ha='center', fontsize=9)
        
        ax.legend(loc='best', fontsize=8)
        ax.grid(True, alpha=0.3, axis='y')
        
        fig.tight_layout()
        
        img_buffer = io.BytesIO()
        fig.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
        img_buffer.seek(0)
        plt.close(fig)
        
        img = ImageReader(img_buffer)
        chart_height = 200
        c.drawImage(img, margin, y - chart_height, width=width - (2 * margin), height=chart_height, preserveAspectRatio=True, anchor="nw")
        y -= chart_height - 20

    # Recruiters Summary Table - Start on next page
    if recruiters_summary and len(recruiters_summary) > 0:
        # Always create a new page for the table to ensure proper spacing
        c.showPage()
        _draw_header_footer(c, title, subtitle)
        y = height - 110
        
        
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, y, "Recruiters Summary")
        y -= 20
        
        # Table headers
        headers = ["Recruiter Name", "Candidates", "Sourced", "Screened", "Lined Up", "Turned Up", "Offer Accepted", "Joined", "Rejected", "Activities", "Logins"]
        col_widths = [120, 60, 50, 50, 50, 50, 60, 50, 50, 60, 50]
        
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.HexColor("#0f172a"))
        x = margin
        for i, header in enumerate(headers):
            c.drawString(x, y, header[:12])
            x += col_widths[i]
        y -= 15
        
        c.setStrokeColor(colors.HexColor("#e2e8f0"))
        c.line(margin, y, width - margin, y)
        y -= 10
        
        # Table rows - Show ALL data (no truncation)
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.black)
        for row in recruiters_summary:
            if y < 60:
                c.showPage()
                _draw_header_footer(c, title, subtitle)
                y = height - 110
                # Redraw headers
                c.setFont("Helvetica-Bold", 8)
                c.setFillColor(colors.HexColor("#0f172a"))
                x = margin
                for i, header in enumerate(headers):
                    c.drawString(x, y, header[:12])
                    x += col_widths[i]
                y -= 15
                c.setStrokeColor(colors.HexColor("#e2e8f0"))
                c.line(margin, y, width - margin, y)
                y -= 10
                c.setFont("Helvetica", 7)
                c.setFillColor(colors.black)
            
            x = margin
            recruiter_name = str(row.get("recruiter_name", ""))[:18]
            c.drawString(x, y, recruiter_name)
            x += col_widths[0]
            c.drawString(x, y, str(row.get("candidates", 0)))
            x += col_widths[1]
            c.drawString(x, y, str(row.get("sourced", 0)))
            x += col_widths[2]
            c.drawString(x, y, str(row.get("screened", 0)))
            x += col_widths[3]
            c.drawString(x, y, str(row.get("lined_up", 0)))
            x += col_widths[4]
            c.drawString(x, y, str(row.get("turned_up", 0)))
            x += col_widths[5]
            c.drawString(x, y, str(row.get("offer_accepted", 0)))
            x += col_widths[6]
            c.drawString(x, y, str(row.get("joined", 0)))
            x += col_widths[7]
            c.drawString(x, y, str(row.get("rejected", 0)))
            x += col_widths[8]
            c.drawString(x, y, str(row.get("activities", 0)))
            x += col_widths[9]
            c.drawString(x, y, str(row.get("logins", 0)))
            y -= 12
    
    # Only show END OF REPORT if we've displayed some content
    # Check if we have any content to show
    has_content = (
        (daily_status_trends and len(daily_status_trends) > 0) or
        has_page2_charts or
        (recruiters_summary and len(recruiters_summary) > 0)
    )
    
    if has_content:
        c.showPage()
        _draw_header_footer(c, title, subtitle)
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.HexColor("#666666"))
        c.drawCentredString(width/2, height/2, "END OF REPORT")

    c.save()
    return buffer.getvalue()


def export_recruiter_performance_pdf(
    title: str,
    summary_tiles: List[Tuple[str, str]],
    recruiter_metadata: Mapping,
    jobs_assigned: List[Mapping],
    daily_breakdown: List[Mapping],
    recruiter_activity_details: List[Mapping],
    login_logs: List[Mapping],
    charts: Mapping[str, List[Mapping]],
    generated_by: str = "",
    date_range: Tuple[date, date] = (None, None),
) -> bytes:
    """
    Export individual recruiter performance report to PDF.
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    c.setTitle(title)

    # IST Conversion
    utc_now = datetime.utcnow()
    ist_now = utc_now + timedelta(hours=5, minutes=30)
    date_str = ist_now.strftime('%d-%b-%Y %I:%M %p IST')
    
    subtitle = f"Generated: {date_str}"
    
    # Date Range sub-text
    d_start, d_end = date_range
    if d_start and d_end:
        range_str = f"{d_start.strftime('%d %b %Y')} - {d_end.strftime('%d %b %Y')}"
    else:
        range_str = "All Time"
        
    subtitle += f" | Range: {range_str}"
    
    if generated_by:
        subtitle += f" | By: {generated_by}"

    _draw_header_footer(c, title, subtitle)
    y = height - 110
    margin = 40

    # Recruiter metadata - Truncate long names to prevent header overflow
    recruiter_name = recruiter_metadata.get("recruiter_name", "N/A")
    # Truncate if too long (max 50 chars to fit on page)
    if len(recruiter_name) > 50:
        recruiter_name = recruiter_name[:47] + "..."
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.drawString(margin, y, f"Recruiter: {recruiter_name}")
    y -= 30

    # Summary tiles
    y = _draw_tiles(c, summary_tiles, y)
    y -= 20

    # Daily Status Chart
    daily_status_trends = charts.get("daily_status_trends", [])
    if daily_status_trends:
        if y < 300:
            c.showPage()
            _draw_header_footer(c, title, subtitle)
            y = height - 110
        
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, y, "Daily Status")
        y -= 20
        
        fig = Figure(figsize=(10, 4))
        ax = fig.add_subplot(111)
        
        dates_raw = [item.get("date", "") for item in daily_status_trends]
        sourced = [item.get("sourced", 0) for item in daily_status_trends]
        screened = [item.get("screened", 0) for item in daily_status_trends]
        lined_up = [item.get("lined_up", 0) for item in daily_status_trends]
        turned_up = [item.get("turned_up", 0) for item in daily_status_trends]
        offer_accepted = [item.get("offer_accepted", 0) for item in daily_status_trends]
        
        # Determine group type from date range
        d_start, d_end = date_range
        total_days = 365
        group_type = "daily"
        if d_start and d_end:
            total_days = (d_end - d_start).days + 1
            if total_days == 1:
                group_type = "hourly"
            elif total_days <= 30:
                group_type = "daily"
            elif total_days <= 365:
                group_type = "weekly"
            else:
                group_type = "monthly"
        
        # Format labels based on group type
        date_labels = []
        for d_str in dates_raw:
            if group_type == "hourly":
                date_labels.append(str(d_str))
            elif group_type == "daily":
                try:
                    if isinstance(d_str, str):
                        d = pd.to_datetime(d_str).date()
                        date_labels.append(d.strftime('%d-%m'))
                    elif isinstance(d_str, date):
                        date_labels.append(d_str.strftime('%d-%m'))
                    else:
                        date_labels.append(str(d_str)[:5])
                except:
                    date_labels.append(str(d_str)[:5])
            elif group_type == "weekly":
                try:
                    if isinstance(d_str, str):
                        d = pd.to_datetime(d_str).date()
                        date_labels.append(d.strftime('%d-%m'))
                    elif isinstance(d_str, date):
                        date_labels.append(d_str.strftime('%d-%m'))
                    else:
                        date_labels.append(str(d_str)[:5])
                except:
                    date_labels.append(str(d_str)[:5])
            else:  # monthly
                try:
                    if isinstance(d_str, str):
                        d = pd.to_datetime(d_str).date()
                        date_labels.append(d.strftime('%b-%Y'))
                    elif isinstance(d_str, date):
                        date_labels.append(d.strftime('%b-%Y'))
                    else:
                        date_labels.append(str(d_str)[:7])
                except:
                    date_labels.append(str(d_str)[:7])
        
        x_positions = range(len(dates_raw))
        
        ax.plot(x_positions, sourced, marker='o', label='Sourced', linewidth=2, markersize=4)
        ax.plot(x_positions, screened, marker='s', label='Screened', linewidth=2, markersize=4)
        ax.plot(x_positions, lined_up, marker='^', label='Lined Up', linewidth=2, markersize=4)
        ax.plot(x_positions, turned_up, marker='v', label='Turned Up', linewidth=2, markersize=4)
        ax.plot(x_positions, offer_accepted, marker='d', label='Offer Accepted', linewidth=2, markersize=4)
        
        ax.set_xlabel('Date' if group_type != "hourly" else 'Hour', fontsize=10)
        ax.set_ylabel('Count', fontsize=10)
        ax.set_title('Daily Status', fontsize=12, fontweight='bold')
        ax.legend(loc='best', fontsize=8)
        ax.grid(True, alpha=0.3)
        
        # Set X-axis labels with dynamic formatting (max 15 labels)
        rotation = 45 if len(date_labels) > 10 else (45 if group_type == "hourly" and len(date_labels) > 12 else 0)
        if len(date_labels) > 15:
            step = max(1, len(date_labels) // 15)
            ax.set_xticks(x_positions[::step])
            ax.set_xticklabels(date_labels[::step], rotation=rotation, ha='right' if rotation else 'center', fontsize=8)
        else:
            ax.set_xticks(x_positions)
            ax.set_xticklabels(date_labels, rotation=rotation, ha='right' if rotation else 'center', fontsize=8)
        
        fig.tight_layout()
        
        img_buffer = io.BytesIO()
        fig.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
        img_buffer.seek(0)
        plt.close(fig)
        
        img = ImageReader(img_buffer)
        chart_height = 200
        c.drawImage(img, margin, y - chart_height, width=width - (2 * margin), height=chart_height, preserveAspectRatio=True, anchor="nw")
        y -= chart_height - 20

    # Page 2: Daily Joined vs Rejected and Jobs Performance Charts
    daily_joined_rejected = charts.get("daily_joined_rejected", [])
    jobs_performance = charts.get("jobs_performance", [])
    
    # Check if we have actual data
    has_page2_charts = (daily_joined_rejected and len(daily_joined_rejected) > 0) or \
                       (jobs_performance and len(jobs_performance) > 0)
    
    if has_page2_charts:
        c.showPage()
        _draw_header_footer(c, title, subtitle)
        y = height - 110
    
    # Daily Joined vs Rejected Chart
    if daily_joined_rejected and len(daily_joined_rejected) > 0:
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, y, "Daily Joined vs Rejected")
        y -= 20
        
        fig = Figure(figsize=(10, 4))
        ax = fig.add_subplot(111)
        
        dates_raw = [item.get("date", "") for item in daily_joined_rejected]
        joined = [item.get("joined", 0) for item in daily_joined_rejected]
        rejected = [item.get("rejected", 0) for item in daily_joined_rejected]
        
        # Determine group type from date range
        d_start, d_end = date_range
        total_days = 365
        group_type = "daily"
        if d_start and d_end:
            total_days = (d_end - d_start).days + 1
            if total_days == 1:
                group_type = "hourly"
            elif total_days <= 30:
                group_type = "daily"
            elif total_days <= 365:
                group_type = "weekly"
            else:
                group_type = "monthly"
        
        # Format labels based on group type
        date_labels = []
        for d_str in dates_raw:
            if group_type == "hourly":
                date_labels.append(str(d_str))
            elif group_type == "daily":
                try:
                    if isinstance(d_str, str):
                        d = pd.to_datetime(d_str).date()
                        date_labels.append(d.strftime('%d-%m'))
                    elif isinstance(d_str, date):
                        date_labels.append(d.strftime('%d-%m'))
                    else:
                        date_labels.append(str(d_str)[:5])
                except:
                    date_labels.append(str(d_str)[:5])
            elif group_type == "weekly":
                try:
                    if isinstance(d_str, str):
                        d = pd.to_datetime(d_str).date()
                        date_labels.append(d.strftime('%d-%m'))
                    elif isinstance(d_str, date):
                        date_labels.append(d.strftime('%d-%m'))
                    else:
                        date_labels.append(str(d_str)[:5])
                except:
                    date_labels.append(str(d_str)[:5])
            else:  # monthly
                try:
                    if isinstance(d_str, str):
                        d = pd.to_datetime(d_str).date()
                        date_labels.append(d.strftime('%b-%Y'))
                    elif isinstance(d_str, date):
                        date_labels.append(d.strftime('%b-%Y'))
                    else:
                        date_labels.append(str(d_str)[:7])
                except:
                    date_labels.append(str(d_str)[:7])
        
        x_pos = range(len(dates_raw))
        width_bar = 0.35
        
        ax.bar([x - width_bar/2 for x in x_pos], joined, width_bar, label='Joined', color='#10b981')
        ax.bar([x + width_bar/2 for x in x_pos], rejected, width_bar, label='Rejected', color='#ef4444')
        
        ax.set_xlabel('Date' if group_type != "hourly" else 'Hour', fontsize=10)
        ax.set_ylabel('Count', fontsize=10)
        ax.set_title('Daily Joined vs Rejected', fontsize=12, fontweight='bold')
        
        # Set X-axis labels with dynamic formatting (max 15 labels)
        rotation = 45 if len(date_labels) > 10 else (45 if group_type == "hourly" and len(date_labels) > 12 else 0)
        if len(date_labels) > 15:
            step = max(1, len(date_labels) // 15)
            ax.set_xticks(x_pos[::step])
            ax.set_xticklabels(date_labels[::step], rotation=rotation, ha='right' if rotation else 'center', fontsize=8)
        else:
            ax.set_xticks(x_pos)
            ax.set_xticklabels(date_labels, rotation=rotation, ha='right' if rotation else 'center', fontsize=8)
        
        ax.legend(loc='best', fontsize=8)
        ax.grid(True, alpha=0.3, axis='y')
        
        fig.tight_layout()
        
        img_buffer = io.BytesIO()
        fig.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
        img_buffer.seek(0)
        plt.close(fig)
        
        img = ImageReader(img_buffer)
        chart_height = 200
        c.drawImage(img, margin, y - chart_height, width=width - (2 * margin), height=chart_height, preserveAspectRatio=True, anchor="nw")
        y -= chart_height - 20
    
    # Jobs Performance Chart
    if jobs_performance and len(jobs_performance) > 0:
        # Add vertical separation
        y -= 30
        
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, y, "Jobs Performance")
        y -= 20
        
        fig = Figure(figsize=(10, 4))
        ax = fig.add_subplot(111)
        
        jobs_full = [item.get("job_title", "") for item in jobs_performance]
        num_jobs = len(jobs_full)
        if num_jobs <= 5:
            max_len = 25
        elif num_jobs <= 10:
            max_len = 20
        else:
            max_len = 15
        
        jobs = [name[:max_len] + "..." if len(name) > max_len else name for name in jobs_full]
        candidates = [item.get("candidates", 0) for item in jobs_performance]
        joined = [item.get("joined", 0) for item in jobs_performance]
        
        x_pos = range(len(jobs))
        width_bar = 0.35
        
        ax.bar([x - width_bar/2 for x in x_pos], candidates, width_bar, label='Candidates', color='#2563eb')
        ax.bar([x + width_bar/2 for x in x_pos], joined, width_bar, label='Joined', color='#10b981')
        
        ax.set_xlabel('Job', fontsize=10)
        ax.set_ylabel('Count', fontsize=10)
        ax.set_title('Jobs Performance', fontsize=12, fontweight='bold')
        ax.set_xticks(x_pos)
        
        # Dynamic rotation and spacing for job titles
        if num_jobs > 8:
            step = max(1, num_jobs // 15) if num_jobs > 15 else 1
            ax.set_xticks(x_pos[::step])
            ax.set_xticklabels(jobs[::step], rotation=45, ha='right', fontsize=8)
        elif num_jobs > 5:
            ax.set_xticklabels(jobs, rotation=45, ha='right', fontsize=8)
        else:
            ax.set_xticklabels(jobs, rotation=0, ha='center', fontsize=9)
        
        ax.legend(loc='best', fontsize=8)
        ax.grid(True, alpha=0.3, axis='y')
        
        fig.tight_layout()
        
        img_buffer = io.BytesIO()
        fig.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
        img_buffer.seek(0)
        plt.close(fig)
        
        img = ImageReader(img_buffer)
        chart_height = 200
        c.drawImage(img, margin, y - chart_height, width=width - (2 * margin), height=chart_height, preserveAspectRatio=True, anchor="nw")
        y -= chart_height - 20

    # Jobs Assigned Table - Start on page 3
    if jobs_assigned and len(jobs_assigned) > 0:
        c.showPage()
        _draw_header_footer(c, title, subtitle)
        y = height - 110
        
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, y, "Jobs Assigned")
        y -= 20
        
        # Table headers
        headers = ["Job Title", "Candidates", "Joined"]
        col_widths = [300, 100, 100]
        
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.HexColor("#0f172a"))
        x = margin
        for i, header in enumerate(headers):
            c.drawString(x, y, header[:20])
            x += col_widths[i]
        y -= 15
        
        c.setStrokeColor(colors.HexColor("#e2e8f0"))
        c.line(margin, y, width - margin, y)
        y -= 10
        
        # Table rows - Show ALL data (no truncation)
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.black)
        for row in jobs_assigned:
            if y < 60:
                c.showPage()
                _draw_header_footer(c, title, subtitle)
                y = height - 110
                # Redraw headers
                c.setFont("Helvetica-Bold", 8)
                c.setFillColor(colors.HexColor("#0f172a"))
                x = margin
                for i, header in enumerate(headers):
                    c.drawString(x, y, header[:20])
                    x += col_widths[i]
                y -= 15
                c.setStrokeColor(colors.HexColor("#e2e8f0"))
                c.line(margin, y, width - margin, y)
                y -= 10
                c.setFont("Helvetica", 7)
                c.setFillColor(colors.black)
            
            x = margin
            job_title = str(row.get("job_title", ""))[:35]
            c.drawString(x, y, job_title)
            x += col_widths[0]
            c.drawString(x, y, str(row.get("candidates", 0)))
            x += col_widths[1]
            c.drawString(x, y, str(row.get("joined", 0)))
            y -= 12

    # Recruiter Activity Details Table
    if recruiter_activity_details and len(recruiter_activity_details) > 0:
        # Add vertical separation
        y -= 40
        if y < 200:
            c.showPage()
            _draw_header_footer(c, title, subtitle)
            y = height - 110
        
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, y, "Recruiter Activity Details")
        y -= 20
        
        # Table headers
        headers = ["Activity Type", "Candidate Name", "Remarks", "Date & Time (IST)"]
        col_widths = [100, 120, 200, 120]
        
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.HexColor("#0f172a"))
        x = margin
        for i, header in enumerate(headers):
            c.drawString(x, y, header[:18])
            x += col_widths[i]
        y -= 15
        
        c.setStrokeColor(colors.HexColor("#e2e8f0"))
        c.line(margin, y, width - margin, y)
        y -= 10
        
        # Table rows - Show ALL data (no truncation)
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.black)
        for row in recruiter_activity_details:
            if y < 60:
                c.showPage()
                _draw_header_footer(c, title, subtitle)
                y = height - 110
                # Redraw headers
                c.setFont("Helvetica-Bold", 8)
                c.setFillColor(colors.HexColor("#0f172a"))
                x = margin
                for i, header in enumerate(headers):
                    c.drawString(x, y, header[:18])
                    x += col_widths[i]
                y -= 15
                c.setStrokeColor(colors.HexColor("#e2e8f0"))
                c.line(margin, y, width - margin, y)
                y -= 10
                c.setFont("Helvetica", 7)
                c.setFillColor(colors.black)
            
            x = margin
            activity_type = str(row.get("activity_type", ""))[:18]
            c.drawString(x, y, activity_type)
            x += col_widths[0]
            candidate_name = str(row.get("candidate_name", "N/A"))[:20]
            c.drawString(x, y, candidate_name)
            x += col_widths[1]
            remarks = str(row.get("remarks", ""))[:35]
            c.drawString(x, y, remarks)
            x += col_widths[2]
            created_at = str(row.get("created_at", "N/A"))[:18]
            c.drawString(x, y, created_at)
            y -= 12

    # Login Logs Table
    if login_logs and len(login_logs) > 0:
        # Add vertical separation
        y -= 40
        if y < 200:
            c.showPage()
            _draw_header_footer(c, title, subtitle)
            y = height - 110
        
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, y, "Login Logs")
        y -= 20
        
        # Table headers
        headers = ["Session ID", "Login At (IST)", "Status"]
        col_widths = [200, 150, 80]
        
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.HexColor("#0f172a"))
        x = margin
        for i, header in enumerate(headers):
            c.drawString(x, y, header[:20])
            x += col_widths[i]
        y -= 15
        
        c.setStrokeColor(colors.HexColor("#e2e8f0"))
        c.line(margin, y, width - margin, y)
        y -= 10
        
        # Table rows - Show ALL data (no truncation)
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.black)
        for row in login_logs:
            if y < 60:
                c.showPage()
                _draw_header_footer(c, title, subtitle)
                y = height - 110
                # Redraw headers
                c.setFont("Helvetica-Bold", 8)
                c.setFillColor(colors.HexColor("#0f172a"))
                x = margin
                for i, header in enumerate(headers):
                    c.drawString(x, y, header[:20])
                    x += col_widths[i]
                y -= 15
                c.setStrokeColor(colors.HexColor("#e2e8f0"))
                c.line(margin, y, width - margin, y)
                y -= 10
                c.setFont("Helvetica", 7)
                c.setFillColor(colors.black)
            
            x = margin
            session_id = str(row.get("session_id", ""))[:30]
            c.drawString(x, y, session_id)
            x += col_widths[0]
            login_at = str(row.get("login_at", "N/A"))[:20]
            c.drawString(x, y, login_at)
            x += col_widths[1]
            status = "Active" if row.get("is_active", False) else "Inactive"
            c.drawString(x, y, status)
            y -= 12

    c.showPage()
    _draw_header_footer(c, title, subtitle)
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.HexColor("#666666"))
    c.drawCentredString(width/2, height/2, "END OF REPORT")

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

