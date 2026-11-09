from django.test import SimpleTestCase, override_settings

from config.storage import RelaxedManifestStaticFilesStorage


class StaticCacheBustingTests(SimpleTestCase):
    @override_settings(DEBUG=False)
    def test_missing_manifest_entry_does_not_break_pages(self):
        storage = RelaxedManifestStaticFilesStorage()
        storage.hashed_files = {}                 # как будто collectstatic ещё не запускали
        self.assertEqual(storage.url('css/custom.css'), '/static/css/custom.css')

    @override_settings(DEBUG=False)
    def test_known_file_gets_hashed_name(self):
        storage = RelaxedManifestStaticFilesStorage()
        storage.hashed_files = {'css/custom.css': 'css/custom.1a2b3c4d5e6f.css'}
        self.assertEqual(storage.url('css/custom.css'), '/static/css/custom.1a2b3c4d5e6f.css')
