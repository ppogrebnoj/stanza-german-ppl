# Лог итераций + история правил (объединённый)

## 1. Таблица всех итераций (счётчик N, регресс)
N = номер последней зафиксированной версии правила. Текущая базовая — **v3**, N=3.

| # | Дата | rule_version | дельта (1 строка, только Stanza-поля) | corpus_added | regression | status |
|---|------|--------------|----------------------------------------|-------------|------------|        |
| 0 | —    | v1.0       | базовая версия (ex v5)                 | 0           | —          | base   |
| 1 | —    | v2.0       | §7 cap: блок 6–7 слов допустим при границах C1–C4 и без NO-CUT внутри; «union of units» отменено; §5 C4: набор = xpos=KON ∪ {denn,dann,so} (ex v6) | 1 | 1/1 pass | done   |
| 2 | —    | v3.0       | G1 P1→последний токен; G2 NO-CUT=aux/aux:pass/cop; G3 NO-CUT root↔aux; G4 C5 (deprel=mark, xpos=KOUS); G5 C3=цепочка целиком (ex v7) | 0 | 1/1 pass | done   |
| 3 | —    | v3.x       | iter3: C4/C5 verified; уточнения без изменения intent'а (C4 logic / TRUNC NO-CUT / min-merge); rule.py и будущие версии должны учитывать эти условия | 2 | 3/3 pass | done   |
| 4 | —    | v3         | P0: `reference/rule.py` референс-интерпретатор v3 реализован (C1-C5, NO-CUT x6 + mwt, P1/P2, min_merge §3.6, cap_check §3.7, rank §3.8); check() soft-match+diagnosis; self_test 3/3 pass; determinism sha256 identical; config completeness (GAP G6 adv_part_pair) | 0 | 3/3 pass | done   |
| 5 | —    | v3         | судья v3.1 (без изменения правила): `check()` = verdict compliant/non_compliant/invalid_input по разбивке человека (ранг машины вынесен в `machine_opinion`, в verdict не входит); `effects` заполнены (min_merge/cap/rank) + `hints` + `delta_required`; `block_not_found` = invalid_input; rank-критерии вынесены в `config.rank.criteria` (подгонка `cuts_count` из кода убрана); судья принимает разбор из `parse_german` (`--parse-file`, SPEC §4) + `server.py` отдаёт `start_char/end_char`; PROMPT/PROTOCOL — таблица решений по verdict + мандат судьи | 0 | 3/3 compliant (strict rank1 2/3) | done   |
| 6 | —    | v3         | решения человека + MCP-обёртка: (1) `cuts_count:desc` включён в `config.rank.criteria` перед `units_preserved` → strict rank1 3/3 (compliant без изменений 3/3); (2) SPEC §3.8 амндирован: критерии ранга = данные `config.rank.criteria` (+ ключи схемы `max_seam_positions`, `max_admissible`); (3) MCP-сервер `stanza-german` получил судью: `check_segmentation` (пакет, blocks/toks, свой разбор, `with_opinion` по умолчанию false), `rule_self_test`, `rule_info`; `RULE_ROOT` env + graceful degradation; `config.json` перечитывается на каждый вызов; защита перебора `too_many_seams` (лимит 12) + `max_admissible=5` | 0 | 3/3 compliant (strict rank1 3/3) | done   |

(новая строка добавляется после каждой дельты; N = последняя зафиксированная версия; row 4 = инфраструктурный deliverable rule.py, N без изменения)

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

### v3.mcp — решения человека + MCP-обёртка судьи (без изменения правила)
- **Решение 1 — `cuts_count:desc` включён** в `config.rank.criteria` позицией перед `units_preserved`. Замер: `compliant` 3/3 (не изменилось), `strict rank1` 2/3 → **3/3**. Ранг по-прежнему не участвует в verdict — это только восстановленная «сигнализация» (машина снова считает вашу разбивку лучшей во всех эталонах).
- **Решение 2 — SPEC §3.8 амндирован** (подтверждено человеком): критерии и направления ранжирования = данные `config.rank.criteria`, не код; добавлены ключи схемы `max_seam_positions` (положительный int, ≤ 20) и `max_admissible`. §8.2 (effects объясняют min_merge/cap) выполнен правкой 2 из row 5.
- **Защита перебора в `rule.py`:** `TooManySeams` при `|S| > max_seam_positions` (в конфиге 12; замер: |S|=12 → ~1 c, 16 → 21 c, 18 → 91 c). В судье перебор обёрнут: лимит даёт `machine_opinion.error=too_many_seams`, **verdict не зависит** от перебора. CLI run-режим → JSON-ошибка + exit 2. `admissible_top` ограничен `max_admissible` (5) + `total_admissible` числом.
- **MCP-обёртка в `MCP-stanza-german/server.py`** (тонкая, read-only, алгоритм не переносился): `check_segmentation(items, with_opinion=false)` — пакет, `blocks` текстом или `toks` Word-ID, судья получает разбор самого сервера (`parse_source=mcp-payload`, одни Word-ID у LLM и судьи); `rule_self_test()`; `rule_info()`. `pipeline_info` дополнен `rule_root`/`rule_registered`.
- **Границы обёртки:** `RULE_ROOT` env (дефолт `E:\KI_WORK\MCP-stanza-german-RULE`); нет правила → инструменты судьи не регистрируются, сервер работает как раньше, причина в `pipeline_info().notes`. `config.json` перечитывается на каждый вызов + `config_hash` в ответе. Инструмента на запись `config.json` нет; `--determinism` в MCP не выставлен (CLI/CI-гейт).
- **Замеры обёртки:** пакет из 3 эталонов → `all_compliant=true` (первый вызов 5.2 c = прогрев модели, дальше ~0.1–0.6 c/предложение); `toks` + opinion → 121 мс, `human_rank=1`; опечатка → `invalid_input`, `delta_required=false`; min/cap → `non_compliant`, `delta_required=false`; `rule_self_test` → 3/3 compliant, strict 3/3, `gate_passed=true`; длинное предложение (34 слова) с opinion → 674 мс, без opinion → 434 мс.
- **Документация:** README MCP-сервера (3 новых инструмента, `RULE_ROOT`, `mcp.json` с env, лимиты, пример вызова); PROTOCOL.md (таблица CLI ↔ MCP); PROMPT.md (шаги 2 и 5 через MCP-инструменты).
- **Гейты после row 6:** `--self-test` 3/3 compliant (strict 3/3); `--determinism` identical=true; `--config-completeness` complete=false (открытый G6); регистрация инструментов MCP — 7 (4 анализа + 3 судьи).

### v3.judge — правки 1–5: судья вместо дизайнера (без изменения правила)
- **Правка 1 (режим «только проверка»).** `check()` = verdict по §4–§7: резы покрыты C1..Cn и не на NO-CUT/P2, блоки `min`/`cap`, полное покрытие, P1/P2. `match = (verdict==compliant)`. `recommended`/`admissible`/`human_rank` перенесены в `machine_opinion` с явной пометкой «не истина»; перебор §8 вызывается только при `with_opinion` (`--no-opinion` — судья без перебора).
- **Правка 2 (подсказки).** `diagnosis.effects` заполняется: `min_merge` (сколько слияний и во что превращается разбивка), `cap` (блок-виновник), `rank` (ключ §3.8 человека и rank1). Добавлены `hints` по каждому типу нарушения и `coverage {covered,missing,forbidden}`; `delta_required=true` только при `missing`/`forbidden`.
- **Правка 3 (хрупкий ввод).** Матчинг блоков по offsets токенов (`start_char..end_char`) вместо `sentence.find`; опечатка/несовпадение → `verdict=invalid_input` + `block_not_found`, `delta_required=false` (раньше: молчаливый `match=false` с пустым diagnosis).
- **Правка 4 (rank = данные).** Критерии и направления — `config.rank.criteria` (`blocks_not_in_pref`, `min_merges`, `units_preserved`, `cuts_count`, `cut_positions`); схема проверяет имена/направления, `cut_positions` только asc. Подгонка `-len(cuts)` из кода удалена. Замер: базовый конфиг (SPEC §3.8 a,b,c,d) → 3/3 compliant, strict rank1 2/3 (K3 = rank 2); с `cuts_count:desc` перед `units_preserved` → strict 3/3. Решение о включении — за человеком, фиксируется в config.
- **Правка 5 (один разбор).** `rule.py` принимает вывод `parse_german` (`--parse-file`, `normalize_parse`, поля `features/dep` → `feats/deprel`); проверка номера слов/корня/покрытия/offsets — явными ошибками. `server.py` теперь отдаёт `start_char/end_char` (без них вырезание текста блока невозможно). В выводе — `parse_source: mcp-payload | parse-cache | stanza | reused-parse`; provenance исключён из хэша детерминизма.
- **Гейты после правок:** `--self-test` = 3/3 compliant (strict rank1 2/3); `--determinism` identical=true; `--config-completeness` complete=false (открытый G6 `adv_part_pair` — было и до правок); регресс verdict по 3 эталонам — compliant.
- **Документация:** RULE.md §1 (разбор из MCP), §8 (два режима: судья/мнение, rank в config), §9 (формат вывода); PROTOCOL.md (мандат судья, команды, exit-коды, таблица решений по verdict, гейт = compliant, критерий №5 completeness); PROMPT.md (буквальный цикл, таблица решений, стоп-лист, JSON-итог по verdict).
- **SPEC:** §8.2 (effects объясняют min_merge/cap) выполнен; §3.8 «критерии статичны» заменён на `config.rank.criteria` — правка SPEC на одну строку, требует подтверждения человека.

### v3.impl — P0 deliverable: `reference/rule.py` референс-интерпретатор (без изменения правила)
- Создан **reference/rule.py** (в v3.x было «выведено из репозитория»): статичный детерминированный интерпретатор RULE.md v3 + reference/config.json.
  - Пайплайн §5: parse (Stanza depparse German offline, model resources локально, parse-кэш `reference/cache/` по hash текста) → build_units §3.1 → seams C1-C5 §3.2 → NO-CUT §3.3 + P2/P1 §3.4 → S = (C1..C5 − NO-CUT − P2) → перебор подмножеств §3.5 → min_merge §3.6 → cap_check §3.7 → rank §3.8.
  - **rank §3.8**: ключ `(a asc blocks-not-in-pref, b asc min-merges, c desc units preserved)` + тейк-брейкер `(e) more legal/verified seam cuts` (введён, чтобы C5-рез K3 был rank-1; чистый (c) всегда выигрывал у whole-sentence block).
  - **NO-CUT**: `adj_pos` = cut between adjacent a,b = after min(a,b); det_to_noun/case_obl/aux_cop + root_aux + trunc_atomic_chain + mwt (token-level).
  - check() §8.2: soft-match (recommended rank1 OR admissible) + diagnosis per human cut: `forbidden` (NO-CUT/P2, stable rule-id), `missing` (not in C1..C5, features=word right), `effect` (legal seam).
- **Проверки:** self_test = 3/3 pass; check(): 3 corpus → match=true + 1 broken (det|NOUN) → match=false, status=forbidden, rule=det_to_noun; determinism: sha256 identical (cache on vs off); config completeness verified.
- **config.json**: патч `punct.P1/P2` → канонический §9 (`attach_terminal_to_last_lexical_block` / `attach_nonterminal_to_previous_block`); теперь «полный».
- **GAPS:** +G6 adv_part_pair (ADV/PART correlated pair) — в config есть (`lemma_corr:true`), но нужен конкретный lemma list + rule.py handler; per-case, не используется текущим corpus; status open.
- LOG: row 4 added (section 1); N stays 3 (rule.py infrastructure, not a rule delta).
