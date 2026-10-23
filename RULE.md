# Тех Задание v3.0 — сегментация немецкого предложения по данным Stanza

## 1. Данные
Единственный источник — выход Stanza: id, text, lemma, upos, xpos, feats, head, deprel, is_mwt. Только над этими полями; внешние знания и паузы запрещены.
**Судья судит по тому же разбору, что видит LLM:** `rule.py --check ... --parse-file <parse_german.json>`. Без переданного разбора судья парсит сам и помечает `parse_source`.
## 2. Счёт слов
`lex_count(блока)` = число токенов с `upos ≠ PUNCT`; MWT (`is_mwt=true`, children>1) = 1; длина блока в символах — справочная величина, не участвует в выборе разбиения.
## 3. Атомарные единицы
`unit(w) = [min_leaf(w), max_leaf(w)]` для каждого прямого зависимого root, плюс интервал самого root; список упорядочен по `start_id`. MWT — неделимая единица.
## 4. Запрет реза (NO-CUT) — рёбра, которые не разрываются
| deprel / признак Stanza | что запрещено |
|---|---|
| `det, det:poss, amod, nummod, compound, flat, appos` → NOUN | рез между словом и его head-NOUN |
| `case` + `pobj/obl` | рез внутри PP (ADP ↔ NOUN) |
| NOUN с `xpos == TRUNC` (срезанный состав) | цепочка NOUN–(cc/conj)–NOUN атомарна — рез внутри неё (C1/C2) запрещён 
| MWT children | рез между частями |
| `aux, aux:pass, cop` | рез между зависимым и его head (глагольная рамка; v3: условие «той же леммы» отменено — оно невыполнимо: лемма aux = haben/sein/werden) |
| глагол-root (`xpos ∈ {VAFIN, VVFIN, VVPP}`) ↔ его aux-зависимый | рез между root-глаголом и его aux (v3: фикс составных времён, напр. «gelesen haben»)
| пара ADV/PART→ADV (лемматическая коррелятива) | рез между членами пары |


## 5. Легальные резы (SEAMS)
- **C1** — граница соседних unit по `start_id`.
- **C2** — перед любым токеном `deprel == cc`.
- **C3** — перед **всей цепочкой** `case/nmod/appos` при head-NOUN (цепочка = ADP-зависимое и все его подчинённые; рез перед первым токеном цепочки, НЕ перед её первым словом), если слева и справа ≥3 лексических слов. (v3: рез перед первым словом цепочек запрещён NO-CUT, формулировка уточнена.)
- **C4** — сразу после конечного глагола root (`xpos ∈ {VAFIN, VVFIN}`), если следующий токен имеет `deprel ∈ {advmod, cc}` И (`xpos == KON` ИЛИ `lemma ∈ {denn, dann, so}`). Набор `KON / denn / dann / so` фиксирован; всё остное (`PTKNEG`, напр. `nicht`) не входит.
- **C5** — перед токеном `deprel == mark` (`xpos=KOUS`), если слева и справа ≥3 лексических слов. (v3: новый класс; придаточные: «…, weil er müde ist», «Weil …, kam …»; статус verified (iter3)

Каждый класс seam хранится со статусом **verified / untested**; verified-классы зафиксированы и не удаляются без данных.


## 6. Пунктуация (PUNCT-glue)
- **P1**: терминальные `.`/`?`/`!` — к блоку, содержащему **последний токен предложения** (v3: фикс перфекта/модальных рамок: root = VVPP, aux = VAFIN после объектных блоков, «…gelesen.»).
- **P2**: все прочие знаки (`-`, `,`, скобки) — к **предшествующему** блоку; рез непосредственно перед ними запрещён независимо от `head`.
## 7. Ограничения блока
min=3 лексических слов — жёстко: блок <3 → слияние со **соседним** блоком (есть прямой зависимый root → расширяется root-блок; при двух — тот, где меньше lex-слов; равенство — левый); иначе — слей с наименьшим блоком. Повторять до >=3 во всех блоках. pref=[3,5]. cap=7: блок 6–7 слов допустим только при легальных seams (C1–C5) и без NO-CUT внутри; >7 — снимается.
## 8. Два режима: судья (verdict) и мнение машины (ранг)
### 8.1 Судья — проверка разбивки человека (главный режим цикла)
Verdict `compliant` ⇔ одновременно: (1) каждый рез разбивки покрыт C1–Cn и не попадает на NO-CUT/P2; (2) ни один блок не короче `min` (short-sentence exception: всё предложение < min ⇒ один блок); (3) ни один блок не длиннее `cap`; (4) блоки покрывают предложение целиком, без пропусков/пересечений/пустых; (5) P1/P2 соблюдены (терминальный знак в блоке с последним токеном, прочие знаки приклеены к предшествующему). Иначе `non_compliant`; если текст блока не найден в предложении — `invalid_input` (это НЕ дыра правила, дельта не готовится).
**Судья не решает, как резать.** Ранжирование в verdict не входит.
### 8.2 Мнение машины — перебор и ранжирование (справочно)
Seam-множество: C1∪C2∪C3∪C4∪C5 − NO-CUT − P2. Разбиения по seams → P1/P2 → min-слияние; снять NO-CUT, cap>7, <3. Ранжирование только по структуре Stanza; **критерии и их направления — данные правила в `config.json → rank.criteria`** (не код): `blocks_not_in_pref`, `min_merges`, `units_preserved`, `cuts_count`, `cut_positions`. Ранг 1 = `recommended`, остальные = `admissible`; в выводе судьи они идут в секции `machine_opinion` с пометкой, что это не истина. Критерий `cuts_count:desc` в базовом конфиге **выключен** (исторически был подгонкой под K3); включение — явная строка в конфиге + запись в LOG.
## 9. Выход
### 9.1 Судья `check()` (главный вывод цикла)
```json
{"language":"de","rule_version":"vN","config_hash":"<sha256>","parse_source":"mcp-payload|parse-cache|stanza",
 "verdict":"compliant|non_compliant|invalid_input","match":true|false,"human_rank":1|N|null,
 "violations":[{"type":"forbidden|missing|min|cap|coverage|block_not_found","pos":7,"rule":"case_obl"}],
 "diagnosis":{"cuts":[{"pos":7,"between":"an | Heizungsanlagen","status":"forbidden","rule":"case_obl","features":{...},"hint":"..."}],
   "effects":{"min_merge":[{"merges":1,"machine_blocks":[...]}],"cap":[{"block":[3,21],"lex_words":16}],"rank":{"human_rank":2,"human_key":{...},"rank1_key":{...}}},
   "coverage":{"covered":[5],"missing":[],"forbidden":[2]},
   "hints":["..."],"delta_required":true|false},
 "machine_opinion":{"enabled":true,"recommended":[...],"admissible_top":[...],"total_admissible":3,"human_rank":2,"note":"не истина"}}
```
`delta_required=true` только при `missing`/`forbidden` (дыра правила). `min`/`cap`/`coverage` — дырой не считаются.
### 9.2 Мнение машины `run()`
```json
{"language":"de","rule_version":"vN","parse_source":"...","rank_criteria":["blocks_not_in_pref:asc","min_merges:asc","units_preserved:desc","cut_positions:asc"],
 "recommended":[{"n":1,"text":"","lex_words":3,"toks":[1,2,3],"seams":["C1"]}],
 "admissible":[{"rank":2,"blocks":[...]}],"rejected":[{"variant":"","violations":["min"]}],
 "seam_classes_status":{"C1":"verified",...}}
```
## Файлы цикла
Машинальная версия правила: **reference/config.json**; референс-интерпретатор: **reference/rule.py** (см. PROLOG).
