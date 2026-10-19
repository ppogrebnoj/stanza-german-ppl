# Plan plan_mvbkipke_d5db927e1c3c4991: RULE v7: формализация 6 дыр правила + автоматический регресс (revision 1)

## Objective
Устранить формальные дыры правила v6, найденные проверкой на Stanza, и сделать регресс (шаг D) исполняемым, а не «на словах».

## Steps
1. RULE v7.md: P1 → «терминальный знак к блоку, содержащему последний токен предложения» (.fixes перфект/модальный root) _(edit)_
2. RULE v7.md §4: NO-CUT глагольной рамки через deprel ∈ {aux, aux:pass, cop} (убрать невыполнимое условие «той же леммы»); NO-CUT рез между глаголом-root и его aux _(edit)_
3. RULE v7.md §5: новый класс C5 — рез перед токеном deprel=mark (KOUS), если слева и справа ≥3 lex-слов; C3 переформулировать: рез перед всей цепочкой case/nmod/appos, не перед её первым словом _(edit)_
4. reference/rule.py: детерминированный референс правила (parse_german → seam-множество C1..C5 → разбиения → P1/P2 → min-слияние → cap → ранжирование) + self-check на кейсе iter1-umfassen-heizung и 4 контрольных предложениях _(command)_
5. Обновить PROMPT.md (v5.2): шаг D = запуск reference/rule.py, регресс по CORPUS/verified.jsonl; §5 — определить min/pref/cap _(edit)_
6. LOG/iterations.md: строка 2 (v7.0); синхронизировать «текущая базовая версия» в LOG/PROTOCOL/MEMORY (v6 → v7) _(edit)_
7. GAPS/registry.md: зарегистрировать найденные GAP (G1 P1-перфект, G2 NO-CUT-рамка, G3 aux-root, G4 придаточные mark, G5 C3-цепочка) со статусом resolved после дельт _(edit)_

## Files
- create: RULE v7.md
- create: reference/rule.py
- modify: PROMPT.md
- modify: LOG/iterations.md
- modify: GAPS/registry.md
- modify: CHANGELOG.md

## Commands
- python reference/rule.py

## Risks
- C5 — новый seam-класс: это нарушение критерия «последние 3 итерации только уточнения»; протокол допускает новые классы до накопления 20 кейсов, но это явная смена профиля правила
- C5/NO-CUT-рамка не верифицированы человеком (untested) — статус в правиле будет untested, verified только после вашего принятого разбиения
- reference/rule.py — первый код проекта; он реализует правило v7 буквально, его расхождения с RULE v7.md надо читать как баг правила, а не скрипта
