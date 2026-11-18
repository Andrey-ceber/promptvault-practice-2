# Проверка PromptVault: TDD и фактическое исполнение

## Подход

Код писался вертикальными функциональными циклами: сначала тест нужного поведения, запуск с RED, реализация, запуск GREEN и всей накопленной suite. Использован `unittest` стандартной библиотеки. HTTP-тесты действительно поднимают сервер на `127.0.0.1` с портом `0` (свободный порт ОС), отправляют запросы `urllib.request`, останавливают сервер и удаляют временную БД. Ни SQLite, ни HTTP не замоканы.

## Журнал наблюдавшихся RED → GREEN

| Цикл | Тест / поведение | Наблюдавшийся RED | GREEN накопленной suite |
|---|---|---|---|
| 1 | Создание и повторное чтение SQLite | `ModuleNotFoundError: No module named 'promptvault'` — пакета ещё нет | 1 тест, OK, 0.055s |
| 2 | Правка, восстановление новой версией, запрет UPDATE/DELETE истории | `AttributeError: 'Store' object has no attribute 'edit'` | 2 теста, OK, 0.217s |
| 3 | Пустые/длинные/нестроковые поля и неверные переменные | `ValidationError not raised`; для None — ограничение NOT NULL вместо доменной ошибки; ошибочные записи попадали в БД | 3 теста, OK, 0.243s |
| 4 | Поиск текущих версий, diff, JSON с историей | `AttributeError: 'Store' object has no attribute 'search'` | 4 теста, OK, 0.336s |
| 5 | Однопроходный render, проверка отсутствующих/пустых значений | `ModuleNotFoundError: No module named 'promptvault.render'` | 6 тестов, OK, 0.286s |
| 6 | Реальный HTTP-поток создание → правка → diff → restore → render → export | `ModuleNotFoundError: No module named 'promptvault.web'` | 7 тестов, OK, 1.123s |
| 7 | Security headers, запрет чужих Host/Origin, лимит POST | `AssertionError: None != 'nosniff'` | 9 тестов, OK, 2.488s |
| 8 | CLI `python -m promptvault --help` | `No module named promptvault.__main__; 'promptvault' is a package and cannot be directly executed` | 10 тестов, OK |

В цикле 3 инструмент патча внёс синтаксическую ошибку в `with self.connect()`; ошибка немедленно обнаружена lint и исправлена до GREEN. В цикле 6 первый прогон после реализации выявил ошибку самого HTTP-теста: кириллица в URL должна быть percent-encoded; исправлен URL теста через `urlencode`, функциональные требования не ослаблялись. Тест экранирования HTML был добавлен как регрессионная проверка уже реализованного escaping и сразу прошёл; он не выдаётся за самостоятельный RED-цикл.

## Реальные результаты на Windows

Команда из корня проекта:

```text
python -m unittest discover -s tests -v
```

Python: **3.14.7**, Windows. Итог проверочного прогона после реализации CLI:

```text
test_module_has_help_with_safe_defaults ... ok
test_browser_workflow_create_edit_compare_restore_render_export ... ok
test_html_escapes_inputs_and_errors_are_controlled ... ok
test_security_headers_host_origin_and_body_limits ... ok
test_missing_blank_and_invalid_variables_rejected ... ok
test_render_substitutes_once_and_preserves_source ... ok
test_create_persists_template ... ok
test_edit_and_restore_append_immutable_versions ... ok
test_invalid_fields_are_rejected_without_writes ... ok
test_search_diff_and_export_use_latest_and_history ... ok

Ran 10 tests in 3.517s
OK
```

`python -m compileall -q promptvault tests`: exit code **0**, без вывода.

## Реальные результаты Docker

Выполнено:

```text
docker compose build
docker compose run --rm --no-deps app python -m unittest discover -s tests -v
```

Build завершился успешно; образ `promptvault-practice2-app:latest`. Все те же тесты внутри Linux-контейнера:

```text
Ran 10 tests in 3.358s
OK
```

Дополнительно контейнер был временно запущен через `docker compose up -d --wait --wait-timeout 45`, достиг состояния **Healthy**, и запрос с хоста вернул:

```text
DOCKER HTTP 200 {"status": "ok"}
```

После проверки `docker compose down` удалил контейнер `promptvault-practice2-app-1` и сеть проекта. Долгоживущий сервер не оставлен. Named volume сохранён (обычная остановка не должна удалять постоянные данные).

## Что проверено

- Сохранность шаблона после повторного открытия SQLite.
- История v1/v2/v3, сохранение v2 после восстановления v1.
- SQL-триггеры действительно отклоняют UPDATE и DELETE.
- Валидация полей (13 вариантов невалидного ввода) без частично созданных записей.
- Unicode-поиск по текущим версиям и безопасная обработка строки, похожей на SQL injection.
- Diff и JSON с полной историей.
- Однопроходная подстановка, повторные переменные, шесть вариантов неверных значений, исходный шаблон не меняется.
- Полный пользовательский поток по реальному TCP/HTTP, including redirects 303 → GET.
- XSS escaping названия, описания, шаблона; 400/403/404/413; заголовки CSP/nosniff/no-store.
- Значения render не попадают в export; нет внутреннего пути БД в схеме экспорта.
- CSS доступен локально, CLI запускается, Docker build/тесты/health работают.

## Границы подтверждения

Это 10 методов unittest с дополнительными subtests, не заявление о 100% code coverage. Функциональность форм проверялась HTTP-запросами; визуальная браузерная проверка и скринкаст выполняются отдельно при сдаче. Настроен CI для Windows/Linux и Python 3.12–3.14, но **удалённый GitHub Actions в рамках этой работы ещё не запускался**. Нагрузочное тестирование, pentest и долговременная эксплуатация не проводились.
