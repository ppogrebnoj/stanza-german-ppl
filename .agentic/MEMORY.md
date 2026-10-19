## RULE v3 — текущее состояние и NEXT (MCP-stanza-german-RULE)

**Состояние (после упрощения, N=3):**
- Правило — единый **RULE.md** (v3); версии v1/v2/v3 — git-теги (`git checkout <tag>`), история дельт — LOG/iterations.md. (Реноумерация: ex v5→v1, v6→v2, v7→v3; commit 130744c.)
- Машинальная версия правила — **reference/config.json** (единый файл, без номера; `"version":"v3"`). Created при упрощении; схема по reference/TZ_rule_py.md §4.
- Все C1–C5 = verified; G1–G5 = resolved; verified-кейсов: 3 / нужно 20 (критерий выхода в ТЗ).

**NEXT:**
1. Продолжение цикла итераций: человек даёт ground-truth — LLM по PROMPT.md (дельта = патч config.json + обновлённые § RULE.md, не весь файл).
2. Реализация `reference/rule.py` + `self_test()` по reference/TZ_rule_py.md (P0: статичный интерпретатор; P1: self_test + regression; после этого шаг D в PROMPT — прогон скриптом, регресс без чтения корпуса).

**Файлы цикла:** RULE.md / PROMPT.md / PROTOCOL (файлы + гейты) / CORPUS (verified.jsonl + schema.jsonl) / GAPS/registry.md / LOG/iterations.md (лог + changelog)
