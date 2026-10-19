## Цикл доработки RULE v5 (MCP-stanza-german-RULE) — конвенции и решения
Цель: человек даёт разбивку → LLM корректирует правило по промту. После достаточного числа итераций правило = ТЗ для программирования. Сейчас работаем только над правилом и промтом.

### Файлы цикла (root E:\KI_WORK\MCP-stanza-german-RULE)
- RULE v{N}.md — отдельный файл на версию в корне (базовая: RULE v5.md). Правило только, без промта.
- PROMPT.md — промт для LLM (v5.1), логика v5.0 сохранена 1:1; жёсткий вход, 8 секций + JSON-итог, гейты до выпуска версии.
- PROTOCOL.md — механика цикла, формат входа/выхода, правило приёма ground truth, критерии выхода в ТЗ.
- CORPUS/verified.jsonl — хранимый корпус verified-разбиений человека; по 1 кейсу на строку: {"id","sentence","blocks":[],"accepted":true,"comment"}. accepted=true = ground truth; schema-example (accepted=false) не входит в регресс.
- GAPS/registry.md — реестр GAP (столбцы gap_id | Stanza-признак | пример | статус open→resolved).
- LOG/iterations.md — лог итераций, счётчик N (текущая базовая v5).
- CHANGELOG.md — единый changelog по всем версиям правила.

### Формат входа человека → LLM
```
Предложение: <текст>
Блоки:
1) <блок 1>
2) <блок 2>
...
Комментарий: <опционально>
```

### Правило приёма ground truth (verified): 3 условия
1. Детерминированность — разбивка воспроизводится правилом детерминированным способом.
2. Только Stanza-поля — деpparse/xpos/lemma/is_mwt, без семантики и пауз.
3. Ноль регресса — новая версия воспроизводит все ранее verified-кейсы; конфликты → запись в GAPS/registry.md.

### Критерии выхода в ТЗ (все, одновременно)
- >=20 verified-кейсов в CORPUS/verified.jsonl (accepted=true).
- Реестр GAP пуст / все resolved.
- Последние 3 итерации — только уточнения (без новых seam-классов C5+, без изменения NO-CUT/P1/P2).
- Регресс 100%.

### Состояние (на момент записи)
- Инфраструктура цикла создана и верифицирована: план plan_mv9gz5nh_8f3798a6d3654dbd выполнен; task board todo_mv9hg4gd_7b0584c404634ec7 — все 7 пунктов completed.
- N=0 (base v5); verified-кейсов: 0.
- Workspace ГОТОВ к запуску итерации 6: пользователь даёт предложение в формате выше; LLM отвечает по PROMPT.md (8 секций + JSON), затем rule version bump → RULE v6.md, запись в LOG/iterations.md, CORPUS, GAPS, CHANGELOG.

### Gotcha
- workspace_edit: операция splice требует обязательное строковое поле 'content' — без него батч откатывается (loop bug). Для полных перезаписей файлов использовать MCP server-filesystem (write_file/read_text_file) — надёжнее и проще.

### RULE v7 завершено (2026-10-18, commit 9fe10f1, plan_mve6aesn_2d463ba0caab4f21)
- RULE v7.md — актуальная версия правила (база). §6 P1→последний токен; §4 NO-CUT=aux/aux:pass/cop + root↔aux; §5 C5 (deprel=mark, xpos=KOUS, untested), C3=цепочка целиком. §«Референс-реализация» УДАЛЕНО (reference/rule.py выведен из репозитория, rule.py НЕ В ЭТОМ ДИРЕКТОРИИ).
- PROMPT.md — v5.2: база RULE v7; шаг D = детерминированный прогон по CORPUS/verified.jsonl (без rule.py); min=3, pref=[3,5], cap=7; C1..C5.
- LOG/iterations.md — N=2, v7.0; sync базы v5→v7.
- GAPS/registry.md — G1–G5 registered, status resolved.
- CHANGELOG.md — запись v7.0.

### Sостояние / что дальше (NEXT)
- verified-кейсов в CORPUS/verified.jsonl: 1 (iter1-umfassen-heizung). Критерий выхода в ТЗ: >=20 → ещё 19 кейсов.
- C5 = untested — нужен тестовый кейс с придаточным (weil/dass/чтобы) для верификации и принятия.
- G1–G5 marked resolved — статус зависит от того, что человек примет v7-разбивку; до этого они open.
- reference/rule.py выведен — если понадобится детерминированный регресс-скрипт, добавится отдельной дельтой (не в рамках v7).

### Gotcha
- PROMPT шаг D теперь описывает детерминированный прогон без конкретного файла; при расхождении LLM с правилом — баг правила, человек решает.

### ТЗ на rule.py готово (2026-10-18, plan_mve9apk1_860a727d91624e67, tx_mve9teiq_a08b9155dd914bed)
- **reference/TZ_rule_py.md** — standalone ТЗ на проектирование rule.py (18 разделов: цель; архитектура 2 слога; вход/каш; модель данных; схема конфига v7; пайплайн; детерминизм; версионирование/синк с RULE v{n}.md; выход JSON; тесты; гейты PROTOCOL; layout; non-goals; edge cases; workflow v{n+1}; приоритеты; план B).
- **Архитектура:** rule.py = статичный интерпретатор (не версируется) + config/v{n}.json = данные правила (правится при v{n+1}). При новой версии правим JSON, не rule.py.
- **Состояние:** RULE v7.md — актуальное правило; config/v7.json и rule.py — НЕ созданы (отдельная дельта); TZ_rule_py.md — ТЗ.
- **Step 2** (указатель на TZ_rule_py.md в «Инфраструктура» RULE v7.md) — пропущен по требованию.

### NEXT: реализация rule.py
- Создать `reference/config/v7.json` (схема из §4 ТЗ) + `reference/rule.py` (интерпретатор, §5 пайплайн).
- `self_test()` → 100% regression по CORPUS/verified.jsonl.
- config completeness: все правила RULE v7.md в config.
- Не переписывать rule.py при v8 — править только config/v8.json.
