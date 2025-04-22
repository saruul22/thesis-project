import csv
import datetime
from io import BytesIO
import xlsxwriter
from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from face_authentication.models import WeaponTransaction

def export_transactions_csv(request):
    """CSV formataar transactionuudaa export hiine"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="transactions_{datetime.date.today()}.csv"'

    # Transactioniihaa datag avna - filtertei baij bolno
    transactions = WeaponTransaction.objects.select_related('weapon', 'personnel').order_by('-timestamp')

    # Apply date filters if provided
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if start_date:
        transactions = transactions.filter(timestamp__date__gte=start_date)

    if end_date:
        transactions = transactions.filter(timestamp__date__lte=end_date)

    # Create CSV writer
    writer = csv.writer(response)
    writer.writerow(['Transaction ID', 'Date/Time', 'Type', 'Weapon', 'Personnel', 'Verified By'])

    # Data rows nemne
    for transaction in transactions:
        writer.writerow([
            str(transaction.id),
            transaction.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            transaction.get_transaction_type_display(),
            f"{transaction.weapon.weapon_model} - {transaction.weapon.serial_number}",
            f"{transaction.personnel.rank} {transaction.personnel.first_name} {transaction.personnel.last_name}",
            transaction.verified_by or 'N/A'
        ])

    return response

def export_transactions_excel(request):
    """Excel file bolgoj exportolno"""
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {'remove_timezone': True})
    worksheet = workbook.add_worksheet('Transactions')

    # Header format
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4472C4',
        'color': 'white',
        'border': 1
    })

    # Data format nemeh
    date_format = workbook.add_format({'num_format': 'yyyy-mm-dd hh:mm:ss'})

    # Write headers
    headers = ['Transaction ID', 'Date/Time', 'Type', 'Weapon', 'Personnel', 'Verified By']
    for col_num, header in enumerate(headers):
        worksheet.write(0, col_num, header, header_format)

    # Transaction data avah
    transactions = WeaponTransaction.objects.select_related('weapon', 'personnel').order_by('-timestamp')

    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if start_date:
        transactions = transactions.filter(timestamp__date__gte=start_date)

    if end_date:
        transactions = transactions.filter(timestamp__date__lte=end_date)

    # Write data rows
    for row_num, transaction in enumerate(transactions, 1):
        worksheet.write(row_num, 0, str(transaction.id))
        worksheet.write_datetime(row_num, 1, transaction.timestamp, date_format)
        worksheet.write(row_num, 2, transaction.get_transaction_type_display())
        worksheet.write(row_num, 3, f"{transaction.weapon.weapon_model} - {transaction.weapon.serial_number}")
        worksheet.write(row_num, 4, f"{transaction.personnel.rank} {transaction.personnel.first_name} {transaction.personnel.last_name}")
        worksheet.write(row_num, 5, transaction.verified_by or 'N/A')

    # Col width
    for i, width in enumerate([36, 20, 15, 25, 30, 20]):
        worksheet.set_column(i, i, width)

    workbook.close()
    output.seek(0)

    # Create response
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="transactions_{datetime.date.today()}.xlsx"'

    return response

def export_transactions_pdf(request):
    """PDF file aar gargah"""
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="transactions_{datetime.date.today()}.pdf"'

    # Create PDF document
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    elements = []

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    pdfmetrics.registerFont(TTFont('DejaVuSans', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))

    # Define styles
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    title_style.fontName = 'DejaVuSans'

    normal_style = styles['Normal']
    normal_style.fontName = 'DejaVuSans'

    # Add title
    elements.append(Paragraph("Weapon Transactions Report", title_style))
    elements.append(Paragraph(f"Generated on: {datetime.date.today()}", normal_style))

    # Transaction data avah
    transactions = WeaponTransaction.objects.select_related('weapon', 'personnel').order_by('-timestamp')

    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if start_date:
        transactions = transactions.filter(timestamp__date__gte=start_date)

    if end_date:
        transactions = transactions.filter(timestamp__date__lte=end_date)

    # Create table data
    data = [['Transaction ID', 'Огноо', 'Төрөл', 'Галт зэвсэг', 'Алба хаагч', 'Хянасан']]

    # Add data rows
    for transaction in transactions:
        data.append([
            str(transaction.id),
            transaction.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            transaction.get_transaction_type_display(),
            f"{transaction.weapon.weapon_model} - {transaction.weapon.serial_number}",
            f"{transaction.personnel.rank} {transaction.personnel.first_name} {transaction.personnel.last_name}",
            transaction.verified_by or 'N/A'
        ])

    # Create table
    table = Table(data)

    # Style table
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.blue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVuSans'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 1), (-1, -1), 'DejaVuSans'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])
    table.setStyle(table_style)

    elements.append(table)

    # Build PDF
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()

    response.write(pdf)
    return response
