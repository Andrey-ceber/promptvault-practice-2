import json
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from promptvault.web import make_server


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = make_server(Path(self.tmp.name) / 'web.db', port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, path, data=None, headers=None):
        req = urllib.request.Request(self.base + path, data=urllib.parse.urlencode(data).encode() if data is not None else None, headers=headers or {})
        try:
            response = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.read().decode(), response.headers

    def test_security_headers_host_origin_and_body_limits(self):
        _, _, headers = self.request('/')
        self.assertEqual(headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertIn("default-src 'self'", headers.get('Content-Security-Policy', ''))
        self.assertEqual(headers.get('Cache-Control'), 'no-store')
        self.assertEqual(headers.get('Referrer-Policy'), 'same-origin')
        self.assertEqual(self.request('/', headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request('/create', {'csrf': self.server.token}, {'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.request('/create', {'csrf': self.server.token, 'title': 'x'*140000})[0], 413)
        self.assertEqual(self.request('/create', {})[0], 403)

    def test_html_escapes_inputs_and_errors_are_controlled(self):
        fields = dict(csrf=self.server.token, title='<script>alert(1)</script>', description='<img src=x onerror=alert(1)>', tags='test', template='</pre><script>x</script> {{name}}', comment='Старт')
        _, body, _ = self.request('/create', fields)
        self.assertNotIn('<script>', body)
        self.assertIn('&lt;script&gt;', body)
        self.assertNotIn('<img src=x', self.request('/')[1])
        for path in ('/missing', '/prompt?id=999', '/compare?id=1&left=999&right=1'):
            self.assertEqual(self.request(path)[0], 404)
        self.assertEqual(self.request('/prompt?id=bad')[0], 400)
        self.assertEqual(self.request('/render?id=1', dict(csrf=self.server.token, variables='not-json'))[0], 400)
        fields['template'] = ''
        self.assertEqual(self.request('/edit?id=1', fields)[0], 400)
        self.assertEqual(len(self.server.store.history(1)), 1)

    def test_browser_workflow_create_edit_compare_restore_render_export(self):
        status, home, _ = self.request('/')
        self.assertEqual(status, 200)
        self.assertIn('Промпт-библиотека с версиями', home)
        _, form, _ = self.request('/new')
        token = re.search(r'name="csrf" value="([^"]+)"', form).group(1)
        fields = dict(csrf=token, title='Учебный план', description='Демо', tags='учёба', template='Тема: {{topic}}', comment='Старт')
        status, body, _ = self.request('/create', fields)
        self.assertEqual(status, 200)
        self.assertIn('Учебный план', body)
        fields.update(template='Составь план: {{topic}}', comment='Уточнение')
        self.assertEqual(self.request('/edit?id=1', fields)[0], 200)
        _, diff, _ = self.request('/compare?id=1&left=1&right=2')
        self.assertIn('-  &quot;template&quot;: &quot;Тема: {{topic}}&quot;', diff)
        self.assertIn('+  &quot;template&quot;: &quot;Составь план: {{topic}}&quot;', diff)
        self.assertEqual(self.request('/restore?id=1', dict(csrf=token, version='1', comment='Возврат'))[0], 200)
        _, rendered, _ = self.request('/render?id=1', dict(csrf=token, variables='{"topic":"История"}'))
        self.assertIn('Тема: История', rendered)
        self.assertEqual(self.request('/render?id=1', dict(csrf=token, variables='{}'))[0], 400)
        _, exported, headers = self.request('/export')
        data = json.loads(exported)
        self.assertEqual(len(data['prompts'][0]['versions']), 3)
        self.assertEqual(data['prompts'][0]['versions'][0]['template'], 'Тема: {{topic}}')
        self.assertNotIn('История', exported)
        self.assertIn('attachment', headers['Content-Disposition'])
        self.assertEqual(json.loads(self.request('/health')[1]), {'status': 'ok'})
        self.assertIn('Учебный план', self.request('/?' + urllib.parse.urlencode({'q': 'учёба'}))[1])
        self.assertEqual(self.request('/static/style.css')[0], 200)
