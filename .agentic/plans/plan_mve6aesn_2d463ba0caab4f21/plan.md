# Plan plan_mve6aesn_2d463ba0caab4f21: Завершение RULE v7: PROMPT v5.2 + LOG/GAPS/CHANGELOG (без step 4) (revision 1)

## Objective
Завершить план RULE v7 без reference/rule.py: обновить PROMPT.md до v5.2 (база v7, детерминированный шаг D без ссылки на rule.py, значения min/pref/cap), синхронизировать LOG/iterations.md (v7), зарегистрировать GAP G1–G5 resolved, записать CHANGELOG v7.0; убрать из RULE v7.md отсылку к удалённому rule.py.

## Steps
1. RULE v7.md: удалить §«Референс-реализация» (reference/rule.py удалён); оставить принцип детерминированности в §8; поправить «Инфраструктура» на v7 без rule.py _(edit)_
2. PROMPT.md: версия → v5.2; «Внешние файлы» база RULE v7.md; шаг D — детерминированный прогон по CORPUS/verified.jsonl (без rule.py), конфликт-регламент; добавить min=3, pref=[3,5], cap=7; §5 вывода C1..C5 _(edit)_
3. LOG/iterations.md: строка v7.0 (delta G1–G5); синхронизировать «текущая базовая версия» v5→v7 _(edit)_
4. GAPS/registry.md: зарегистрировать G1..G5 со статусом resolved (P1-перфект, NO-CUT-рамка, aux-root, C5-mark, C3-цепочка) _(edit)_
5. CHANGELOG.md: запись v7.0 (6 дельт + PROMPT v5.2, rule.py выведен из репозитория) _(edit)_

## Files
- modify: RULE v7.md
- modify: PROMPT.md
- modify: LOG/iterations.md
- modify: GAPS/registry.md
- modify: CHANGELOG.md

## Risks
- RULE v7.md §«Референс-реализация» отсылал к rule.py — удаляем; принцип детерминированности остаётся в §8, но референтный код не в репозитории (поддерживается отдельно/рукой)
- PROMPT шаг D теперь описывает детерминированный прогон без конкретного файла — если потом нужен rule.py, добавится отдельной дельтой
- GAP G1–G5 маркируются resolved — статус зависит от того, что человек примет v7-разбивку; до этого они open
