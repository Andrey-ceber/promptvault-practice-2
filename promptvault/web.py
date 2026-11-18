"""Локальный HTTP UI. Не предназначен для публичного размещения."""
import html
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from .store import Store, TOKEN, ValidationError
from .render import render


def esc(value):
    return html.escape(str(value), quote=True)


def page(title, body):
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · PromptVault</title>
<link rel="stylesheet" href="/static/style.css"></head><body><header><a class="brand" href="/">PV <span>PromptVault</span></a><nav><a href="/new">+ Новый промпт</a><a href="/export">Экспорт JSON</a></nav></header><main>
<div class="eyebrow">УЧЕБНАЯ МАСТЕРСКАЯ · PYTHON + SQLITE</div><h1>{esc(title)}</h1>{body}</main><footer>Локальная библиотека. Без LLM и внешних API. Не храните секреты в шаблонах.</footer></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'same-origin')
        super().end_headers()

    def log_message(self, *args):
        pass

    def send(self, body, status=200, kind='text/html; charset=utf-8', attachment=False):
        raw = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(raw)))
        if attachment:
            self.send_header('Content-Disposition', 'attachment; filename="promptvault.json"')
        self.end_headers()
        self.wfile.write(raw)

    def csrf(self):
        return f'<input type="hidden" name="csrf" value="{self.server.token}">'

    def form(self, item=None, values=None):
        item = values or item or {}
        action = f'/edit?id={item["id"]}' if 'id' in item else '/create'
        fields = ''
        for key, label, limit in [('title', 'Название', 120), ('description', 'Описание', 2000), ('tags', 'Теги через запятую', 500), ('template', 'Шаблон промпта', 20000), ('comment', 'Комментарий к новой версии', 500)]:
            value = item.get(key, '') if key != 'comment' else item.get('form_comment', '')
            required = 'required' if key in ('title', 'template', 'comment') else ''
            fields += f'<label>{label}<textarea name="{key}" maxlength="{limit}" rows="{7 if key == "template" else 2}" {required}>{esc(value)}</textarea></label>'
        return f'<form class="panel" method="post" action="{action}">{self.csrf()}{fields}<p class="muted">Переменные: {{{{topic}}}}, {{{{audience}}}}. Название, шаблон и комментарий обязательны.</p><button>Сохранить новую версию</button></form>'

    def detail(self, pid, result=''):
        item = self.server.store.get(pid)
        history = self.server.store.history(pid)
        versions = ''.join(f'<option value="{v["version"]}">v{v["version"]}</option>' for v in history)
        rows = ''.join(f'<tr><td>v{v["version"]}</td><td>{esc(v["created_at"])}</td><td>{esc(v["comment"])}</td></tr>' for v in history)
        names = ', '.join(sorted(set(TOKEN.findall(item['template'])))) or 'нет'
        body = f'''<p class="muted">Текущая версия v{item['version']} · {esc(item['tags'])}</p>
<p>{esc(item['description'])}</p><section class="panel"><h2>Исходный шаблон</h2><pre>{esc(item['template'])}</pre></section>{result}
<div class="columns"><section><h2>Предпросмотр</h2><form class="panel" method="post" action="/render?id={pid}">{self.csrf()}<p>Переменные: {esc(names)}</p><label>Значения в JSON<textarea name="variables" rows="4" required placeholder='{{"topic": "История"}}'></textarea></label><button>Подставить значения</button><p class="muted">Результат не сохраняется. Исходный шаблон не меняется.</p></form></section>
<section><h2>История версий</h2><div class="panel"><table><tr><th>Версия</th><th>UTC</th><th>Комментарий</th></tr>{rows}</table>
<form method="get" action="/compare"><input type="hidden" name="id" value="{pid}"><label>От версии<select name="left">{versions}</select></label><label>К версии<select name="right">{versions}</select></label><button>Сравнить версии</button></form>
<form method="post" action="/restore?id={pid}">{self.csrf()}<label>Восстановить версию<select name="version">{versions}</select></label><label>Комментарий<input name="comment" maxlength="500" required></label><button class="secondary">Восстановить как новую</button></form></div></section></div>
<h2>Редактировать → новая версия</h2>{self.form(item)}'''
        return page(item['title'], body)

    def do_GET(self):
        self.route(False)

    def do_POST(self):
        self.route(True)

    def route(self, post):
        target = urlsplit(self.path)
        query = parse_qs(target.query)
        val = lambda key, default='': query.get(key, [default])[0]
        store = self.server.store
        host = self.headers.get('Host', '')
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if host not in allowed or (post and self.headers.get('Origin') not in (None, 'http://' + host)):
            self.send(page('Доступ запрещён', '<p>Разрешён только локальный доступ.</p>'), 403)
            return
        try:
            if post:
                length = int(self.headers.get('Content-Length', '0'))
                if length < 0 or length > 131072:
                    self.send(page('Слишком большой запрос', '<p>Лимит 128 КиБ.</p>'), 413)
                    return
                if self.headers.get('Transfer-Encoding'):
                    raise ValidationError('Потоковая передача не поддерживается')
                fields = parse_qs(self.rfile.read(length).decode('utf-8'), keep_blank_values=True, max_num_fields=30)
                field = lambda key: fields.get(key, [''])[0]
                if field('csrf') != self.server.token:
                    self.send(page('Доступ запрещён', '<p>Откройте форму заново.</p>'), 403)
                    return
                pid = int(val('id', '0'))
                if target.path in ('/create', '/edit'):
                    args = [field(key) for key in ('title', 'description', 'tags', 'template', 'comment')]
                    item = store.create(*args) if target.path == '/create' else store.edit(pid, *args)
                    self.send_response(303)
                    self.send_header('Location', f'/prompt?id={item["id"]}')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                elif target.path == '/restore':
                    store.restore(pid, int(field('version')), field('comment'))
                    self.send(self.detail(pid, '<p class="notice">Восстановлено как новая версия.</p>'))
                elif target.path == '/render':
                    result = render(store.get(pid)['template'], json.loads(field('variables')))
                    self.send(self.detail(pid, f'<section class="panel result"><h2>Результат подстановки</h2><pre>{esc(result)}</pre></section>'))
                else:
                    self.send(page('Не найдено', ''), 404)
            elif target.path == '/health':
                with store.connect() as db:
                    db.execute('SELECT 1').fetchone()
                self.send(json.dumps({'status': 'ok'}), kind='application/json; charset=utf-8')
            elif target.path == '/static/style.css':
                self.send(Path(__file__).with_name('style.css').read_text(encoding='utf-8'), kind='text/css; charset=utf-8')
            elif target.path == '/export':
                self.send(json.dumps(store.export(), ensure_ascii=False, indent=2), kind='application/json; charset=utf-8', attachment=True)
            elif target.path == '/new':
                self.send(page('Новый промпт', self.form()))
            elif target.path == '/prompt':
                self.send(self.detail(int(val('id'))))
            elif target.path == '/compare':
                pid = int(val('id'))
                diff = store.compare(pid, int(val('left')), int(val('right')))
                self.send(page('Сравнение версий', f'<a href="/prompt?id={pid}">← К промпту</a><pre class="panel">{esc(diff or "Нет различий")}</pre>'))
            elif target.path == '/':
                cards = ''.join(f'<a class="card" href="/prompt?id={p["id"]}"><span class="badge">v{p["version"]}</span><h2>{esc(p["title"])}</h2><p>{esc(p["description"])}</p><small>{esc(p["tags"])}</small></a>' for p in store.search(val('q')))
                self.send(page('Промпт-библиотека с версиями', f'<p class="lead">Храните идеи. Сравнивайте изменения. Возвращайтесь к удачным формулировкам.</p><form class="search" action="/" method="get"><input name="q" maxlength="200" value="{esc(val("q"))}" placeholder="Поиск по названию, описанию, тегам и шаблону"><button>Найти</button></form><div class="cards">{cards or "<div class=panel>Промптов пока нет или ничего не найдено. Создайте первый учебный шаблон.</div>"}</div>'))
            else:
                self.send(page('Не найдено', ''), 404)
        except KeyError:
            self.send(page('Не найдено', '<p>Промпт или версия не найдены.</p>'), 404)
        except (ValueError, UnicodeError) as error:
            self.send(page('Проверьте данные', f'<p class="notice">{esc(str(error))}</p><p>Вернитесь назад в браузере: введённые значения останутся в форме.</p><a href="/">← В библиотеку</a>'), 400)


def make_server(db, host='127.0.0.1', port=8782):
    store = Store(db)
    server = ThreadingHTTPServer((host, port), Handler)
    server.store = store
    server.token = secrets.token_urlsafe(32)
    return server
