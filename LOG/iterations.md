# Лог итераций + история правил (объединённый)

## 1. Таблица всех итераций (счётчик N, регресс)
N = номер последней зафиксированной версии правила. Текущая базовая — **v3**, N=3.

| # | Дата | rule_version | дельта (1 строка, только Stanza-поля) | corpus_added | regression | status |
|---|------|--------------|----------------------------------------|-------------|------------|        |
| 0 | —    | v1.0       | базовая версия (ex v5)                 | 0           | —          | base   |
| 1 | —    | v2.0       | §7 cap: блок 6–7 слов допустим при границах C1–C4 и без NO-CUT внутри; «union of units» отменено; §5 C4: набор = xpos=KON ∪ {denn,dann,so} (ex v6) | 1 | 1/1 pass | done   |
| 2 | —    | v3.0       | G1 P1→последний токен; G2 NO-CUT=aux/aux:pass/cop; G3 NO-CUT root↔aux; G4 C5 (deprel=mark, xpos=KOUS); G5 C3=цепочка целиком (ex v7) | 0 | 1/1 pass | done   |
| 3 | —    | v3.x       | iter3: C4/C5 verified; уточнения без изменения intent'а (C4 logic / TRUNC NO-CUT / min-merge); rule.py и будущие версии должны учитывать эти условия | 2 | 3/3 pass | done   |

(новая строка добавляется после каждой дельты; N = последняя зафиксированная версия)

## 2. История изменений правил (детально, для будущего ТЗ/разработчика)
### v1.0 — базовое правило
- Зафиксено: секции 1–9 ТЗ (данные; счёт слов; атомарные единицы; NO-CUT; SEAMS C1–C4; PUNCT P1/P2; ограничения блока min/pref/cap; детерминированный отбор; JSON-выход).
- Промт v1.0 был встроен в RULE v1.md.

### v1.1 — инфраструктура цикла (правило без изменений)
- Промт вынесен в PROMPT.md: жёсткий вход, 8 секций + JSON-итог, гейты до выпуска версии.
- Созданы: PROLOG; CORPUS/verified.jsonl; GAPS/registry.md; LOG/iterations; единый changelog (теперь — секция 2 этого файла).
- Критерии выхода в ТЗ зафиксированы (PROLOG): >=20 verified; все GAP resolved; последние 3 итерации только уточнения; регресс 100%.

### v2.0 — итерация 1 (кейс «Meine Dienstleistungen umfassen …»)
- §7 cap: блок 6–7 слов допустим, если все его границы — легальные seams (C1–C4) и внутри блока нет NO-CUT-ребра; условие «объединение целых unit» отменено.
- §5 C4: набор lemma зафиксирован как `xpos=KON ∪ {denn, dann, so}` (`PTKNEG`, напр. `nicht`, не входит).
- Статусы классов: C1/C2/C3 = verified (корпус iter1), C4 = untested.
- CORPUS/verified.jsonl: +1 кейс (iter1-umfassen-heizung, accepted=true).

### v3.0 — итерация 2 (формализация 6 дыр; rule.py выведен из репозитория)
- §6 P1: терминальный знак к блоку, содержащему **последний токен** предложения (G1: фикс перфекта/модальных рамок).
- §4 NO-CUT: глагольная рамка через `deprel ∈ {aux, aux:pass, cop}` (G2; условие «той же леммы» отменено — невыполнимо).
- §4 NO-CUT: рез между root-глаголом (`xpos ∈ {VAFIN, VVFIN, VVPP}`) и его aux (G3: фикс составных времён).
- §5 C5: новый класс — рез перед `deprel=mark` (`xpos=KOUS`), если слева/справа ≥3 lex-слов (G4: придаточные; статус untested).
- §5 C3: уточнено — рез перед **всей цепочкой** `case/nmod/appos`, не перед её первым словом (G5).
- PROMPT.md v1.2: база RULE v3, детерминированный шаг D по CORPUS/verified.jsonl (без rule.py), значения min=3, pref=[3,5], cap=7, C1..C5.
- LOG: N=2; GAPS: G1–G5 registered, status resolved.
- reference/rule.py выведен из репозитория (референс поддерживается отдельно).

### v3.x — iter3 (C4/C5 verified + уточнения)
- C5: тестовый кейс «Ich weiß es, weil er müde ist.» — mark/KOUS в середине; rank1 = единственный valid.
- C4: тестовый кейс «Er kam dann nach Hause.» — VVFIN+advmod/lemma; left block 2 lex <3 → min-merge; final rank1 = 1 block.
- Уточнения (без изменения intent'а): C4 logic (`xpos==KON` OR `lemma∈{denn,dann,so}`); TRUNC NO-CUT (NOUN xpos==TRUNC → chain атомарна); min-merge (детерминированный алгоритм).
- LOG: N=3; GAPS: C4/C5 → verified; PROLOG критерий №2 усилен (all G resolved + all seam classes verified).

### v3.y — упрощение (без изменения правила, только конвенция)
- Правило: отдельные файлы на версии → единый **RULE.md**; версии v1..v3 → git-теги.
- Создан **reference/config.json** (единый, без номера) — машинальная версия правила; внутреннее `"version":"v3"`.
- PROMPT v1.3: секция 5 = дельта (патч config + только изменившиеся §), а не весь файл.
- GAPS: таблица верификации seam-классов удалена (дубль); CORPUS: schema-example → отдельный **schema.jsonl**.
- LOG/iterations + CHANGELOG объединены в единый файл (текущий).
