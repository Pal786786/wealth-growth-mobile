"""Premium PDF + Excel generators for My Funding Bank wallet.

Design: navy + gold premium fintech receipt with bull mark + QR code.
"""
from __future__ import annotations
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Brand palette
NAVY = colors.HexColor("#0A1428")
NAVY_DARK = colors.HexColor("#040813")
SKY = colors.HexColor("#38BDF8")
GOLD = colors.HexColor("#D4AF37")
GOLD_LIGHT = colors.HexColor("#F0CC5C")
MUTED = colors.HexColor("#94A3B8")
WHITE = colors.HexColor("#FFFFFF")
GREEN = colors.HexColor("#10B981")
RED = colors.HexColor("#EF4444")


def _qr_image(data: str, size_mm: float = 25.0) -> BytesIO:
    qr = qrcode.QRCode(version=1, box_size=4, border=1)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0A1428", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _fmt_inr(n: float) -> str:
    sign = "-" if n < 0 else ""
    n = abs(n)
    s = f"{n:,.2f}"
    # Indian numbering: 12,34,567.89
    if '.' in s:
        int_part, dec = s.split('.')
    else:
        int_part, dec = s, "00"
    int_part = int_part.replace(",", "")
    if len(int_part) > 3:
        last3 = int_part[-3:]
        rest = int_part[:-3]
        groups: list = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        int_part = ",".join(groups) + "," + last3
    return f"\u20b9 {sign}{int_part}.{dec}"


def _draw_header(c: canvas.Canvas, doc_w: float, title: str, subtitle: str = ""):
    """Premium navy band with gold bull mark + brand."""
    c.setFillColor(NAVY)
    c.rect(0, A4[1] - 35 * mm, doc_w, 35 * mm, fill=True, stroke=False)
    # gold accent stripe
    c.setFillColor(GOLD)
    c.rect(0, A4[1] - 36 * mm, doc_w, 1 * mm, fill=True, stroke=False)

    # Bull mark (mini, geometric — same vibe as web navbar)
    cx, cy = 20 * mm, A4[1] - 17 * mm
    c.setFillColor(GOLD)
    c.circle(cx, cy, 8 * mm, fill=True, stroke=False)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(cx, cy - 4, "MFB")

    # Brand text
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(34 * mm, A4[1] - 14 * mm, "My Funding Bank")
    c.setFillColor(GOLD_LIGHT)
    c.setFont("Helvetica", 9)
    c.drawString(34 * mm, A4[1] - 19 * mm, "Where Wealth Meets Intelligence")

    # Title block (right)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(doc_w - 15 * mm, A4[1] - 14 * mm, title)
    if subtitle:
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8)
        c.drawRightString(doc_w - 15 * mm, A4[1] - 19 * mm, subtitle)


def _draw_footer(c: canvas.Canvas, doc_w: float, page_num: int):
    c.setFillColor(NAVY)
    c.rect(0, 0, doc_w, 12 * mm, fill=True, stroke=False)
    c.setFillColor(GOLD)
    c.rect(0, 12 * mm, doc_w, 0.5 * mm, fill=True, stroke=False)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7)
    c.drawString(15 * mm, 5 * mm,
                 "This is a computer-generated document. No signature required. "
                 "For queries: support@myfundingbank.com")
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(GOLD_LIGHT)
    c.drawRightString(doc_w - 15 * mm, 5 * mm, f"Page {page_num}")


# ---------- Receipt PDF ----------
def build_receipt_pdf(tx: Dict[str, Any], user: Dict[str, Any], wallet_balance: float) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    _draw_header(c, W, "Transaction Receipt",
                 f"Receipt # {tx.get('tx_id', '—')}")

    # Status pill (top center)
    status = (tx.get("status") or "").upper()
    pill_color = GREEN if status == "SUCCESS" else GOLD if status == "PENDING" else RED
    c.setFillColor(pill_color)
    c.roundRect(W / 2 - 25 * mm, H - 55 * mm, 50 * mm, 8 * mm, 4 * mm, fill=True, stroke=False)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(W / 2, H - 50 * mm, status)

    # Amount (huge, centered)
    sign = "-" if tx.get("type") == "debit" else "+"
    color = RED if tx.get("type") == "debit" else GREEN
    c.setFillColor(NAVY_DARK)
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(W / 2, H - 80 * mm, f"{sign}{_fmt_inr(tx.get('amount', 0))}")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 9)
    c.drawCentredString(W / 2, H - 86 * mm,
                        (tx.get("description") or "").upper())

    # Detail rows (left card)
    rows = [
        ("Transaction ID", tx.get("tx_id", "—")),
        ("Date & Time",
         (tx.get("created_at") or datetime.utcnow()).strftime("%d %b %Y, %I:%M %p IST")),
        ("Type", (tx.get("type") or "").upper()),
        ("Category", (tx.get("category") or "").replace("_", " ").title()),
        ("Counterparty", str(tx.get("counterparty") or "—")),
        ("Amount", _fmt_inr(tx.get("amount", 0))),
        ("Status", status),
    ]
    if tx.get("provider"):
        rows.append(("Provider", str(tx["provider"]).title()))
    if tx.get("reference_id"):
        rows.append(("Reference", str(tx["reference_id"])))

    y = H - 105 * mm
    box_x = 20 * mm
    box_w = W - 80 * mm
    box_h = len(rows) * 7 * mm + 8 * mm
    c.setFillColor(colors.HexColor("#F8FAFC"))
    c.setStrokeColor(colors.HexColor("#E2E8F0"))
    c.roundRect(box_x, y - box_h, box_w, box_h, 3 * mm, fill=True, stroke=True)
    yy = y - 8 * mm
    c.setFont("Helvetica", 9)
    for k, v in rows:
        c.setFillColor(MUTED)
        c.drawString(box_x + 6 * mm, yy, k)
        c.setFillColor(NAVY_DARK)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(box_x + 55 * mm, yy, str(v))
        c.setFont("Helvetica", 9)
        yy -= 7 * mm

    # QR (right) — encodes a verification URL
    qr_buf = _qr_image(f"MFB-VERIFY-{tx.get('tx_id', '')}")
    qr_x = W - 50 * mm
    qr_y = y - 50 * mm
    c.drawImage(ImageReader(qr_buf), qr_x, qr_y, width=30 * mm, height=30 * mm,
                mask='auto', preserveAspectRatio=True)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7)
    c.drawCentredString(qr_x + 15 * mm, qr_y - 4 * mm, "Scan to verify")

    # Customer block
    cy_top = qr_y - 18 * mm
    c.setFillColor(NAVY_DARK)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(box_x, cy_top, "Account Holder")
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawString(box_x, cy_top - 5 * mm, user.get("full_name", "—"))
    c.drawString(box_x, cy_top - 10 * mm,
                 f"{user.get('email', '—')}  ·  {user.get('mobile', '—')}")
    c.drawString(box_x, cy_top - 15 * mm, f"User ID: {user.get('user_id', '—')}")

    # Wallet balance after txn
    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(box_x, cy_top - 25 * mm,
                 f"Wallet Balance after transaction: {_fmt_inr(wallet_balance)}")

    _draw_footer(c, W, 1)
    c.showPage()
    c.save()
    return buf.getvalue()


# ---------- Statement PDF ----------
def build_statement_pdf(transactions: List[Dict[str, Any]], user: Dict[str, Any],
                       summary: Dict[str, float], period_label: str) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=50 * mm, bottomMargin=18 * mm,
                            leftMargin=15 * mm, rightMargin=15 * mm)

    styles = getSampleStyleSheet()
    h2 = ParagraphStyle('h2', parent=styles['Normal'], fontName='Helvetica-Bold',
                        fontSize=12, textColor=NAVY_DARK, spaceAfter=4 * mm)
    small = ParagraphStyle('small', parent=styles['Normal'], fontName='Helvetica',
                           fontSize=8, textColor=MUTED)
    bold = ParagraphStyle('bold', parent=styles['Normal'], fontName='Helvetica-Bold',
                          fontSize=9, textColor=NAVY_DARK)

    story: list = []
    story.append(Paragraph(
        f"<b>Account Holder:</b> {user.get('full_name', '—')} &nbsp;&nbsp; "
        f"<b>User ID:</b> {user.get('user_id', '—')}", styles['Normal']))
    story.append(Paragraph(
        f"{user.get('email', '—')} · {user.get('mobile', '—')}", small))
    story.append(Spacer(1, 5 * mm))

    # Summary tiles
    summary_data = [
        ["OPENING BAL", "DEPOSITS", "WITHDRAWALS", "CASHBACK", "CLOSING BAL"],
        [_fmt_inr(summary.get("opening_balance", 0)),
         _fmt_inr(summary.get("total_deposits", 0)),
         _fmt_inr(summary.get("total_withdrawals", 0)),
         _fmt_inr(summary.get("total_cashback", 0)),
         _fmt_inr(summary.get("closing_balance", 0))],
    ]
    t = Table(summary_data, colWidths=[36 * mm] * 5)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), GOLD_LIGHT),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor("#F8FAFC")),
        ('TEXTCOLOR', (0, 1), (-1, 1), NAVY_DARK),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, 1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
    ]))
    story.append(t)
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph(f"<b>Transactions · {period_label}</b>", h2))
    head = ["Date", "Tx ID", "Type", "Category", "Description", "Status", "Amount"]
    rows = [head]
    for tx in transactions:
        sign = "-" if tx.get("type") == "debit" else "+"
        rows.append([
            (tx.get("created_at") or datetime.utcnow()).strftime("%d %b\n%I:%M %p"),
            tx.get("tx_id", "—")[:14],
            (tx.get("type") or "").upper(),
            (tx.get("category") or "").replace("_", " ").title()[:14],
            (tx.get("description") or "—")[:32],
            (tx.get("status") or "").upper(),
            f"{sign}{_fmt_inr(tx.get('amount', 0)).replace('₹ ', '₹')}",
        ])
    if len(rows) == 1:
        rows.append(["—"] * 7)

    tx_table = Table(rows, repeatRows=1,
                     colWidths=[20 * mm, 30 * mm, 16 * mm, 22 * mm, 50 * mm, 18 * mm, 26 * mm])
    tx_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), GOLD_LIGHT),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 7.5),
        ('TEXTCOLOR', (0, 1), (-1, -1), NAVY_DARK),
        ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F8FAFC")]),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(tx_table)

    # Header/footer on every page
    def on_page(c, _doc):
        _draw_header(c, A4[0], "Wallet Statement", period_label)
        _draw_footer(c, A4[0], _doc.page)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


# ---------- Statement Excel ----------
def build_statement_xlsx(transactions: List[Dict[str, Any]], user: Dict[str, Any],
                        summary: Dict[str, float], period_label: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Statement"

    # Header styling helpers
    navy = PatternFill("solid", fgColor="0A1428")
    gold = PatternFill("solid", fgColor="D4AF37")
    soft = PatternFill("solid", fgColor="F8FAFC")
    bold = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    head_gold = Font(name="Calibri", size=10, bold=True, color="0A1428")
    body = Font(name="Calibri", size=10, color="0A1428")
    center = Alignment(horizontal="center", vertical="center")
    right = Alignment(horizontal="right")
    thin = Side(style="thin", color="E2E8F0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # Brand band
    ws.merge_cells("A1:G1")
    ws["A1"] = "My Funding Bank — Wallet Statement"
    ws["A1"].fill = navy
    ws["A1"].font = Font(name="Calibri", size=14, bold=True, color="D4AF37")
    ws["A1"].alignment = center
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:G2")
    ws["A2"] = period_label
    ws["A2"].fill = gold
    ws["A2"].font = head_gold
    ws["A2"].alignment = center

    # User block
    ws["A4"] = "Account Holder:"
    ws["B4"] = user.get("full_name", "—")
    ws["A5"] = "User ID:"; ws["B5"] = user.get("user_id", "—")
    ws["A6"] = "Email:"; ws["B6"] = user.get("email", "—")
    ws["A7"] = "Mobile:"; ws["B7"] = user.get("mobile", "—")
    for r in range(4, 8):
        ws.cell(r, 1).font = Font(name="Calibri", size=10, bold=True, color="0A1428")

    # Summary grid
    ws["D4"] = "Opening"; ws["E4"] = summary.get("opening_balance", 0)
    ws["D5"] = "Deposits"; ws["E5"] = summary.get("total_deposits", 0)
    ws["D6"] = "Withdrawals"; ws["E6"] = summary.get("total_withdrawals", 0)
    ws["D7"] = "Cashback"; ws["E7"] = summary.get("total_cashback", 0)
    ws["F4"] = "Closing"; ws["G4"] = summary.get("closing_balance", 0)
    for r in range(4, 8):
        ws.cell(r, 4).font = Font(name="Calibri", size=10, bold=True, color="D4AF37")
        ws.cell(r, 6).font = Font(name="Calibri", size=10, bold=True, color="D4AF37")
        for col in (5, 7):
            cell = ws.cell(r, col)
            cell.number_format = '"₹ "#,##0.00'
            cell.font = bold
            cell.fill = navy
            cell.alignment = right

    # Transactions table
    head_row = 9
    headers = ["Date", "Transaction ID", "Type", "Category", "Description", "Status", "Amount"]
    for i, h in enumerate(headers, 1):
        cell = ws.cell(head_row, i, h)
        cell.fill = navy; cell.font = bold; cell.alignment = center; cell.border = border

    for ri, tx in enumerate(transactions, start=head_row + 1):
        dt = tx.get("created_at") or datetime.utcnow()
        sign = -1 if tx.get("type") == "debit" else 1
        cells = [
            dt.strftime("%d %b %Y %H:%M"),
            tx.get("tx_id", "—"),
            (tx.get("type") or "").upper(),
            (tx.get("category") or "").replace("_", " ").title(),
            tx.get("description", "—"),
            (tx.get("status") or "").upper(),
            sign * float(tx.get("amount", 0)),
        ]
        for ci, val in enumerate(cells, 1):
            cell = ws.cell(ri, ci, val)
            cell.font = body; cell.border = border
            if ri % 2 == 0:
                cell.fill = soft
            if ci == 7:
                cell.number_format = '"₹ "#,##0.00;[Red]-"₹ "#,##0.00'
                cell.alignment = right

    widths = [22, 18, 12, 16, 36, 14, 18]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    out = BytesIO()
    wb.save(out)
    return out.getvalue()


# ---------- Admin transactions CSV ----------
def build_admin_tx_csv(transactions: List[Dict[str, Any]]) -> bytes:
    import csv
    from io import StringIO
    s = StringIO()
    w = csv.writer(s)
    w.writerow(["tx_id", "user_id", "type", "category", "amount", "status",
                "provider", "reference_id", "counterparty", "description", "created_at"])
    for tx in transactions:
        w.writerow([
            tx.get("tx_id", ""), tx.get("user_id", ""),
            tx.get("type", ""), tx.get("category", ""),
            tx.get("amount", 0), tx.get("status", ""),
            tx.get("provider", "") or "", tx.get("reference_id", "") or "",
            tx.get("counterparty", "") or "",
            (tx.get("description", "") or "").replace("\n", " "),
            (tx.get("created_at") or datetime.utcnow()).isoformat(),
        ])
    return s.getvalue().encode("utf-8")
