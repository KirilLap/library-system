import re
from io import BytesIO


GENRE_KEYWORDS = {
    'FICTION': ['худ', 'fiction', 'роман', 'повест', 'расска', 'novel', 'рассказ'],
    'CHILDREN': ['дет', 'child', 'юнош', 'для детей'],
    'EDUCATIONAL': ['учеб', 'education', 'пособ', 'учебник', 'методич'],
    'POETRY': ['поэз', 'стих', 'poetry', 'verse', 'лирик'],
    'NONFICTION': ['докум', 'non-fic', 'публиц', 'биограф', 'мемуар'],
}


def guess_genre(subject_text):
    text = subject_text.lower()
    for genre, keywords in GENRE_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return genre
    return 'OTHER'


def extract_year(text):
    if not text:
        return None
    match = re.search(r'\d{4}', text)
    if match:
        year = int(match.group())
        if 1800 <= year <= 2100:
            return year
    return None


def record_to_dict(record):
    result = {}
    for field in record:
        tag = field.tag
        if hasattr(field, 'subfields'):
            subfields = {}
            codes = field.subfields[0::2]
            values = field.subfields[1::2]
            for code, value in zip(codes, values):
                if code in subfields:
                    existing = subfields[code]
                    if isinstance(existing, list):
                        existing.append(value)
                    else:
                        subfields[code] = [existing, value]
                else:
                    subfields[code] = value
            entry = {
                'ind1': field.indicator1,
                'ind2': field.indicator2,
                'subfields': subfields,
            }
        else:
            entry = field.value()

        if tag in result:
            existing = result[tag]
            if isinstance(existing, list):
                existing.append(entry)
            else:
                result[tag] = [existing, entry]
        else:
            result[tag] = entry
    return result


def get_subfield(record, tag, code):
    field = record.get(tag)
    if not field:
        return ''
    values = field.get_subfields(code)
    return values[0] if values else ''


def extract_book_data(record):
    f001 = record.get('001')
    inventory_number = f001.value().strip() if f001 else ''

    title = get_subfield(record, '245', 'a').rstrip(' /').strip()
    subtitle = get_subfield(record, '245', 'b').rstrip(' /').strip()
    if subtitle:
        title = f'{title}: {subtitle}'

    author = get_subfield(record, '100', 'a').rstrip(',. ').strip()
    if not author:
        author = get_subfield(record, '700', 'a').rstrip(',. ').strip()

    isbn_raw = get_subfield(record, '020', 'a')
    isbn = isbn_raw.split(' ')[0].strip() if isbn_raw else ''

    publisher = (
        get_subfield(record, '260', 'b') or get_subfield(record, '264', 'b')
    ).strip(' ,.')

    year_text = get_subfield(record, '260', 'c') or get_subfield(record, '264', 'c')
    year = extract_year(year_text)

    genre = 'OTHER'
    f650 = record.get('650')
    if f650:
        subjects = f650.get_subfields('a')
        if subjects:
            genre = guess_genre(subjects[0])

    return {
        'inventory_number': inventory_number,
        'title': title,
        'author': author,
        'isbn': isbn,
        'publisher': publisher,
        'year': year,
        'genre': genre,
        'marc_data': record_to_dict(record),
    }


def parse_marc_file(file_bytes):
    from pymarc import MARCReader

    records = []
    errors = []

    try:
        reader = MARCReader(BytesIO(file_bytes), to_unicode=True, force_utf8=True)
        for i, record in enumerate(reader):
            if record is None:
                errors.append((i, 'Не удалось прочитать запись'))
                continue
            try:
                records.append(extract_book_data(record))
            except Exception as e:
                errors.append((i, str(e)))
    except Exception as e:
        errors.append((0, f'Ошибка чтения файла: {e}'))

    return records, errors
