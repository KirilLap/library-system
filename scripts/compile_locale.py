"""Компилирует locale/uz/LC_MESSAGES/django.po в .mo без системных gettext-утилит
(msgfmt на Windows обычно не установлен) — используется чистый Python (polib)."""
import pathlib
import polib

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent

for po_path in BASE_DIR.glob('locale/*/LC_MESSAGES/django.po'):
    po = polib.pofile(str(po_path))
    mo_path = po_path.with_suffix('.mo')
    po.save_as_mofile(str(mo_path))
    print(f'{po_path} -> {mo_path} ({len(po)} записей)')
