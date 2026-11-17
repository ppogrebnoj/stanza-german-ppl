# CHANGELOG — MCP-stanza-german (сервер)

## 4.0.1 (2026-11-17)
- `RULE_ROOT` по умолчанию больше не `E:\KI_WORK\правило`: путь считается от
  расположения `server.py` (`MCP-stanza-german/../правило`). Проект переносится
  в любой каталог без правки кода; `env.RULE_ROOT` по-прежнему переопределяет.
- Текст подсказки, когда правило не найдено, показывает проверенный каталог
  и оба искомых пути (`validator.py`, `reference/validator_v3.py`).
- README: примеры конфига с плейсхолдером `<КОРЕНЬ ПРОЕКТА>`, путь кэша моделей —
  `%LOCALAPPDATA%`/`STANZA_RESOURCES_DIR` вместо личного пути пользователя.

## 4.0.0 (2026-11-10)
- Новый инструмент `segment_german`: нарезка текста на блоки по правилу V4 (+ `with_check`).
- `segment_german` чистит «битый» текст (NBSP, мягкие переносы, лигатуры, прямые кавычки)
  и возвращает список правок в поле `normalized`.
- Убраны `constituency_german`, `analyze_german`, `calc_pause`: правило считает границы
  по дереву зависимостей, озвучка в проекте не нужна.
- Конвейер без модели составляющих: старт 3.7 → 2.0 с, меньше памяти.

## 3.0.0 (2026-11-10)
- Судья переведён на `правило/validator.py`: вердикт + коды нарушений
  (`ADP`, `FUNC`, `PUNCT`, `HYPHEN`, `QUOTE`, `MIN`, `MAX`, `SYL`), предупреждения и штрафы.
- `rule_self_test` проверяет разметку 52 (`bench/sets/corpus52.jsonl`), `rule_info` отдаёт параметры нарезки.
- Убраны перебор вариантов и его лимиты.

## 2.0.0 (2026-10-23)
- Судья правила: `check_segmentation`, `rule_self_test`, `rule_info` (путь — env `RULE_ROOT`).
- Логирование: `server.log` (вращение при >2 МБ) + stderr; каждый вызов инструмента — запись start/ok/error + время.
- Версии: `version.json` (`server_version`), поле `server_version` в `pipeline_info()`, запись START при запуске (версии Stanza/Torch/Python + версия правила).
- Судья принимает разбор самого сервера (`parse_source=mcp-payload`).

## 1.0.0
- `parse_german` (Stanza depparse German offline), MWT-поля + `tokens`.
- `constituency_german`, `calc_pause`, `pipeline_info`.
