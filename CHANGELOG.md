# Changelog RULE (единый, все версии)

## v5.0 — базовое правило
- Зафиксено: секции 1–9 ТЗ (данные; счёт слов; атомарные единицы; NO-CUT; SEAMS C1–C4; PUNCT P1/P2; ограничения блока min/pref/cap; детерминированный отбор; JSON-выход).
- Промт v5.0 был встроен в RULE v5.md.

## v5.1 — инфраструктура цикла (правило без изменений)
- Промт вынесен в PROMPT.md (v5.1): жёсткий вход, 8 секций + JSON-итог, гейты до выпуска версии.
- RULE v{N}.md — отдельный файл на версию в корне (базовая RULE v5.md).
- Созданы: PROTOCOL.md; CORPUS/verified.jsonl; GAPS/registry.md; LOG/iterations.md; единый CHANGELOG.md.
- Критерии выхода в ТЗ для программирования зафиксированы (PROTOCOL.md): >=20 verified; все GAP resolved; последние 3 итерации только уточнения; регресс 100%.

## v6.0 — итерация 1 (кейс «Meine Dienstleistungen umfassen …»)
- §7 cap: блок 6–7 слов допустим, если все его границы — легальные seams (C1–C4) и внутри блока нет NO-CUT-ребра; условие «объединение целых unit» отменено.
- §5 C4: набор lemma зафиксирован как `xpos=KON ∪ {denn, dann, so}` (`PTKNEG`, напр. `nicht`, не входит).
- Статусы классов: C1/C2/C3 = verified (корпус iter1), C4 = untested.
- CORPUS/verified.jsonl: +1 кейс (iter1-umfassen-heizung, accepted=true).

## v7.0 — итерация 2 (формализация 6 дыр; rule.py выведен из репозитория)
- §6 P1: терминальный знак к блоку, содержащему **последний токен** предложения (G1: фикс перфекта/модальных рамок).
- §4 NO-CUT: глагольная рамка через `deprel ∈ {aux, aux:pass, cop}` (G2; условие «той же леммы» отменено — невыполнимо).
- §4 NO-CUT: рез между root-глаголом (`xpos ∈ {VAFIN, VVFIN, VVPP}`) и его aux (G3: фикс составных времён).
- §5 C5: новый класс — рез перед `deprel=mark` (`xpos=KOUS`), если слева/справа ≥3 lex-слов (G4: придаточные; статус untested).
- §5 C3: уточнено — рез перед **всей цепочкой** `case/nmod/appos`, не перед её первым словом (G5).
- PROMPT.md v5.2: база RULE v7, детерминированный шаг D по CORPUS/verified.jsonl (без rule.py), значения min=3, pref=[3,5], cap=7, C1..C5.
- LOG/iterations.md: N=2; GAPS/registry.md: G1–G5 registered, status resolved.
- reference/rule.py выведен из репозитория (референс поддерживается отдельно).
