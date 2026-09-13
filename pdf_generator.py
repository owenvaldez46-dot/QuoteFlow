import io
import urllib.request
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

def generate_pdf_bytes(quote: dict, user: dict = None) -> bytes:
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
    
    # Estilos personalizados
    normal_style = styles['Normal']
    bold_style = ParagraphStyle('BoldText', parent=styles['Normal'], fontName='Helvetica-Bold')
    
    # --- Manejo seguro de la fecha created_at ---
    created_at_val = quote.get('created_at')
    if isinstance(created_at_val, datetime):
        fecha_str = created_at_val.strftime("%Y-%m-%d")
    elif created_at_val:
        fecha_str = str(created_at_val)[:10]
    else:
        fecha_str = datetime.now().strftime("%Y-%m-%d")

    # --- Datos de la Empresa (Usuario) ---
    company_name = user.get('company_name') if user and user.get('company_name') else "Mi Empresa"
    company_phone = user.get('company_phone') if user and user.get('company_phone') else ""
    company_address = user.get('company_address') if user and user.get('company_address') else ""
    company_logo_url = user.get('company_logo') if user else None

    logo_img = None
    if company_logo_url:
        try:
            img_data = urllib.request.urlopen(company_logo_url).read()
            img_buffer = io.BytesIO(img_data)
            logo_img = Image(img_buffer, width=100, height=50)
        except Exception:
            logo_img = None

    company_info_text = f"<b>{company_name}</b><br/>"
    if company_address:
        company_info_text += f"{company_address}<br/>"
    if company_phone:
        company_info_text += f"Tel: {company_phone}<br/>"

    quote_id = quote.get('id', 0)
    status = quote.get('status', 'Pendiente')

    quote_info_text = (
        f"<font size=15 color='#2563eb'><b>COTIZACIÓN #{quote_id:03d}</b></font><br/><br/>"
        f"<b>Fecha:</b> {fecha_str}<br/>"
        f"<b>Estado:</b> {status}"
    )

    if logo_img:
        left_cell = Table([[logo_img], [Paragraph(company_info_text, normal_style)]], colWidths=[200])
    else:
        left_cell = Paragraph(company_info_text, normal_style)

    header_table = Table([[left_cell, Paragraph(quote_info_text, normal_style)]], colWidths=[300, 240])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    
    story.append(header_table)
    story.append(Spacer(1, 20))

    # --- Datos del Cliente ---
    client_name = quote.get('client_name', 'N/A')
    client_email = quote.get('client_email', '')
    client_text = f"<b>COTIZADO A:</b><br/><font size=11><b>{client_name}</b></font>"
    if client_email:
        client_text += f"<br/>{client_email}"
    
    story.append(Paragraph(client_text, normal_style))
    story.append(Spacer(1, 15))

    # --- Detalle del Servicio ---
    service_title = quote.get('service_title', 'Servicio General')
    description = quote.get('description', '')
    
    items_data = [
        [Paragraph("<b>Descripción del Servicio</b>", bold_style), Paragraph("<b>Monto</b>", bold_style)]
    ]

    desc_content = f"<b>{service_title}</b>"
    if description:
        desc_content += f"<br/><font size=9 color='#6b7280'>{description}</font>"

    amount = float(quote.get('amount', 0.0))
    tax_rate = float(quote.get('tax_rate', 0.0))
    total_amount = float(quote.get('total_amount', amount + (amount * tax_rate / 100.0)))
    tax_amount = total_amount - amount

    items_data.append([Paragraph(desc_content, normal_style), Paragraph(f"${amount:,.2f}", normal_style)])

    table_items = Table(items_data, colWidths=[400, 140])
    table_items.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f4f6')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
    ]))

    story.append(table_items)
    story.append(Spacer(1, 15))

    # --- Totales ---
    summary_data = [
        [Paragraph("Subtotal:", normal_style), Paragraph(f"${amount:,.2f}", normal_style)],
        [Paragraph(f"Impuesto ({tax_rate:.1f}%):", normal_style), Paragraph(f"${tax_amount:,.2f}", normal_style)],
        [Paragraph("<b>Total:</b>", bold_style), Paragraph(f"<b>${total_amount:,.2f}</b>", bold_style)]
    ]

    summary_table = Table(summary_data, colWidths=[400, 140])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LINEABOVE', (0, 2), (-1, 2), 1, colors.HexColor('#2563eb')),
    ]))

    story.append(summary_table)

    # Construir documento PDF
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    return pdf_bytes
