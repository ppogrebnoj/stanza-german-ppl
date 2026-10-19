# Changelog RULE (единый, все версии)

## v1.0 — базовое правило
- Зафиксено: секции 1–9 ТЗ (данные; счёт слов; атомарные единицы; NO-CUT; SEAMS C1–C4; PUNCT P1/P2; ограничения блока min/pref/cap; детерминированный отбор; JSON-выход).
- Промт v1.0 был встроен в RULE v1.md.

## v1.1 — инфраструктура цикла (правило без изменений)
- Промт вынесен в PROMPT.md (v1.1): жёсткий вход, 8 секций + JSON-итог, гейты до выпуска версии.
- RULE v{N}.md — отдельный файл на версию в корне (базовая RULE v1.md).
- Созданы: PROTOCOL.md; CORPUS/verified.jsonl; GAPS/registry.md; LOG/iterations.md; единый CHANGELOG.md.
- Критерии выхода в ТЗ для программирования зафиксированы (PROTOCOL.md): >=20 verified; все GAP resolved; последние 3 итерации только уточнения; регресс 100%.

## v2.0 — итерация 1 (кейс «Meine Dienstleistungen umfassen …»)
- §7 cap: блок 6–7 слов допустим, если все его границы — легальные seams (C1–C4) и внутри блока нет NO-CUT-ребра; условие «объединение целых unit» отменено.
- §5 C4: набор lemma зафиксирован как `xpos=KON ∪ {denn, dann, so}` (`PTKNEG`, напр. `nicht`, не входит).
- Статусы классов: C1/C2/C3 = verified (корпус iter1), C4 = untested.
- CORPUS/verified.jsonl: +1 кейс (iter1-umfassen-heizung, accepted=true).

## v3.0 — итерация 2 (формализация 6 дыр; rule.py выведен из репозитория)
- §6 P1: терминальный знак к блоку, содержащему **последний токен** предложения (G1: фикс перфекта/модальных рамок).
- §4 NO-CUT: глагольная рамка через `deprel ∈ {aux, aux:pass, cop}` (G2; условие «той же леммы» отменено — невыполнимо).
- §4 NO-CUT: рез между root-глаголом (`xpos ∈ {VAFIN, VVFIN, VVPP}`) и его aux (G3: фикс составных времён).
- §5 C5: новый класс — рез перед `deprel=mark` (`xpos=KOUS`), если слева/справа ≥3 lex-слов (G4: придаточные; статус untested).
- §5 C3: уточнено — рез перед **всей цепочкой** `case/nmod/appos`, не перед её первым словом (G5).
- PROMPT.md v1.2: база RULE v3, детерминированный шаг D по CORPUS/verified.jsonl (без rule.py), значения min=3, pref=[3,5], cap=7, C1..C5.
- LOG/iterations.md: N=2; GAPS/registry.md: G1–G5 registered, status resolved.
- reference/rule.py выведен из репозитория (референс поддерживается отдельно).

## v3.x — iter3 (C4/C5 verified + уточнения; правило без изменения)
- C5: тестовый кейс «Ich weiß es, weil er müde ist.» — mark/KOUS в середине; rank1 = единственный valid.
- C4: тестовый кейс «Er kam dann nach Hause.» — VVFIN+advmod/lemma; left block 2 lex <3 → min-merge; final rank1 = 1 block.
- Уточнения (без изменения intent'а): C4 logic (`xpos==KON` OR `lemma∈{denn,dann,so}`); TRUNC NO-CUT (NOUN xpos==TRUNC → chain атомарна); min-merge (детерминированный алгоритм).
- LOG/iterations.md: N=3; GAPS: C4/C5 → verified; PROLOG criterion #2 strengthened (all G resolved + all seam classes verified).

## v3.y — Simplification (no rule changes, convention only)
- Rule consolidation: individual files per version (RULE v1..v3.md) → single **RULE.md**; versions v1..v3 → git tags.
- New file **reference/config.json** (single, unnumbered) — machine version of the rule; internal `"version":"v3"`.
- PROMPT v1.3: section 5 = delta (config patch + only changed sections), not whole file; external files → see PROLOG §files cycle.
- PROLOG: files cycle + gates (input format moved to PROMPT); versioning: single RULE.md + git tags, config.json unnumbered.
- GAPS: table of seam class verification removed (duplicates); CORPUS: schema-example → separate file **schema.jsonl**; reference/TZ_rule_py: trimmed (output JSON / gates / non-goals → references; current state and priorities moved to .agentic/MEMORY).
