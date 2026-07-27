import io
import math
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.graphics.shapes import Drawing, Circle, Path, Group
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.lineplots import LinePlot 

def draw_optima_logo() -> Drawing:
    """Draws the PyMudCement Optima Pro SVG emblem for the ReportLab PDF header."""
    d = Drawing(80, 80)
    
    # Scale transformation factor: 80px target height / 1200px SVG viewbox = 0.0667
    g = Group()
    g.scale(0.0667, 0.0667)
    
    # 1. Outer Dark Ring / Gear Element
    ring = Circle(600, 470, 210)
    ring.fillColor = None
    ring.strokeColor = colors.HexColor("#49576D")
    ring.strokeWidth = 45
    g.add(ring)
    
    # 2. Left Blue Swirl (Mud Hydro)
    blue_swirl = Path(fillColor=colors.HexColor("#0A4EA8"), strokeColor=None)
    blue_swirl.moveTo(600, 120)
    blue_swirl.curveTo(470, 270, 430, 380, 455, 520)
    blue_swirl.curveTo(475, 660, 560, 760, 600, 790)
    blue_swirl.curveTo(530, 650, 520, 480, 600, 120)
    g.add(blue_swirl)
    
    # 3. Right Gold Swirl (Cement Hydro)
    gold_swirl = Path(fillColor=colors.HexColor("#C88400"), strokeColor=None)
    gold_swirl.moveTo(600, 120)
    gold_swirl.curveTo(720, 260, 760, 380, 735, 520)
    gold_swirl.curveTo(710, 650, 640, 740, 600, 790)
    gold_swirl.curveTo(680, 620, 680, 450, 600, 120)
    g.add(gold_swirl)
    
    d.add(g)
    return d 

def create_pressure_drop_chart(results: dict) -> Drawing:
    """Renders a pressure drop breakdown bar chart."""
    drawing = Drawing(240, 140)
    chart = VerticalBarChart()
    chart.x = 35
    chart.y = 20
    chart.height = 100
    chart.width = 190
    
    spp = float(results.get("standpipe_pressure_spp_psi", 0.0))
    annular_loss = float(results.get("total_annular_pressure_loss_psi", 0.0))
    pipe_loss = max(0.0, spp - annular_loss)
    
    chart.data = [[annular_loss, pipe_loss, spp]]
    chart.categoryAxis.categoryNames = ['Annular', 'Pipe', 'Total SPP']
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.dy = -8
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontSize = 7
    chart.bars[0].fillColor = colors.HexColor("#1976D2")
    
    drawing.add(chart)
    return drawing 

def create_rheology_curve(pv: float = 20.0, yp: float = 15.0) -> Drawing:
    """Generates a Shear Stress vs. Shear Rate Rheology Plot."""
    drawing = Drawing(240, 140)
    plot = LinePlot()
    plot.x = 35
    plot.y = 20
    plot.height = 100
    plot.width = 190
    
    shear_rates = [100 * i for i in range(1, 11)]
    shear_stresses = [yp + pv * (sr / 1022.0) for sr in shear_rates]
    
    plot.data = [list(zip(shear_rates, shear_stresses))]
    plot.lines[0].strokeColor = colors.HexColor("#D89B00")
    plot.lines[0].strokeWidth = 2
    
    plot.xValueAxis.valueMin = 0
    plot.xValueAxis.valueMax = 1000
    plot.xValueAxis.labels.fontSize = 7
    plot.yValueAxis.valueMin = 0
    plot.yValueAxis.labels.fontSize = 7
    
    drawing.add(plot)
    return drawing 

def generate_hydraulics_pdf(
    results: dict, 
    diagnostic_report: dict, 
    executed_by: str, 
    segments: list = None,
    pv: float = 20.0,
    yp: float = 15.0
) -> io.BytesIO:
    """Generates an official PDF report embedding the integrated SVG vector logo header."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter, 
        rightMargin=36, 
        leftMargin=36, 
        topMargin=36, 
        bottomMargin=36
    )
    story = []
    styles = getSampleStyleSheet() 

    PRIMARY_BLUE = colors.HexColor("#1976D2")
    DARK_TEXT = colors.HexColor("#1E293B") 

    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=20, textColor=PRIMARY_BLUE, spaceAfter=2)
    sub_title_style = ParagraphStyle('DocSubTitle', parent=styles['Normal'], fontSize=8, textColor=DARK_TEXT, fontName='Helvetica-Bold', spaceAfter=10) 

    # 1. Header with integrated SVG logo emblem
    logo_drawing = draw_optima_logo()
    header_table = Table([[logo_drawing, [
        Paragraph("<b>PyMud<font color='#D89B00'>Cement</font></b>", title_style),
        Paragraph("OPTIMA PRO — DRILLING HYDRAULICS & AI DIAGNOSTICS REPORT", sub_title_style)
    ]]], colWidths=[90, 450])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8)
    ]))
    story.append(header_table)
    story.append(Spacer(1, 8)) 

    # 2. Metadata Block
    meta_data = [
        ["Executed By:", executed_by, "Status:", diagnostic_report.get("status", "SUCCESS")],
        ["Severity:", diagnostic_report.get("severity", "GREEN"), "Matched Hazard:", diagnostic_report.get("matched_hazard", "None")]
    ]
    t_meta = Table(meta_data, colWidths=[90, 180, 90, 180])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
        ('TEXTCOLOR', (0,0), (-1,-1), DARK_TEXT),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0"))
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 12)) 

    # 3. Multi-Segment Well Geometry
    story.append(Paragraph("<b>1. Multi-Segment Wellbore Geometry</b>", styles['Heading2']))
    if not segments:
        segments = [
            {"name": "Drill Pipe", "top_md": 0, "bottom_md": 7000, "pipe_od": 5.0, "pipe_id": 4.276, "hole_id": 8.5},
            {"name": "HWDP", "top_md": 7000, "bottom_md": 8000, "pipe_od": 5.0, "pipe_id": 3.0, "hole_id": 8.5}
        ]
        
    geom_data = [["Segment Name", "Top MD (ft)", "Bottom MD (ft)", "Pipe OD (in)", "Pipe ID (in)", "Hole ID (in)"]]
    for seg in segments:
        geom_data.append([
            seg.get("name", "Segment"),
            f"{seg.get('top_md', 0):.0f}",
            f"{seg.get('bottom_md', 0):.0f}",
            f"{seg.get('pipe_od', 0.0):.3f}",
            f"{seg.get('pipe_id', 0.0):.3f}",
            f"{seg.get('hole_id', 0.0):.3f}"
        ])
        
    t_geom = Table(geom_data, colWidths=[110, 85, 85, 85, 85, 90])
    t_geom.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY_BLUE),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_geom)
    story.append(Spacer(1, 12)) 

    # 4. Pressure Loss & Rheology Charts Side-by-Side
    story.append(Paragraph("<b>2. Hydraulics & Rheology Visualizations</b>", styles['Heading2']))
    chart_p_loss = create_pressure_drop_chart(results)
    chart_rheo = create_rheology_curve(pv=pv, yp=yp)
    
    viz_table = Table([[
        [Paragraph("<b>Pressure Loss Breakdown</b>", styles['Normal']), chart_p_loss],
        [Paragraph("<b>Rheology Curve (Rheogram)</b>", styles['Normal']), chart_rheo]
    ]], colWidths=[270, 270])
    viz_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER')
    ]))
    story.append(viz_table)
    story.append(Spacer(1, 10)) 

    # 5. Diagnostics
    story.append(Paragraph("<b>3. AI Diagnostics & Action Blueprint</b>", styles['Heading2']))
    story.append(Paragraph(f"<b>Diagnosis:</b> {diagnostic_report.get('detailed_diagnosis', 'Normal Operating Envelope.')}", styles['Normal']))
    story.append(Spacer(1, 4))
    
    recs = diagnostic_report.get("actionable_recommendations", [])
    if recs:
        story.append(Paragraph("<b>Action Blueprint:</b>", styles['Normal']))
        for rec in recs:
            story.append(Paragraph(f"• {rec}", styles['Normal'])) 

    doc.build(story)
    buffer.seek(0)
    return buffer
