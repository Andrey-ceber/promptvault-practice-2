import unittest
from promptvault.render import render
from promptvault.store import ValidationError


class RenderTests(unittest.TestCase):
    def test_render_substitutes_once_and_preserves_source(self):
        source = '{{name}}: {{ topic }} / {{name}}'
        self.assertEqual(render(source, {'name': '{{topic}}', 'topic': 'Тест'}), '{{topic}}: Тест / {{topic}}')
        self.assertEqual(source, '{{name}}: {{ topic }} / {{name}}')

    def test_missing_blank_and_invalid_variables_rejected(self):
        for values in ({}, {'name': ''}, {'name': '  '}, {'name': 2}, [], {'name': 'x'*20001}):
            with self.subTest(values=str(values)[:50]), self.assertRaises(ValidationError):
                render('Привет {{name}}', values)
