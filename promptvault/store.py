"""SQLite-хранилище учебных шаблонов."""
import sqlite3
import re

TOKEN = re.compile(r'\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}')


def validate(title, description, tags, template, comment):
    for value, limit, required, name in zip(
            (title, description, tags, template, comment),
            (120, 2000, 500, 20000, 500), (True, False, False, True, True),
            ('Название', 'Описание', 'Теги', 'Шаблон', 'Комментарий')):
        if not isinstance(value, str) or len(value) > limit or '\x00' in value or (required and not value.strip()):
            raise ValidationError(f'{name}: требуется текст до {limit} символов' + (' (не пустой)' if required else ''))
    residue = TOKEN.sub('', template)
    if '{{' in residue or '}}' in residue:
        raise ValidationError('Переменные: используйте {{name}}, латиницу, цифры и подчёркивание')
from contextlib import contextmanager
from pathlib import Path


class ValidationError(ValueError):
    pass


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS prompts(id INTEGER PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS versions(
                    prompt_id INTEGER NOT NULL REFERENCES prompts(id),
                    version INTEGER NOT NULL, title TEXT NOT NULL,
                    description TEXT NOT NULL, tags TEXT NOT NULL,
                    template TEXT NOT NULL, comment TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    PRIMARY KEY(prompt_id,version));
                CREATE TRIGGER IF NOT EXISTS immutable_update BEFORE UPDATE ON versions
                    BEGIN SELECT RAISE(ABORT,'Versions are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_delete BEFORE DELETE ON versions
                    BEGIN SELECT RAISE(ABORT,'Versions are immutable'); END;
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, title, description, tags, template, comment):
        validate(title, description, tags, template, comment)
        with self.connect() as db:
            pid = db.execute('INSERT INTO prompts DEFAULT VALUES').lastrowid
            db.execute('INSERT INTO versions(prompt_id,version,title,description,tags,template,comment) VALUES(?,1,?,?,?,?,?)',
                       (pid, title, description, tags, template, comment))
        return self.get(pid)

    def get(self, pid, version=None):
        with self.connect() as db:
            row = db.execute('SELECT prompt_id AS id,* FROM versions WHERE prompt_id=?' +
                             (' AND version=?' if version is not None else '') + ' ORDER BY version DESC LIMIT 1',
                             (pid,version) if version is not None else (pid,)).fetchone()
        if row is None:
            raise KeyError('Промпт или версия не найдены')
        return dict(row)

    def edit(self, pid, title, description, tags, template, comment):
        validate(title, description, tags, template, comment)
        self.get(pid)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            version = db.execute('SELECT MAX(version)+1 FROM versions WHERE prompt_id=?', (pid,)).fetchone()[0]
            db.execute('INSERT INTO versions(prompt_id,version,title,description,tags,template,comment) VALUES(?,?,?,?,?,?,?)',
                       (pid, version, title, description, tags, template, comment))
        return self.get(pid, version)

    def history(self, pid):
        self.get(pid)
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM versions WHERE prompt_id=? ORDER BY version DESC', (pid,))]

    def search(self, query=''):
        with self.connect() as db:
            rows = db.execute('SELECT prompt_id AS id,* FROM versions v WHERE version=(SELECT MAX(version) FROM versions WHERE prompt_id=v.prompt_id) ORDER BY prompt_id DESC').fetchall()
        needle = query.casefold()
        return [dict(row) for row in rows if needle in ' '.join(row[k] for k in ('title', 'description', 'tags', 'template')).casefold()]

    def compare(self, pid, left, right):
        import difflib
        import json
        def text(version):
            item = self.get(pid, version)
            fields = {key: item[key] for key in ('title', 'description', 'tags', 'template')}
            return (json.dumps(fields, ensure_ascii=False, indent=2) + '\n').splitlines(keepends=True)
        return ''.join(difflib.unified_diff(text(left), text(right), fromfile=f'v{left}', tofile=f'v{right}'))

    def export(self):
        return {'format': 'promptvault-1', 'prompts': [
            {'id': item['id'], 'versions': self.history(item['id'])} for item in self.search()]}

    def restore(self, pid, version, comment):
        old = self.get(pid, version)
        return self.edit(pid, old['title'], old['description'], old['tags'], old['template'], comment)
