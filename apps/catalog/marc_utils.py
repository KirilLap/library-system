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
    """Convert a pymarc Record to a JSON-serializable dict."""
    result = {}
    for field in record:
        tag = field.tag
        if hasattr(field, 'subfields') and field.subfields:
            subfields = {}
            sf_list = field.subfields
            # pymarc 5.x: Subfield namedtuples; pymarc 4.x: flat list
            if hasattr(sf_list[0], 'code'):
                pairs = [(sf.code, sf.value) for sf in sf_list]
            else:
                pairs = list(zip(sf_list[0::2], sf_list[1::2]))
            for code, value in pairs:
                code = str(code)
                value = str(value)
                if code in subfields:
                    existing = subfields[code]
                    if isinstance(existing, list):
                        existing.append(value)
                    else:
                        subfields[code] = [existing, value]
                else:
                    subfields[code] = value
            entry = {'ind1': str(field.indicator1), 'ind2': str(field.indicator2), 'subfields': subfields}
        elif hasattr(field, 'subfields'):
            entry = {'ind1': str(field.indicator1), 'ind2': str(field.indicator2), 'subfields': {}}
        else:
            entry = str(field.value())

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
    inventory_number = str(f001.value()).strip() if f001 else ''

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


def _parse_by_terminators(file_bytes):
    """
    Alternative MARC parser for files with incorrect directory field lengths
    (e.g. exported from IRBIS/RUSMARC systems).
    Splits field data by \\x1e instead of relying on directory offsets.
    Returns a list of pymarc Records, or empty list on failure.
    """
    from pymarc import Field, Record

    try:
        base_address = int(file_bytes[12:17])
        directory_raw = file_bytes[24:base_address - 1]

        if len(directory_raw) % 12 != 0:
            return []

        tags = [
            directory_raw[i * 12:i * 12 + 3].decode('ascii', errors='replace')
            for i in range(len(directory_raw) // 12)
        ]

        # Split the field data section by field terminator \x1e
        field_section = file_bytes[base_address:]
        chunks = field_section.split(b'\x1e')
        # Last chunk is either empty or \x1d record terminator — skip it

        records = []
        record = Record()

        for i, tag in enumerate(tags):
            if i >= len(chunks):
                break
            chunk = chunks[i]

            try:
                if tag < '010':
                    # Control field: no indicators or subfields
                    value = chunk.decode('utf-8', errors='replace').rstrip()
                    field = Field(tag=tag, data=value)
                else:
                    # Variable field: 2 indicator bytes + subfields
                    if len(chunk) < 1:
                        continue

                    # Detect indicators
                    b0 = chunk[0] if len(chunk) > 0 else 0x20
                    b1 = chunk[1] if len(chunk) > 1 else 0x20

                    if b0 == 0x1F:
                        # Missing both indicators
                        ind1, ind2 = ' ', ' '
                        sf_bytes = chunk
                    elif b1 == 0x1F:
                        # Missing second indicator
                        ind1 = chr(b0) if 0x20 <= b0 < 0x7F else ' '
                        ind2 = ' '
                        sf_bytes = chunk[1:]
                    else:
                        ind1 = chr(b0) if 0x20 <= b0 < 0x7F else ' '
                        ind2 = chr(b1) if 0x20 <= b1 < 0x7F else ' '
                        sf_bytes = chunk[2:]

                    # Parse subfields: split by \x1f
                    parts = sf_bytes.split(b'\x1f')
                    field = Field(tag=tag, indicators=[ind1, ind2], subfields=[])
                    has_subfields = False
                    for part in parts[1:]:  # skip leading junk before first \x1f
                        if len(part) >= 1:
                            code = chr(part[0]) if 0x20 <= part[0] < 0x7F else 'a'
                            value = part[1:].decode('utf-8', errors='replace').rstrip()
                            field.add_subfield(code, value)
                            has_subfields = True

                    if not has_subfields:
                        continue

                record.add_field(field)

            except Exception:
                continue

        if record.fields:
            records.append(record)

        return records

    except Exception:
        return []


def _try_parse(file_bytes, **kwargs):
    import warnings as _w
    from pymarc import MARCReader
    records = []
    errors = []
    try:
        with _w.catch_warnings():
            _w.simplefilter('ignore')
            reader = MARCReader(BytesIO(file_bytes), **kwargs)
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


def parse_marc_file(file_bytes):
    """
    Parse MARC file bytes. Handles:
    - Standard MARC21 UTF-8 and MARC-8
    - Files with incorrect directory field lengths (IRBIS/RUSMARC)
    Returns (records, errors).
    """
    # Standard pymarc parsing
    for kwargs in [
        dict(to_unicode=True, force_utf8=False),
        dict(to_unicode=True, force_utf8=True),
    ]:
        records, errors = _try_parse(file_bytes, **kwargs)
        if records:
            return records, errors

    # Fallback: parse by field terminators (for IRBIS/RUSMARC files)
    fallback_records = _parse_by_terminators(file_bytes)
    if fallback_records:
        book_records = []
        errors = []
        for i, rec in enumerate(fallback_records):
            try:
                book_records.append(extract_book_data(rec))
            except Exception as e:
                errors.append((i, str(e)))
        return book_records, errors

    return [], [(0, 'Не удалось прочитать файл. Проверьте формат (MARC21 .mrc или .marc).')]
