import sqlite3
import tempfile
import unittest
from pathlib import Path
from promptvault.store import Store, ValidationError


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'vault.db'
        self.store = Store(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_persists_template(self):
        item = self.store.create('Учебный конспект', 'Краткое описание', 'учёба, текст', 'Тема: {{topic}}', 'Начало')
        self.assertEqual(item['version'], 1)
        self.assertEqual(Store(self.path).get(item['id'])['template'], 'Тема: {{topic}}')
        self.assertEqual(item['tags'], 'учёба, текст')

    def test_edit_and_restore_append_immutable_versions(self):
        first = self.store.create('Первый', '', 'тест', 'Привет {{name}}', 'Создание')
        second = self.store.edit(first['id'], 'Второй', '', 'тест', 'Пока {{name}}', 'Правка')
        restored = self.store.restore(first['id'], 1, 'Возврат')
        self.assertEqual(second['version'], 2)
        self.assertEqual(restored['version'], 3)
        self.assertEqual(restored['template'], first['template'])
        self.assertEqual(self.store.get(first['id'], 2)['title'], 'Второй')
        self.assertEqual(len(self.store.history(first['id'])), 3)
        with self.store.connect() as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('UPDATE versions SET title=?', ('Взлом',))
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('DELETE FROM versions')

    def test_invalid_fields_are_rejected_without_writes(self):
        valid = ['Название', '', '', 'Тема {{topic}}', 'Создание']
        for field, bad in [(0, ''), (0, '   '), (0, 'a'*121), (1, 'a'*2001), (2, 'a'*501), (3, ''), (3, 'a'*20001), (4, ''), (4, 'a'*501), (3, '{{broken'), (3, '{{bad-name}}'), (0, None), (0, 'bad\u0000name')]:
            with self.subTest(field=field, value=str(bad)[:15]):
                args = valid.copy()
                args[field] = bad
                with self.assertRaises(ValidationError):
                    self.store.create(*args)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM prompts').fetchone()[0], 0)

    def test_compare_preserves_field_boundaries(self):
        item = self.store.create('A', 'B\nC', 'Tags', 'Template', 'Start')
        self.store.edit(item['id'], 'A\nB', 'C', 'Tags', 'Template', 'Edit')

        diff = self.store.compare(item['id'], 1, 2)

        self.assertTrue(diff.startswith('--- v1\n+++ v2\n'), diff)
        self.assertIn('-  "title": "A",\n', diff)
        self.assertIn('+  "title": "A\\nB",\n', diff)
        self.assertIn('-  "description": "B\\nC",\n', diff)
        self.assertIn('+  "description": "C",\n', diff)

    def test_compare_separates_changed_template_lines_without_final_newline(self):
        item = self.store.create('Title', '', '', 'old', 'Start')
        self.store.edit(item['id'], 'Title', '', '', 'new', 'Edit')

        diff = self.store.compare(item['id'], 1, 2)

        self.assertTrue(diff.startswith('--- v1\n+++ v2\n'))
        removed = [line for line in diff.splitlines() if line.startswith('-') and not line.startswith('---')]
        added = [line for line in diff.splitlines() if line.startswith('+') and not line.startswith('+++')]
        self.assertTrue(any('old' in line for line in removed), diff)
        self.assertTrue(any('new' in line for line in added), diff)
        self.assertFalse(any('old' in line and 'new' in line for line in removed + added), diff)
        self.assertTrue(diff.endswith('\n'), diff)

    def test_compare_preserves_template_trailing_newline(self):
        item = self.store.create('Title', '', '', 'Template', 'Start')
        self.store.edit(item['id'], 'Title', '', '', 'Template\n', 'Edit')

        diff = self.store.compare(item['id'], 1, 2)

        self.assertIn('-  "template": "Template"\n', diff)
        self.assertIn('+  "template": "Template\\n"\n', diff)

    def test_compare_ignores_version_metadata(self):
        item = self.store.create('Title', '', '', 'Template', 'Start')
        self.store.edit(item['id'], 'Title', '', '', 'Template', 'Different comment')
        with self.store.connect() as db:
            db.execute('DROP TRIGGER immutable_update')
            db.execute('UPDATE versions SET created_at=? WHERE version=2', ('2099-01-01T00:00:00Z',))

        self.assertEqual(self.store.compare(item['id'], 1, 2), '')

    def test_search_diff_and_export_use_latest_and_history(self):
        item = self.store.create('Конспект', 'Описание', 'Учёба', 'Тема: {{topic}}', 'Старт')
        self.store.edit(item['id'], 'План', 'Описание', 'Учёба', 'План: {{topic}}', 'Правка')
        self.assertEqual(len(self.store.search('УЧЁБА')), 1)
        self.assertEqual(self.store.search('Конспект'), [])
        self.assertEqual(len(self.store.search("' OR 1=1 --")), 0)
        diff = self.store.compare(item['id'], 1, 2)
        self.assertIn('-  "template": "Тема: {{topic}}"\n', diff)
        self.assertIn('+  "template": "План: {{topic}}"\n', diff)
        data = self.store.export()
        self.assertEqual(data['format'], 'promptvault-1')
        self.assertEqual(len(data['prompts'][0]['versions']), 2)
        self.assertNotIn('path', data)


if __name__ == '__main__':
    unittest.main()
