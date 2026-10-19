# ТЗ на проектирование rule.py — детерминированный референс-интерпретатор правила RULE.md

## 0. Суть и цель
**rule.py** — детерминированный референс-интерпретатор, формально реализующий актуальное правило `RULE.md` (v3) + его машинульную версию `reference/config.json`.
- **Вход:** немецкое предложение + config.
- **Выход:** разбиение `recommended` / `admissible` / `rejected` по данным Stanza (JSON, §9 RULE).

**Цель:** объективная, воспроизводимая и 100%-детерминированная проверка правила по `CORPUS/verified.jsonl` и верификация нового ground-truth-кейса.

**Ключевой принцип:** *правило = данные (конфиг), интерпретатор = код (статичный).* При новой версии патчится только config — не rule.py.

## 1. Архитектура: два слоя
### 1.1 Слой 1 — статичный интерпретатор (`rule.py`)
Не зависит от конкретной версии. Реализует пайплайн и алгоритмы; всё «что» берёт из конфига.
- `parse` — Stanza depparse + constituency (или кэш).
- `build_units` — атомарные unit по §3 RULE (MWT неделим).
- `seams` — seam-множество: **каждый C-класс = отдельная чистая функция** `c1..cN(tokens, config)` → набор позиций реза.
- `nocut` — рёбра NO-CUT по §4 RULE (из конфига).
- `punct_glue` — P1/P2 по §6 RULE (из конфига).
- `min_merge` — слияние по min по §7 RULE (детерминированный алгоритм из конфига).
- `cap_check` — проверка cap.
- `rank` — ранжирование по §8 RULE (**критерии статичны**, не в конфиге).
- `render` — нормализация/вывод.

### 1.2 Слой 2 — конфиг правила (`reference/config.json`)
Содержит «что» актуальной версии — **единственный изменяемый элемент при новой версии**. Единый файл (без номера); версия — внутреннее поле `"version"`; история — git commit + git tag v{n+1}.
- list C-seam classes (C1..Cn) с условиями (Stanza-поля).
- list NO-CUT edges (условия deprel).
- P1/P2 config (terminal set, last-token rule).
- `min` / `pref` / `cap`, min_merge.
- `seam_classes_status` (verified / untested).
- `version`.

**При v{n+1}: патчим JSON — не трогаем rule.py.**

## 2. Вход / парсинг + кэш
- **Ввод:** текст одного предложения + config. *Пакет (N предложений): rule.py вызывается на каждое предложение отдельно — правило локально, кросс-предложение контекста нет; LLM собирает единый ответ по PROMPT.*
- **Парсинг:** Stanza depparse + constituency (Stanza 1.15.0).
- **Кэш** — по hash текста: `{text_hash → parse_result}`. При повторных запусках читаем из кэша.
- **Детерминированность:** один текст → один parse → один результат. Кэш — не «кэш», а **факт**: если Stanza вернул X, это X; не пересчитываем.
- **Формат кэша:** JSONL (`text_hash → parse_json`).

## 3. Модель данных
- `Token`: `{id, text, lemma, upos, xpos, feats, head, deprel, is_mwt}`.
- `Block`: `{n, text, lex_words, toks:[ids], seams:[class], status}`.
- `Variant`: `{blocks, rank, admissible, violations:[]}`.
- `lex_count(блока)` = токенов с `upos ≠ PUNCT`; MWT = 1.

## 4. Схема конфига (`reference/config.json`, v3)
```json
{
  "version": "v3",
  "rule_file": "RULE.md",
  "min": 3,
  "pref": [3, 5],
  "cap": 7,
  "terminal_set": [".", "?", "!"],
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
  "punct": {"P1":"last_token","P2":"prev_block"}
}
```
**v3:** C5 verified; NO-CUT = `aux/aux:pass/cop` + root↔aux + NOUN xpos==TRUNC (chain atomic); C4 = VVFIN+advmod/cc (xpos==KON OR lemma∈{denn,dann,so}); P1 = last_token; min-merge deterministic.

## 5. Пайплайн (детерминированный)
1. `parse` → токены.
2. `build_units` (MWT atomic).
3. `seams = union(c1..cN(tokens, config))` — каждый class → set позиций.
4. `S = seams − NO-CUT − P2`.
5. Перечислить разбиения по S → применить P1/P2 + min-merge.
6. Фильтр: cap>7, <3, NO-CUT внутри блока.
7. Rank: (a) блоки вне `pref`, (b) min-слияния, (c) unit сохранены, (d) lex-позиции seams.
8. Выход: `recommended` (ранг 1), `admissible` (остальные), `rejected` (violations).

## 6. Детерминизм
- Один input → один output (**hash-верифицируемо**).
- Нет случайности, нет LLM-opinions.
- Детерминированность: один текст + версия Stanza + одно содержимое config → один результат (config = git-commit + внутреннее поле версии; rule.py читает только текущий config).

## 7. Версионирование / синк с RULE.md
- **rule.py** — статичный, **не версируется**.
- **config.json** — единый файл (без номера), внутреннее `"version"` = версия правила.
- **Синхронизация:** при v{n+1} патчим `config.json` + обновляем соответствующие § в `RULE.md`; git commit + tag v{n+1}. rule.py не трогаем.
- **Верификация синхронности:** config «полный» — все правила RULE.md в config; если нет → тест fail.

## 8. Выход JSON
Формат — §9 актуального правила `RULE.md` (и машиночитаемый блок итога PROMPT). Не дублируем: единый источник формата.

## 9. Тесты / верификация
- **`self_test()`** — правило воспроизводит все verified-кейсы `CORPUS/verified.jsonl` (accepted=true); вывод — только pass/fail по каждому кейсу.
- **Determinism check** — один input → один output (hash).
- **Config completeness** — все правила RULE.md в config; если нет → fail.
- **New case verification** — новый ground-truth-кейс: rule.py воспроизводит или gap.
- **Regression 100%** — все verified-кейсы без конфликтов.

## 10. Acceptance-гейты (PROTOCOL)
См. PROLOG §Критерии выхода в ТЗ для программирования (4 условия). Дополнительно: config completeness (§9) — технический гейт синхронности RULE.md ↔ config.json.

## 11. Layout
```
reference/
├── rule.py          # статичный интерпретатор (создаётся отдельной дельтой)
├── config.json      # текущий конфиг (патчится при каждой дельте; без номера)
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
1. Человек даёт ground-truth-кейс (по PROMPT).
2. LLM: parse, seam-разбор, delta, RULE.md + config.json (патч), регресс.
3. **rule.py:** патчим `config.json` (добавляем C-class / меняем NO-CUT); rule.py не трогаем.
4. rule.py: `self_test()` → 100% regression.
5. CORPUS: новый verified-кейс.
6. `LOG/iterations` (таблица + история), GAPS; git commit + tag v{n+1}.

## 14. План B (отказ от конфига)
Если не использовать config: rule.py с встроенными правилами (функции C1..Cn внутри кода). При v{n+1} правим rule.py (не только config). Минус: сложнее читать как ТЗ; выше риск.
**Данное ТЗ использует подход A (config, единый файл) как основной.**
