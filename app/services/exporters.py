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
    
    # Draw line after graph
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.setLineWidth(1)
    c.line(x_start, final_y, x_start + chart_width, final_y)
    
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
) -> float:
    """
    Draw a line graph showing average time in days for each pipeline stage, Accepted, and Rejected.
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
    
    if not all_labels:
        return y_pos
    
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
) -> float:
    """
    Draw a line graph showing pipeline velocity (movement per day).
    """
    y_bottom = y_pos - chart_height
    y_top = y_pos - 40
    
    if not velocity_data:
        return y_pos
    
    # Sort by date
    sorted_data = sorted(velocity_data, key=lambda x: x.get("label", ""))
    
    # Prepare labels and values
    labels = []
    values = []
    for item in sorted_data:
        label = item.get("label", "")
        # Format date label (truncate if needed)
        if len(label) > 8:
            label = label[-5:]  # Take last 5 chars (e.g., "01-15")
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
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.black)
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
    if not labels:
        return y_pos

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

    # IST Conversion
    utc_now = datetime.now(timezone.utc)
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
        
        # Job Title
        job_title = job_metadata.get("job_title", "N/A")
        c.drawString(40, y, f"Job Title: {job_title}")
        y -= 16
        
        # Company Name
        company_name = job_metadata.get("company_name", "N/A")
        c.drawString(40, y, f"Company Name: {company_name}")
        y -= 16
        
        # Job Creation Date
        created_at = job_metadata.get("created_at")
        if created_at:
            if isinstance(created_at, datetime):
                created_at_str = created_at.strftime("%d %b %Y")
            else:
                created_at_str = str(created_at)
        else:
            created_at_str = "N/A"
        c.drawString(40, y, f"Job Creation Date: {created_at_str}")
        y -= 16
        
        # Status
        status = job_metadata.get("status", "N/A")
        c.drawString(40, y, f"Status: {status}")
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
        
        # Left graph: Avg Time per Stage
        graph_y = y
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(margin, graph_y, "Avg Time in Each Stage (Days)")
        graph_y -= 15
        y_left = _draw_avg_time_line_graph(c, graph_y, stage_times, avg_accepted, avg_rejected, chart_width, chart_height, margin)
        
        # Right graph: Pipeline Velocity
        x_right_start = margin + chart_width + margin
        graph_y = y
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(x_right_start, graph_y, "Pipeline Velocity (Movement per Day)")
        graph_y -= 15
        y_right = _draw_velocity_line_graph(c, graph_y, velocity_data, chart_width, chart_height, x_right_start)
        
        # Use the lower Y position
        y = min(y_left, y_right) - 20
        
        # Draw line after graphs
        c.setStrokeColor(colors.HexColor("#e2e8f0"))
        c.setLineWidth(1)
        c.line(margin, y, width - margin, y)
        y -= 30
        
        # Draw Pipeline Flow graph (Joined vs Rejected)
        joined_datewise_data = extras.get("joined_datewise", []) if extras else []
        rejected_datewise_data = extras.get("rejected_datewise", []) if extras else []
        if joined_datewise_data or rejected_datewise_data:
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
        recruiter_assignments = recruiter_metrics.get("recruiter_assignments") or []
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
                assigned_val = total_assigned.get("assigned", 0)
                c.drawString(width - 210, y, str(assigned_val))
                c.drawString(width - 90, y, str(closed))
                y -= 15
            
            y -= 10
            c.setStrokeColor(colors.HexColor("#e2e8f0"))
            c.line(margin, y, width - margin, y)
            y -= 20
        
        # Recruiter assignment table
        if recruiter_assignments:
            if y < 180:
                c.showPage()
                _draw_header_footer(c, title, subtitle)
                y = height - 110
            c.setFillColor(colors.HexColor("#0f172a"))
            c.setFont("Helvetica-Bold", 12)
            c.drawString(margin, y, "Recruiter Assignments")
            y -= 18
            c.setFont("Helvetica-Bold", 9)
            headers = ["Recruiter", "Assigned", "Joined", "Rejected/Dropped"]
            col_widths = [180, 80, 80, 110]
            current_x = margin
            for w, h in zip(col_widths, headers):
                c.drawString(current_x, y, h)
                current_x += w
            y -= 10
            c.setStrokeColor(colors.HexColor("#e2e8f0"))
            c.line(margin, y, width - margin, y)
            y -= 12
            c.setFont("Helvetica", 9)
            for row in recruiter_assignments:
                if y < 70:
                    c.showPage()
                    _draw_header_footer(c, title, subtitle)
                    y = height - 110
                    c.setFillColor(colors.HexColor("#0f172a"))
                    c.setFont("Helvetica-Bold", 12)
                    c.drawString(margin, y, "Recruiter Assignments")
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
                    row.get("recruiter_name", "N/A")[:28] + ("..." if len(str(row.get("recruiter_name",""))) > 28 else ""),
                    str(row.get("assigned", 0)),
                    str(row.get("joined", 0)),
                    str(row.get("rejected", 0)),
                ]
                current_x = margin
                for w, v in zip(col_widths, vals):
                    c.drawString(current_x, y, v)
                    current_x += w
                y -= 14
            y -= 16
            c.setStrokeColor(colors.HexColor("#e2e8f0"))
            c.line(margin, y, width - margin, y)
            y -= 18

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
    clawback_metrics = extras.get("clawback_metrics", {}) if extras else {}
    if clawback_metrics:
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

        # Clawback Completed Today table
        completed_today = clawback_metrics.get("completed_today", [])
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
            y -= 14

        # Clawback Drop or Rejected Today
        drop_today = clawback_metrics.get("drop_today", [])
        if drop_today:
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

        # Clawback candidate details table (all cases)
        clawback_details = clawback_metrics.get("all_cases", [])
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

