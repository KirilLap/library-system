from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class RelaxedManifestStaticFilesStorage(ManifestStaticFilesStorage):
    """Статические файлы с хешем в имени (custom.8f3a1c.css).

    Когда файл меняется, меняется и его адрес, поэтому телефоны и браузеры сразу берут новую версию,
    а не показывают старые стили из кэша. Если файла нет в списке (например, не запускали
    collectstatic или файла нет вовсе), страница не ломается, а использует обычное имя файла."""

    manifest_strict = False

    def stored_name(self, name):
        try:
            return super().stored_name(name)
        except ValueError:      # файла нет среди собранных: отдаём обычный адрес, а не ошибку 500
            return name
