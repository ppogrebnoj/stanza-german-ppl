# CHANGELOG — MCP-stanza-german (сервер)

## 2.0.0 (2026-10-23)
- Судья правила: `check_segmentation`, `rule_self_test`, `rule_info` (путь — env `RULE_ROOT`).
- Логирование: `server.log` (вращение при >2 МБ) + stderr; каждый вызов инструмента — запись start/ok/error + время.
- Версии: `version.json` (`server_version`), поле `server_version` в `pipeline_info()`, запись START при запуске (версии Stanza/Torch/Python + версия правила).
- Выводы: судья принимает разбор самого сервера; `parse_source=mcp-payload`; защита перебора (`max_seam_positions=12`, `max_admissible=5`).

## 1.0.0
- `parse_german` (Stanza depparse German offline), MWT-поля + `tokens`.
- `constituency_german`, `calc_pause`, `pipeline_info`.
