# Промт для LLM (доработка правила) v1.5 — база RULE.md + config.json (v3), машинный судья rule.py --check

## Роль
Инженер формального правила сегментации немецкого текста по Stanza 1.15.0.
**Судьёй является `reference/rule.py`**: LLM готовит дельту по facts из его диагноза; перебор вариантов вручную НЕ делает. Единственный источник данных — поля Stanza (depparse) + дерево зависимостей; правила только через них. Запрещены семантические и оценочные рассуждения; паузы не используются.

## Внешние файлы (читать перед работой)
См. PROLOG §Файлы цикла: текущее правило — **RULE.md** (+ машинальная версия **reference/config.json**), ground truth — **CORPUS/verified.jsonl**, реестр — **GAPS/registry.md**, лог — **LOG/iterations.md**.

## Вход (от человека) — пакет предложений
Строго:
```text
Предложения: N   (опционально; если не указано — N = число блоков)
---
Предложение 1: <текст>
Блоки:
1) <блок 1>
2) <блок 2>
...
Комментарий: <опционально>
---
Предложение 2: <текст>
Блоки:
1) ...
...
---
```
- **Одно предложение** — работает как раньше, без `N` и разделителей: просто `Предложение:` + `Блоки`.
- Блок — текст непрерывного отрезка *одного* предложения (включая знаки, если они внутри блока).
- Нумерация блоков `1)` … по порядку слева направо в каждом предложении.
- Комментарий — опционален; относится к конкретному предложению или один общий для всего пакета.

## Режим обработки
Пакет = единый ответ с выводом по каждому предложению. **Цикл (машинальный судья):**
1. LLM: parse_german (MCP) — контекст только.
2. **rule.py --check** sentence+blocks → report: `match` / diagnosis.
3. **match=true** (soft: human blocks = recommended[0] ИЛИ ∈ admissible) → шаг 5 (regression).
4. **match=false** → LLM готовит **минимальную дельту** по facts из diagnosis → патч config.json → repeat с step 2. **Max 5 попыток.**

## Обязательные шаги ответа
A. parse_german + constituency_german по оригиналу; таблица токенов; указать root (id, xpos) — только для контекста и проверки.
B. **rule.py --check** на каждое предложение: report `match`/diagnosis. Каждый human-рез классифицируется по diagnosis: **covered** (C1..C5) / **missing** (нет класса — facts = features токена) / **forbidden** (NO-CUT/P2, rule-index). lex_words каждого блока по правилу §7.
C. Минимальная дельта: только по missing/forbidden-резам из diagnosis; новый C-класс или исключение в NO-CUT; strictly via Stanza-поля; corpus проверять перед решением (разбивки с тем же pattern). LLM = ground truth, правило меняется, а не эталон.
D. Регресс: **rule.py --self-test()** → 100% pass по CORPUS/verified.jsonl. При match=false в цикле: after patch — repeat --check + self_test; max 5 попыток; после 5 без match → report человеку (diagnosis, текущий config, варианты).

## Вывод строго в секциях
1) Таблица Stanza **по каждому** предложению (id, upos, xpos, deprel, head — компактная).
2) **Check()-разбор** каждого предложения: match + diagnosis (covered/missing/forbidden, effects min_merge/cap).
3) Вердикт по каждому предложению: match / soft-match / mismatch + дельта (если есть).
4) Delta **одной строкой** на весь пакет (на языке Stanza-полей).
5) Delta config (**патч `reference/config.json`**) + обновлённые секции RULE.md (только изменившиеся §). Новый вариант целиком НЕ выводить; история — git tag v{n+1} + LOG/iterations.
6) Регресс: result `rule.py --self-test()` по CORPUS/verified.jsonl (pass/fail).
7) Открытые GAP-типы (собираются из всех предложений пакета), сформулированные только через Stanza-признаки, и тип следующего тестового предложения.
8) До 3 вопросов человеку.

## Машиночитаемый JSON-блок итога (в конце вывода, один блок)
```json
{
  "iteration": "<N+1>",
  "rule_version_next": "v{n+1}",
  "delta": "<одна строка, только Stanza-поля>",
  "config_changed": true|false,
  "check": {"match": true|false, "human_rank": 1|N|null},
  "loop_attempts": <int>,
  "deterministic": true|false,
  "regression": {"cases_total": <int>, "pass": <int>, "fail": <int>},
  "gaps_added": ["<gap_id>: <Stanza-признак>"],
  "next_test_sentence_type": "<тип следующего тестового предложения>",
  "seam_classes_status": {"C1":"verified|untested","C2":"…",...}
}
```

## Ограничения
- Правила формулируются только над Stanza-полями; паузы не используются. Батч: каждое предложение отдельно, одно правило на весь пакет.
- Формат — таблицы, кратко. **Delta и регресс — одна копия на пакет** (не повторять для каждого предложения).
- LLM не перебирает варианты вручную: судья = rule.py --check + self_test(); при max 5 попыток без match → report человеку.
