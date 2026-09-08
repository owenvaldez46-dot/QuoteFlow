import os
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def generate_pdf_bytes(quote, user=None) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    elements = []
    styles = getSampleStyleSheet()

    comp_name = user.get('company_name') if user and user.get('company_name') else "Mi Empresa"
    comp_phone = user.get('company_phone') if user and user.get('company_phone') else ""
    comp_address = user.get('company_address') if user and user.get('company_address') else ""
    logo_path = user.get('company_logo') if user and user.get('company_logo') else None

    logo_img = None
    if logo_path:
        clean_logo_path = logo_path.lstrip('/')
        if os.path.exists(clean_logo_path):
            try:
                logo_img = Image(clean_logo_path, width=110, height=45)
                logo_img.hAlign = 'LEFT'
            except Exception:
                logo_img = None

    company_info_text = f"<b>{comp_name}</b><br/>{comp_address}<br/>{comp_phone}"
    p_company = Paragraph(company_info_text, styles['Normal'])

    quote_info_text = f"<font size=15 color='#2563eb'><b>COTIZACIÓN #{quote['id']:03d}</b></font><br/><br/><b>Fecha:</b> {quote['created_at'][:10]}<br/><b>Estado:</b> {quote['status']}"
    p_quote_info = Paragraph(quote_info_text, ParagraphStyle('RightAlign', parent=styles['Normal'], alignment=2))

    if logo_img:
        header_table = Table([[logo_img, p_company, p_quote_info]], colWidths=[120, 230, 190])
    else:
        header_table = Table([[p_company, p_quote_info]], colWidths=[350, 190])

    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 20))

    p_client = Paragraph(f"<b>Cliente:</b> {quote['client_name']}<br/><b>Email:</b> {quote['client_email'] or 'N/A'}", styles['Normal'])
    elements.append(p_client)
    elements.append(Spacer(1, 15))

    data = [
        ['Servicio / Concepto', 'Descripción', 'Monto Base'],
        [quote['service_title'], quote['description'] or '-', f"${quote['amount']:.2f}"]
    ]
    t = Table(data, colWidths=[180, 260, 100])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2563eb')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 15))

    tax_val = quote['amount'] * (quote['tax_rate'] / 100.0)
    totals_data = [
        ['Subtotal:', f"${quote['amount']:.2f}"],
        [f'Impuesto ({quote["tax_rate"]}%):', f"${tax_val:.2f}"],
        ['Total:', f"${quote['total_amount']:.2f}"]
    ]
    tot_table = Table(totals_data, colWidths=[440, 100])
    tot_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
        ('FONTNAME', (0,2), (1,2), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0,2), (1,2), colors.HexColor('#1e293b')),
        ('LINEABOVE', (0,2), (1,2), 1, colors.HexColor('#2563eb')),
    ]))
    elements.append(tot_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()