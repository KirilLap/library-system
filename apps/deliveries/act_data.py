"""Content of a delivery act, shared by the PDF and Word generators."""
from dataclasses import dataclass

from django.conf import settings
from django.utils.translation import gettext as _


@dataclass
class ActData:
    title: str
    meta: list          # [(label, value), ...]
    headers: list
    rows: list          # [[cell, ...], ...]
    total_label: str
    total: int
    sign_left: str
    sign_right: str


def build_act(batch):
    """Collect act texts in the currently active language."""
    location = batch.location
    items = list(batch.items.select_related('book__book_title').order_by('book__inventory_number'))

    library = getattr(settings, 'LIBRARY_NAME', '')
    phone = getattr(settings, 'LIBRARY_PHONE', '')
    meta = [
        (_('Библиотека'), library + (f' · {phone}' if phone else '')),
        (_('Библиопункт'), f'{location.name} ({_(location.get_type_display())})'),
        (_('Адрес'), location.address),
    ]
    if location.contact_person:
        contact = location.contact_person
        if location.contact_phone:
            contact += f' · {location.contact_phone}'
        meta.append((_('Контактное лицо'), contact))
    meta.append((_('Дата доставки'), batch.delivery_date.strftime('%d.%m.%Y')))
    meta.append((_('Количество книг'), str(len(items))))
    if batch.note:
        meta.append((_('Примечание'), batch.note))

    rows = []
    for i, item in enumerate(items, start=1):
        book = item.book
        rows.append([
            str(i),
            book.inventory_number,
            book.title,
            book.author,
            str(book.year) if book.year else '—',
            _(book.get_genre_display()),
        ])

    return ActData(
        title=_('Акт доставки книг №%(n)s') % {'n': batch.pk},
        meta=meta,
        headers=['№', _('Инв. №'), _('Название'), _('Автор'), _('Год'), _('Жанр')],
        rows=rows,
        total_label=_('Итого книг'),
        total=len(items),
        sign_left=_('Сдал (библиотекарь)'),
        sign_right=_('Принял (ответственный)'),
    )


def act_filename(batch, ext):
    return f'act_batch_{batch.pk}_{batch.delivery_date}.{ext}'
