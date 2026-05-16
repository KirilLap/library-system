"""PDF act generation for delivery batches using WeasyPrint."""

from django.template.loader import render_to_string
from django.conf import settings


def generate_batch_pdf(batch):
    """Return PDF bytes for a DeliveryBatch."""
    from weasyprint import HTML, CSS

    items = batch.items.select_related('book').order_by('book__inventory_number')

    html_string = render_to_string('deliveries/batch_pdf.html', {
        'batch': batch,
        'items': items,
        'LIBRARY_NAME': getattr(settings, 'LIBRARY_NAME', ''),
        'LIBRARY_PHONE': getattr(settings, 'LIBRARY_PHONE', ''),
    })

    css = CSS(string='''
        @page { size: A4; margin: 1.5cm 2cm; }
        body { font-family: Arial, sans-serif; font-size: 12px; color: #000; }
        h1 { font-size: 16px; margin-bottom: 4px; }
        .meta { font-size: 11px; color: #555; margin-bottom: 16px; }
        table { width: 100%; border-collapse: collapse; margin-top: 12px; }
        th, td { border: 1px solid #ccc; padding: 5px 8px; text-align: left; }
        th { background: #f0f0f0; font-weight: bold; }
        tr:nth-child(even) td { background: #fafafa; }
        .footer { margin-top: 24px; font-size: 11px; color: #555; }
        .sign-block { margin-top: 32px; display: flex; justify-content: space-between; }
        .sign-line { border-top: 1px solid #000; width: 200px; text-align: center;
                     padding-top: 4px; font-size: 10px; color: #555; }
    ''')

    pdf_bytes = HTML(string=html_string, base_url=settings.SITE_URL).write_pdf(stylesheets=[css])
    return pdf_bytes
