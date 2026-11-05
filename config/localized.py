from django.utils import translation
from django.utils.translation import gettext


class LocalizedNameMixin:
    """Название справочника (жанр, язык, тип библиопункта) на двух языках.

    name    — русское название (основное);
    name_uz — узбекский перевод, который администратор вводит сразу в форме.
    Если узбекский перевод не введён, используется перевод из файлов локализации,
    а при его отсутствии — русское название.
    """

    def localized_name(self):
        """Название на языке, выбранном посетителем."""
        language = translation.get_language() or ''
        if language.startswith('uz') and self.name_uz:
            return self.name_uz
        return gettext(self.name)

    def uz_name(self):
        """Узбекское название независимо от выбранного языка (для таблиц администратора)."""
        if self.name_uz:
            return self.name_uz
        with translation.override('uz'):
            return gettext(self.name)
