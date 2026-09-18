"""Находит все литеральные строки в {% translate "..." %} / {% blocktranslate %}...{% endblocktranslate %}
по всем шаблонам и сверяет их с msgid в locale/uz/LC_MESSAGES/django.po, чтобы найти пропущенные переводы.
Не проверяет {% translate variable %} (без кавычек) — те строки не определены статически."""
import pathlib
import re
import polib

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / 'templates'
PO_PATH = BASE_DIR / 'locale' / 'uz' / 'LC_MESSAGES' / 'django.po'

po = polib.pofile(str(PO_PATH))
known_msgids = {entry.msgid for entry in po}

# {% translate "literal" %} or {% translate 'literal' %}
translate_re = re.compile(r"""\{%\s*translate\s+"([^"]*)"\s*%\}|\{%\s*translate\s+'([^']*)'\s*%\}""")
# {% blocktranslate ... %}...{% endblocktranslate %} (also trans/blocktrans short forms, not used here)
blocktranslate_re = re.compile(r"\{%\s*blocktranslate[^%]*%\}(.*?)\{%\s*endblocktranslate\s*%\}", re.DOTALL)
var_re = re.compile(r"\{\{\s*(\w+)\s*\}\}")

missing = []
checked = 0

for html_file in TEMPLATES_DIR.rglob('*.html'):
    text = html_file.read_text(encoding='utf-8')
    for m in translate_re.finditer(text):
        literal = m.group(1) if m.group(1) is not None else m.group(2)
        checked += 1
        if literal and literal not in known_msgids:
            missing.append((str(html_file.relative_to(BASE_DIR)), literal))
    for m in blocktranslate_re.finditer(text):
        block = m.group(1).strip()
        # Normalize {{ var }} -> %(var)s like Django's blocktranslate msgid generation
        msgid = var_re.sub(lambda mm: f"%({mm.group(1)})s", block)
        msgid = re.sub(r'\s+', ' ', msgid).strip()
        checked += 1
        if msgid and msgid not in known_msgids:
            missing.append((str(html_file.relative_to(BASE_DIR)), msgid))

print(f'Checked {checked} translate/blocktranslate occurrences.')
if missing:
    print(f'\n{len(missing)} MISSING from django.po:')
    seen = set()
    for path, text in missing:
        key = text
        if key in seen:
            continue
        seen.add(key)
        print(f'  [{path}] {text!r}')
else:
    print('All literal translate/blocktranslate strings found in django.po.')
