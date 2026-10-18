# ТЗ на проектирование rule.py — детерминированный референс-интерпретатор правила RULE v{n}.md

## 0. Суть и цель
**rule.py** — детерминированный референс-интерпретатор, формально реализующий правило `RULE v{n}.md`.
- **Вход:** немецкое предложение + версия правила (v{n}) / путь к config.
- **Выход:** разбиение `recommended` / `admissible` / `rejected` по данным Stanza (JSON, §9 RULE).

**Цель:** объективная, воспроизводимая и 100%-детерминированная проверка правила по `CORPUS/verified.jsonl` и верификация нового ground-truth-кейса.

**Ключевой принцип:** *правило = данные (конфиг), интерпретатор = код (статичный).* При новой версии правится только конфиг — не весь rule.py.

## 1. Архитектура: два слоя
### 1.1 Слой 1 — статичный интерпретатор (`rule.py`)
Не зависит от конкретной версии. Реализует пайплайн и алгоритмы; всё «что» берёт из конфига.
- `parse` — Stanza depparse + constituency (или кэш).
- `build_units` — атомарные unit по §3 RULE (MWT неделим).
- `seams` — seam-множество: **каждый C-класс = отдельная чистая функция** `c1..cN(tokens, config)` → набор позиций реза.
- `nocut` — рёбра NO-CUT по §4 RULE (из конфига).
- `punct_glue` — P1/P2 по §6 RULE (из конфига).
- `min_merge` — слияние по min по §7 RULE.
- `cap_check` — проверка cap.
- `rank` — ранжирование по §8 RULE (**критерии статичны**, не в конфиге).
- `render` — нормализация/вывод.

### 1.2 Слой 2 — конфиг правила (`config/v{n}.json`)
Содержит «что» конкретной версии — **единственный изменяемый элемент при новой версии**.
- list C-seam classes (C1..Cn) с условиями (Stanza-поля).
- list NO-CUT edges (условия deprel).
- P1/P2 config (terminal set, last-token rule).
- `min` / `pref` / `cap`.
- `seam_classes_status` (verified / untested).
- `version` / `rule_version` / `rule_file`.

**При v{n+1}: правим JSON — не трогаем rule.py.**

## 2. Вход / парсинг + кэш
- **Ввод:** текст предложения + версия правила.
- **Парсинг:** Stanza depparse + constituency (Stanza 1.15.0).
- **Кэш** — по hash текста: `{text_hash → parse_result}`.
  - При повторных запусках читаем из кэша.
  - **Детерминированность:** один текст → один parse → один результат.
  - Кэш — не «кэш», а **факт**: если Stanza вернул X, это X; не пересчитываем.
- **Формат кэша:** JSONL (`text_hash → parse_json`).

## 3. Модель данных
- `Token`: `{id, text, lemma, upos, xpos, feats, head, deprel, is_mwt}`.
- `Block`: `{n, text, lex_words, toks:[ids], seams:[class], status}`.
- `Variant`: `{blocks, rank, admissible, violations:[]}`.
- `lex_count(блока)` = токенов с `upos ≠ PUNCT`; MWT = 1.

## 4. Схема конфига (`config/v{n}.json`)
```json
{
  "version": "v7",
  "rule_version": "v7.0",
  "rule_file": "RULE v7.md",
  "min": 3,
  "pref": [3, 5],
  "cap": 7,
  "terminal_set": [".", "?", "!"],
  "seams": [
    {"class_id": "C1", "status": "verified"},
    {"class_id": "C2", "status": "verified"},
    {"class_id": "C3", "status": "verified"},
    {"class_id": "C4", "status": "verified"},
    {"class_id": "C5", "status": "untested"}
  ],
  "nocut": [
    {"deprel": ["det","det:poss","amod","nummod","compound","flat","appos"], "to": "NOUN"},
    {"deprel": ["case"], "with": ["pobj","obl"]},
    {"deprel": ["cc","conj"], "xpos": "TRUNC"},
    {"mwt": true},
    {"deprel": ["aux","aux:pass","cop"]},
    {"root_verb": ["VAFIN","VVFIN","VVPP"], "with_aux": true},
    {"pair": ["ADV","PART"], "lemma_corr": true}
  ],
  "punct": {
    "P1": "last_token",
    "P2": "prev_block"
  }
}
```
**V7:** C5 добавлен; NO-CUT = `aux/aux:pass/cop` + root↔aux; P1 = last_token.

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
- Нет случайности, нет LLM-опinions.
- **Детерминированность:** один текст + версия Stanza + один config → один результат.
- Кэш: есть → читаем; нет → парсим (Stanza 1.15.0).

## 7. Версионирование / синк с RULE v{n}.md
- **rule.py** — статичный, **не версируется**.
- **config/v{n}.json** — одна версия на RULE v{n}.md.
- **Синхронизация:** при v{n+1} правим `config/v{n+1}.json`; rule.py не трогаем.
- **Верификация синхронности:** config «полный» — все правила RULE v{n}.md в config; если нет → тест fail.

## 8. Выход JSON (совпадает с §9 RULE)
```json
{
  "language": "de",
  "rule_version": "vN",
  "recommended": [{"n":1,"text":"","lex_words":3,"toks":[1,2,3],"seams":["C1"]}],
  "admissible": [...],
  "rejected": [{"variant":"","violations":["NO-CUT: det(4)->NOUN(5)"]}],
  "seam_classes_status": {"C1":"verified","C2":"verified","C3":"verified","C4":"verified","C5":"untested"}
}
```

## 9. Тесты / верификация
- **`self_test()`** — правило воспроизводит все verified-кейсы `CORPUS/verified.jsonl` (accepted=true).
- **Determinism check** — один input → один output (hash).
- **Config completeness** — все правила RULE v{n}.md в config; если нет → fail.
- **New case verification** — новый ground-truth-кейс: rule.py воспроизводит или gap.
- **Regression 100%** — все verified-кейсы без конфликтов.

## 10. Acceptance-гейты (PROTOCOL.md)
| # | Критерий |
|---|----------|
| 1 | ≥20 verified-кейсов в `CORPUS/verified.jsonl` |
| 2 | Реестр GAP пуст / all resolved (`GAPS/registry.md`) |
| 3 | Последние 3 итерации — только уточнения (без новых C-class, без изменения NO-CUT/P1/P2) |
| 4 | Регресс 100% — все verified-кейсы воспроизводятся без конфликтов |

## 11. Layout
```
reference/
├── rule.py          # статичный интерпретатор (создаётся в отдельной дельте)
├── config/
│   └── v7.json      # конфиг v7 (создаётся в отдельной дельте)
├── cache/           # parse-кэш
└── TZ_rule_py.md    # это ТЗ
```

## 12. Non-goals
- Не делаем LLM-опinions в rule.py.
- Не делаем «семантику» — только Stanza-поля.
- Не делаем «паузы».
- Не делаем «внешние знания».
- Не переписываем rule.py при новой версии (правим только config).

## 13. Edge cases
- **MWT** (`is_mwt=true`, children>1) — atomic, неделим.
- **Punctuation:** P1 = last token; P2 = non-terminal → prev block.
- **Cap:** блок 6–7 слов допустим только если все seams legal и нет NO-CUT внутри.
- **Min:** блок <3 → merge.
- **Empty blocks** — не допускаются.

## 14. Workflow v{n+1}
1. Человек даёт ground-truth-кейс (по PROMPT.md).
2. LLM: parse, seam-разбор, delta, RULE v{n+1}, регресс.
3. **rule.py:** правим `config/v{n+1}.json` (добавляем C-class / меняем NO-CUT).
4. rule.py: `self_test()` → 100% regression.
5. CORPUS: новый verified-кейс.
6. LOG, GAPS, CHANGELOG.

## 15. Текущее состояние
- **RULE v7.md** — актуальное правило.
- **config/v7.json** — не создан (отдельная дельта).
- **rule.py** — не создан (отдельная дельта).
- **TZ_rule_py.md** — это ТЗ.

## 16. Приоритеты / этапы
- **P0:** статичный интерпретатор + config-схема + детерминизм.
- **P1:** `self_test()` + regression check + config completeness.
- **P2:** cache + new case verification.
- **P3:** CI-интеграция (если понадобится).

## 17. План B (отказ от конфига)
Если не использовать config:
- rule.py с встроенными правилами (функции C1..Cn внутри кода).
- При v{n+1} правим rule.py (не только config).
- Минус: сложнее читать как ТЗ; выше риск.

**Данное ТЗ использует подход A (config) как основной.**
