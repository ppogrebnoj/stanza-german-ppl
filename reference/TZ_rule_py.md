# ТЗ на проектирование rule.py — детерминированный референс-интерпретатор правила RULE.md

## 0. Суть и цель
**rule.py** — детерминированный референс-интерпретатор, формально реализующий актуальное правило `RULE.md` (v3) + его машинальную версию `reference/config.json`.
- **Вход:** текст одного предложения + config. Пакет (N предложений): rule.py вызывается на каждое отдельно — правило локально; LLM собирает единый ответ по PROMPT.
- **Выход:** разбиение `recommended` / `admissible` / `rejected` по данным Stanza (JSON, §8).

**Цель:** объективная, воспроизводимая и 100%-детерминированная проверка правила по `CORPUS/verified.jsonl` и верификация нового ground-truth-кейса.

**Ключевой принцип:** *правило = данные (конфиг), интерпретатор = код (статичный).* При новой версии патчится только config — не rule.py.

## 1. Архитектура: два слоя
### 1.1 Слой 1 — статичный интерпретатор (`rule.py`)
Не зависит от конкретной версии. Реализует пайплайн и алгоритмы; всё «что» берёт из конфига.
- `parse` — Stanza depparse (German, v1.15.0). В v3 условия C/NO-CUT/P используют **только** поля depparse (`id,text,lemma,upos,xpos,feats,head,dep,is_mwt`) + дерево зависимостей; constituency-дерево парсится опционально и сейчас не требуется для вычисления.
- `build_units` — атомарные unit по §3 RULE (MWT неделим).
- `seams` — seam-множество: **каждый C-класс = отдельная чистая функция** `c1..c5(tokens, config)` → набор позиций реза. Детальные определения — §2.
- `nocut` — рёбра NO-CUT по §4 RULE (из конфига; сравнение с seams — §2.6).
- `punct_glue` — P1/P2 по §6 RULE (из конфига; §2.7).
- `min_merge` — слияние по min по §7 RULE (детерминированный алгоритм из конфига; §2.8).
- `cap_check` — проверка cap (§2.9).
- `rank` — ранжирование по §8 RULE (**критерии статичны**, не в конфиге; §2.10).
- `render` — нормализация/вывод (§8).

### 1.2 Слой 2 — конфиг правила (`reference/config.json`)
Содержит «что» актуальной версии — **единственный изменяемый элемент при новой версии**. Единый файл (без номера); версия — внутреннее поле `"version"`; история — git commit + git tag v{n+1}.
- list C-seam classes (C1..C5) с условиями (Stanza-поля).
- list NO-CUT edges (условия deprel).
- P1/P2 config (terminal set, last-token rule).
- `min` / `pref` / `cap`, `min_merge`.
- `seam_classes_status` (verified / untested).
- `version`.

**При v{n+1}: патчим JSON — не трогаем rule.py.**

## 2. Точные определения алгоритма (обязательны для 3/3 pass)

Нумерация токенов 1..n по Stanza id. **Позиция реза p** = «рез после токена p» (между токенами p и p+1), валидна при p < n; эквивалентно — «рез перед токеном p+1».

### 2.1 build_units
Для каждого *прямого* зависимого root (`token.head == root.id`): `unit = [min_id, max_id]` поддерева этого токена. Плюс интервал самого root `[root.id, root.id]`. MWT: если токен `is_mwt=true` (children>1) — его unit расширяется на всю непрерывную цепь токенов с той же леммой; MWT неделим. Список units упорядочен по `start_id`.

### 2.2 C-классы
- **C1** — для *каждого* unit: рез после последнего его токена (`p = unit.max_id`), если p < n. (Структурный; выводится build_units, не в config.)
- **C2** — перед токеном `dep==cc`: `p = token.id - 1`.
- **C3** — перед *целой* цепью PP при head-NOUN. Находит: токен t с `dep∈{nmod}` и `head` — NOUN; chain = поддерева т (ADP + все потомки); first = min(chain). Если lex_left≥3 и lex_right≥3 — рез `p = first - 1`. Не перед первым *словом*, а перед всей цепью (включая ADP).
- **C4** — после root (`xpos∈{VAFIN,VVFIN}`), если следующий токен: `dep∈{advmod,cc}` И (`xpos==KON` ИЛИ `lemma∈{denn,dann,so}`). Фиксированный набор; PTKNEG (напр. `nicht`) не входит.
- **C5** — перед токеном `dep==mark`, `xpos==KOUS`; если lex_left≥3 и lex_right≥3 → `p = token.id - 1`.

`lex_left/p = число lex-токенов (upos≠PUNCT, MWT=1) слева от p; lex_right — справа.`
**S = C1∪C2∪C3∪C4∪C5 − NO-CUT − P2.**

### 2.3 NO-CUT — сравнение с seams
Для каждого типа рёбра в config `nocut` находим позицию(и), которую оно закрывает, и **убираем её из S** (если она там):
- `det→NOUN`: токен d (`dep∈{det,det:poss,amod,nummod,compound,flat,appos}`), head=NOUN → рез между d и head: p = max(d.id, head.id)-1 (только если adjacent).
- `case+obl`: токен c (`dep==case`, head=NOUN) → p = max(c.id, head.id)-1.
- `TRUNC atomic chain`: NOUN с `xpos==TRUNC` — цепь NOUN–(cc/conj)–NOUN атомарна: убираем все p внутри этой цепи (между её токенами).
- `mwt`: внутри MWT-цепи.
- `aux/cop`: токен a (`dep∈{aux,aux:pass,cop}`) → p = max(a.id, head.id)-1 (adjacent).
- `root↔aux`: root-глагол (`xpos∈{VAFIN,VVFIN,VVPP}`) ↔ прямой aux-зависимый.
- `ADV/PART pair` (лемматическая коррелятива): внутри пары.

### 2.4 P1/P2 — пунктуация
- **P2**: все знаки, не в `terminal_set` (`-`, `,`, скобки) → к *предшествующему* блоку; рез непосредственно перед ними запрещён: убираем p = q−1 (q — позиция знака), если q>1.
- **P1**: терминальные `.`/`?/!` → к блоку, содержащему *последний токен предложения*. В выводе блок, содержащий последний токен, всегда получает точку; рез после него не создаётся нового блока.

### 2.5 Перечисление разбиений
Все подмножества S → блоки подрядных токенов; применяем P1/P2 (знаки остаются в своих блоках) + min-merge. Снимаем варианты: cap>7, <3, NO-CUT внутри блока.

### 2.6 min_merge (детерминированный, из config `min_merge`)
Для каждого блока с lex<`min`:
1. Если в нём токен с head==root.id — слей **в блок, содержащий root**.
2. Иначе — слей в соседа с *меньшим* числом lex-слов (при равенстве — влево; если левого нет — вправо).
Повторять до тех пор, пока все блоки ≥`min`.

### 2.7 cap_check
Блок 6–7 слов допустим только если **все его границы — легальные seams (C1..C5) и внутри блока нет NO-CUT-ребра**. Блок >7 — вариант снимается.

### 2.8 rank (критерии статичны, не в config; §8 RULE)
Сортировать по tuple: (a) число блоков вне `pref`; (b) число обязательных min-слияний; (c) число unit, сохранённых целиком; (d) лексикографически — позиции seams слева направо. Ранг 1 = `recommended`; остальные валидные = `admissible`.

## 3. Вход / парсинг + кэш
- **Ввод:** текст одного предложения + config. *Пакет: rule.py на каждое отдельно.*
- **Парсинг:** Stanza depparse (German, v1.15.0). Формат полей идентичен MCP-инструменту `parse_german`: `id,text,lemma,upos,xpos,feats,head,dep,is_mwt` — кросс-проверка с ним обязательна.
- **Stanza API (v1.15.0, важно!):**
  - импортируем класс: `from stanza import Pipeline` (НЕ функция `stanza.pipeline()`);
  - запуск: `m(text)` (НЕ `.predict()`), вернёт `Document`;
  - поля деппарса — в `token.words[-1]`: `.id`(int), `.deprel`, `.head`, `.upos`, `.xpos`, `.lemma`; `is_mwt` — в `Token.is_mwt`; id токена = integer (не tuple);
  - **кэш модели** (offline): `STANZA_CACHE_DIR=C:/Users/BIGTER/AppData/Local/StanfordNLP/stanza/Cache` (версия `1.15.0/resources/de`); не скачивать в сеть.
- **Кэш parse** — по hash текста: `{text_hash → parse_result}`; при повторных запусках читаем из кэша. Кэш — не «кэш», а **факт**: если Stanza вернул X, это X; не пересчитываем.
- **Формат кэша:** JSONL (`text_hash → parse_json`), путь `reference/cache/`.

## 4. Схема конфига (`reference/config.json`, v3)
```json
{
  "version": "v3",
  "rule_file": "RULE.md",
  "min": 3,
  "pref": [3, 5],
  "cap": 7,
  "terminal_set": [".", "?", "!"],
  "min_merge": {"prefer": "head_root", "else": "fewer_lex_words", "tie": "left"},
  "seams": [
    {"class_id": "C1", "status": "verified"},
    {"class_id": "C2", "status": "verified", "condition":{"deprel":["cc"]}},
    {"class_id": "C3", "status": "verified", "condition":{"chain":["case","nmod","appos"],"head":"NOUN","scope":"whole_chain","min_left_lex":3,"min_right_lex":3}},
    {"class_id": "C4", "status": "verified", "after":{"root_xpos":["VAFIN","VVFIN"]},"next_token":{"deprel":["advmod","cc"],"xpos_or_lemma":["KON","denn","dann","so"]}},
    {"class_id": "C5", "status": "verified", "condition":{"deprel":["mark"],"xpos":"KOUS","min_left_lex":3,"min_right_lex":3}}
  ],
  "nocut": [
    {"deprel": ["det","det:poss","amod","nummod","compound","flat","appos"], "to": "NOUN"},
    {"deprel": ["case"], "with": ["pobj","obl"]},
    {"nouns_xpos":"TRUNC","atomic_chain":true},
    {"mwt": true},
    {"deprel": ["aux","aux:pass","cop"]},
    {"root_verb": ["VAFIN","VVFIN","VVPP"], "with_aux": true},
    {"pair": ["ADV","PART"], "lemma_corr": true}
  ],
  "punct": {"P1":"last_token","P2":"prev_block"},
  "seam_classes_status": {"C1":"verified","C2":"verified","C3":"verified","C4":"verified","C5":"verified"}
}
```
**v3:** C5 verified; NO-CUT = `aux/aux:pass/cop` + root↔aux + NOUN xpos==TRUNC (chain atomic); C4 = VVFIN+advmod/cc (xpos==KON OR lemma∈{denn,dann,so}); P1 = last_token; min-merge deterministic.

## 5. Пайплайн (детерминированный)
1. `parse` → токены.
2. `build_units` (MWT atomic).
3. `seams = union(c1..c5(tokens, config))`.
4. `S = seams − NO-CUT − P2`.
5. Перечислить разбиения по S → применить P1/P2 + min-merge.
6. Фильтр: cap>7, <3, NO-CUT внутри блока.
7. Rank (a..d).
8. Выход: `recommended` (ранг 1), `admissible` (остальные), `rejected` (violations).

## 6. Детерминизм
- Один input → один output (**hash-верифицируемо**): сериализуй выход в JSON со sorted keys, sha256; два вызова с одним input+config+cache → identical hash.
- Нет случайности, нет LLM-opinions.
- Детерминированность: один текст + версия Stanza + одно содержимое config → один результат (config = git-commit + внутреннее поле версии; rule.py читает только текущий config).

## 7. Версионирование / синк с RULE.md
- **rule.py** — статичный, **не версируется**.
- **config.json** — единый файл (без номера), внутреннее `"version"` = версия правила.
- **Синхронизация:** при v{n+1} патчим `config.json` + обновляем § в `RULE.md`; git commit + tag v{n+1}. rule.py не трогаем.
- **Верификация синхронности:** config «полный» — все правила RULE.md в config; если нет → тест fail.

## 8. Выход JSON (точный формат)
```json
{
  "language": "de",
  "rule_version": "v3",
  "recommended": [
    {"n": 1, "text": "…", "lex_words": 3, "toks": [1,2,3], "seams": ["C1"]}
  ],
  "admissible": [],
  "rejected": [
    {"variant": "", "violations": ["NO-CUT: det(4)->NOUN(5)"]}
  ],
  "seam_classes_status": {"C1":"verified","C2":"verified","C3":"verified","C4":"verified","C5":"verified"}
}
```
- `recommended` — только ранг 1 (один вариант). `admissible` — остальные валидные. `rejected` — с `violations`.
- `text` блока = исходный текст токенов (включая знаки); `toks` = list id; `seams` = классы, по которым сделан этот блок.

## 9. Тесты / верификация
- **`self_test()`** — правило воспроизводит все verified-кейсы `CORPUS/verified.jsonl` (accepted=true). **Критерий pass:** `[b.text for b in recommended] == case["blocks"]` (строгое совпадение по порядку и количеству; текст нормализовать: trim + collapse whitespace). Вывод — только pass/fail по каждому кейсу.
- **Determinism check** — один input → один output (sha256, §6).
- **Config completeness** — все правила RULE.md в config; если нет → fail.
- **New case verification** — новый ground-truth-кейс: rule.py воспроизводит или gap.
- **Regression 100%** — все verified-кейсы без конфликтов (3/3 pass).

## 10. Acceptance-гейты / Definition of Done
Выход допустим только когда **все** условия выполнены:
1. `rule.py` существует, запускается (`python reference/rule.py "…"`), выводит §8 JSON.
2. `self_test()` = **3/3 pass** по текущему `CORPUS/verified.jsonl` (3 verified-кейса).
3. **Determinism check** passes (sha256 identical).
4. **Config completeness** passes.
5. Запуск без кэша (чистый) даёт тот же результат — детерминизм подтверждён.
Дополнительно: PROLOG §Критерии выхода в ТЗ (4 условия) — для будущего v8+; сейчас только пункты 1–5.

## 11. Environment / Run
- **Python:** 3.11; **dependency:** `stanza==1.15.0`. German depparse model — в кэше MCP (offline), НЕ скачивать.
- **Кэш модели:** `STANZA_CACHE_DIR=C:/Users/BIGTER/AppData/Local/StanfordNLP/stanza/Cache` (стандартный Stanza-path: `1.15.0/resources/de`). rule.py должен задавать его при запуске.
- **Run:** `python reference/rule.py "<sentence>"`; `self_test()` — `python reference/rule.py --self-test`.
- **Layout:**
```
reference/
├── rule.py          # статичный интерпретатор (создаётся)
├── config.json      # текущий конфиг (patch при dельте; без номера)
├── cache/           # parse-кэш
└── TZ_rule_py.md    # это ТЗ
```

## 12. Edge cases
- **MWT** (`is_mwt=true`, children>1) — atomic, неделим.
- **Punctuation:** P1 = last token; P2 = non-terminal → prev block.
- **Cap:** блок 6–7 слов допустим только если все seams legal и нет NO-CUT внутри.
- **Min:** блок <3 → merge (детерминированный алгоритм по config).
- **Empty blocks** — не допускаются.

## 13. Workflow v{n+1}
1. Человек даёт ground-truth-кейс (по PROMPT, может быть пакетом).
2. LLM: parse, seam-разбор, delta, RULE.md + config.json (патч), регресс.
3. **rule.py:** патчим `config.json` (добавляем C-class / меняем NO-CUT); rule.py не трогаем.
4. rule.py: `self_test()` → 100% regression.
5. CORPUS: новый verified-кейс.
6. `LOG/iterations` (таблица + история), GAPS; git commit + tag v{n+1}.

## 14. Ground-truth appendix (3 verified-кейса — эталон для self_test)
> Разбор по реальному Stanza (v1.15.0). rule.py должен давать ровно эти `recommended`-блоки.

**K1: «Meine Dienstleistungen umfassen …»** (cap-relax)
- root=3 `umfassen`(VVFIN); det 6→7 NO-CUT; C3 chain {16..20} first=16 min-left≥3 min-right≥3; C2 cc(19) und — TRUNC chain {17,19,20} атомарно.
- NO-CUT: det6→7; P2 comma(10) убирает p9; TRUNC chain{17,19,20} убирает p18. S={2,3,5,7,10,15}; rank1 = cuts {3,10,15} (блок 6 слов — cap-relax, валиден). **recommended = 4 blocks:**
  `["Meine Dienstleistungen umfassen", "nicht nur die Arbeit an Heizungsanlagen,", "sondern auch die komplette Installation", "von Wasser- und Abwassersystemen."]`

**K2: «Er kam dann nach Hause.»** (min-merge → 1 block)
- root=2 `kam`(VVFIN); C4 cut after 2; P2 убирает рез перед period. Все блоки <3 lex → min_merge слей в root → 1 block. **recommended = 1 block:**
  `["Er kam dann nach Hause."]`

**K3: «Ich weiß es, weil er müde ist.»** (C5 + NO-CUT)
- root=2 `weiß`; C5 mark/KOUS(5) min-left≥3 min-right≥3; NO-CUT cop(8) head=7 → res 7|8; P1 period→last block. **recommended = 2 blocks:**
  `["Ich weiß es,", "weil er müde ist."]`

## 15. План B (отказ от конфига)
Если не использовать config: rule.py с встроенными правилами (функции C1..Cn внутри кода). При v{n+1} правим rule.py (не только config). Минус: сложнее читать как ТЗ; выше риск. **Данное ТЗ использует подход A (config, единый файл) как основной.**
