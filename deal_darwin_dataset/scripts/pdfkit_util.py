"""Small reportlab helpers shared by the PDF generators."""
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Table, TableStyle)

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("DV", FONT_DIR + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DV-B", FONT_DIR + "DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("DV-I", FONT_DIR + "DejaVuSans-Oblique.ttf"))
pdfmetrics.registerFont(TTFont("DVS", FONT_DIR + "DejaVuSerif.ttf"))
pdfmetrics.registerFont(TTFont("DVS-B", FONT_DIR + "DejaVuSerif-Bold.ttf"))
pdfmetrics.registerFontFamily("DV", normal="DV", bold="DV-B", italic="DV-I", boldItalic="DV-B")
pdfmetrics.registerFontFamily("DVS", normal="DVS", bold="DVS-B", italic="DVS", boldItalic="DVS-B")

INK = colors.HexColor("#1b1b1b")
MUTED = colors.HexColor("#5a5a5a")
RULE = colors.HexColor("#c9c9c9")


def styles(accent="#0B2545", serif=False):
    base = "DVS" if serif else "DV"
    bold = "DVS-B" if serif else "DV-B"
    acc = colors.HexColor(accent)
    return dict(
        title=ParagraphStyle("title", fontName=bold, fontSize=17, leading=22, textColor=acc, spaceAfter=4),
        sub=ParagraphStyle("sub", fontName=base, fontSize=9.5, leading=13, textColor=MUTED, spaceAfter=10),
        h=ParagraphStyle("h", fontName=bold, fontSize=11.5, leading=15, textColor=acc, spaceBefore=10, spaceAfter=4),
        body=ParagraphStyle("body", fontName=base, fontSize=9.6, leading=14, textColor=INK, spaceAfter=6),
        small=ParagraphStyle("small", fontName=base, fontSize=8, leading=11, textColor=MUTED),
        cell=ParagraphStyle("cell", fontName=base, fontSize=8.6, leading=11.5, textColor=INK),
        cellb=ParagraphStyle("cellb", fontName=bold, fontSize=8.6, leading=11.5, textColor=INK),
        clause=ParagraphStyle("clause", fontName=base, fontSize=10, leading=15, textColor=INK,
                              spaceAfter=7, alignment=4),
    )


def table(data, col_widths, header=True, accent="#0B2545", st=None):
    st = st or styles(accent)
    rows = []
    for ri, row in enumerate(data):
        rows.append([Paragraph(str(c), st["cellb"] if (header and ri == 0) else st["cell"]) for c in row])
    t = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f5")))
    t.setStyle(TableStyle(style))
    return t


def make_doc(filename, title, footer):
    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont("DV", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(0.8 * inch, 0.5 * inch, footer)
        canvas.drawRightString(letter[0] - 0.8 * inch, 0.5 * inch, f"Page {doc.page}")
        canvas.restoreState()
    doc = SimpleDocTemplate(filename, pagesize=letter, leftMargin=0.85 * inch, rightMargin=0.85 * inch,
                            topMargin=0.8 * inch, bottomMargin=0.8 * inch, title=title,
                            author="Deal Darwin synthetic dataset (fictional)")
    return doc, on_page
