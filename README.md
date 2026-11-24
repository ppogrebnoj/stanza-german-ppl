# Нарезка немецкого текста на блоки для заучивания

Предложение режется на смысловые фразы по 2–6 слов. В руках — **правило** (что считается
хорошей паузой) и **программа** (нарезает сама) + **валидатор** (проверяет вашу разметку).

## Документы

| Файл | Что внутри |
|---|---|
| `ТЗ.md` | что нужно, рамки, как устроено, как проверяем качество |
| `ПРАВИЛО.md` | **как резать**: запреты и их коды, длины, исключения, цифры |
| `ВОПРОСЫ.md` | только открытые вопросы к заказчику |
| `УСТАНОВКА.md` | §1 человеку: Python/Git, доступ, конфиг MCP, приёмка, офлайн, сбои, обновления · §2 агенту: порядок, коды 0/2/3/4, запреты |
| `README.md` | этот файл: карта проекта, команды, блок «Установка» с SHA256 |
| `LICENSE` | условия использования — MIT |

Истории решений отдельным файлом нет: принятое воплощено в `ПРАВИЛО.md` и `config.json`,
а ход обсуждения остаётся в git.

## Папки

```
KI_WORK/
├─ данные/                      ← разметка (её редактируете вы)
│   ├─ РАЗМЕТКА_52.md           … 52 предложения, переразмеченные под новые правила
│   ├─ РАЗМЕТКА_51.md           … первая часть из 150 (энциклопедические + новостные)
│   └─ СПИСОК_150.md            … все 150 предложений с переводом (задание на разметку)
│
├─ правило/                     ← код правила
│   ├─ segment.py               … нарезчик: текст → блоки
│   ├─ normalize.py             … чистка «битого» текста (NBSP, мягкие переносы, лигатуры)
│   ├─ validator.py             … валидатор: блоки + текст → verdict и где ошибка
│   ├─ config.json              … ВСЕ числа правила (раздел segment)
│   ├─ smoke_test.py            … гейт целостности (запускается перед коммитом)
│   └─ git-hooks/pre-commit     … хук, который вызывает smoke_test
│
├─ MCP-stanza-german/           ← MCP-сервер: нарезка, разбор, судья (для чата)
│   └─ mcp.json.example         ← образец конфига: человек кладёт его в свой клиент сам
├─ scripts/                     ← установка и проверка окружения (см. УСТАНОВКА.md)
│   ├─ all.ps1                  ← оркестратор v2: шаги, коды 0/2/3/4/6, отчёт schema_version 2
│   ├─ _env.ps1 / _download.ps1 ← единый поиск Python и загрузки с SHA256/зеркалами
│   ├─ _state.ps1 / progress.ps1← артефакты, mutex, NDJSON-поток в файл и в stdout
│   ├─ check_models.py          … 5 процессоров по манифесту + минимальная загрузка pipeline
│   ├─ server_check.py          … диагностика MCP-сервера и rule_status
│   ├─ acceptance.py            … doctor + smoke + валидаторы + mcp_probe → F1/вердикт
│   ├─ install_status.py        … сводка по install-report.json
│   ├─ offline_kit.ps1          … офлайн-набор: репозиторий + колёса + модели + SHA256
│   ├─ doctor.py                … что готово, что нет (FAIL/OK, --json)
│   ├─ mcp_probe.py             … проверить MCP-сервер по stdio без клиента (код 0/1)
│   └─ setup.ps1                … совместимость: venv + пины + git-хук (поиск Python из _env.ps1)
│
├─ requirements.txt             ← прямые зависимости (пины) и requirements.lock (полное замыкание)
│
└─ bench/                       ← стенд: сравнение алгоритмов
    ├─ sets/*.jsonl             … данные в машинном виде (corpus52 / heldout_51 / heldout_150)
    ├─ results/                 … актуальные цифры (experiments_all.txt, audit.json, предсказания)
   └─ *.py                     … core, scorers, run_bench, experiments, audit, build_sets
```

## Как запустить

```bash
# нарезать одно предложение
python правило/segment.py --text "Ich habe bei der Firma gearbeitet."

# нарезать страницу целиком (битый текст чистится сам: NBSP, мягкие переносы, лигатуры, кавычки)
python правило/segment.py --file страница.txt

# что именно почистилось в тексте
python правило/normalize.py --file страница.txt --show

# нарезать из чата: segment_german("текст")  — MCP-инструмент сервера

# проверить мою разбивку
python правило/validator.py \
   --text "Ich habe bei der Firma gearbeitet." --blocks "Ich habe|bei der Firma gearbeitet."

# проверить целую разметку (52/51)
python правило/validator.py --set bench/sets/heldout_51.jsonl

# пересчитать машинные наборы из markdown-разметки (после правок заказчика)
python bench/build_sets.py

# гейт целостности (быстро / с проверкой живого кода)
python правило/smoke_test.py
python правило/smoke_test.py --full

# MCP-сервер: handshake, инструменты, гейт, судья — без запущенного клиента
python scripts/mcp_probe.py
```

Числа правила живут только в `config.json` → правка правила = правка JSON, без кода.

## Установка (Windows x64, три команды)

Скачайте один файл `bootstrap.ps1`, сверьте хеш с `bootstrap.ps1.sha256` из того же релиза, запустите. Бутстрап поднимает winget
(`Microsoft.WinGet.Client` из PSGallery + `Repair-WinGetPackageManager -AllUsers`), скачивает
исходники из GitHub Release с проверкой SHA256, ставит Python 3.15.2 x64 (per-user, реестр,
py launcher, PATH), Git, пакеты колёсами и модели Stanza, затем проверяет установку.

```powershell
curl.exe -L -o bootstrap.ps1 https://github.com/ppogrebnoj/stanza-german-ppl/releases/latest/download/bootstrap.ps1
(Get-FileHash .\bootstrap.ps1 -Algorithm SHA256).Hash      # сверить с bootstrap.ps1.sha256 из того же релиза
powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1
```

Агент управляет процессом по машинному контракту: `-Json`, `-ProgressJson` (NDJSON),
`install-report.json` (schema_version 2) и коды 0/2/3/4/6. Всё, что создаёт установщик, лежит в
`<проект>\.tmp`: `install.log`, `progress.ndjson`, `downloads\`, `install-report.json`,
`install-report-<UTC>.json`, `mcp-snippet.json` (+ копия в корне проекта).

```powershell
.\install.ps1 -Check inventory -Json       # только чтение: что есть на машине
.\install.ps1 -Check ready -Json           # код 0 на установленной машине
.\install.ps1 -Check mcp -Json             # почему клиент не видит сервер
.\install.ps1 -Acceptance -Json            # doctor + smoke + валидаторы + mcp_probe, F1 0.777 / 0.686
.\install.ps1 -Resume -Steps models -Yes   # продолжить после обрыва сети
```

Полный реестр ключей — `docs/flags.json`; `-Check capabilities -Json` выдаёт его же.
Неизвестный ключ даёт код 4. Модели: ровно пять процессоров
`tokenize,mwt,pos,lemma,depparse` (~315 МБ; `-Models ner,sentiment` докачивает остальные).
Пакеты ставятся только колёсами: `pip install --dry-run --only-binary=:all: -r requirements.lock`.
Запись в конфиг MCP-клиента делает человек: установщик создаёт `mcp-snippet.json` и не трогает
`mcp.json`; код остаётся 0, а готовый фрагмент лежит в `next_action`.

**Коды выхода:** 0 готово (при необходимости `next_action` с MCP-сниппетом) ·
2 нужен человек (`blockers[].fix_cmd`) · 3 шаг упал, `retryable: true` (`next_action.command`) ·
4 ошибка скрипта/среды, не-x64, неизвестный параметр · 6 нужна перезагрузка/перелогин.

Подробности — `УСТАНОВКА.md` (человеку и агенту), `docs/flags.json`, `scripts/install_status.py`.

```
## Как пополнять разметку

1. Открываете `данные/СПИСОК_150.md`, размечаете очередную часть слэшами: `… фраза / фраза …`.
2. Кладёте файл в `данные/РАЗМЕТКА_<N>.md` (как `РАЗМЕТКА_51.md`).
3. Я собираю машинный набор (`bench/build_sets.py`), прогоняю аудит и валидатор,
   показываю, где правило с вами не согласно.

## Состояние (итерация 4, июль 2026)

| | |
|---|---|
| правило | V4, `config.json` v10 |
| F1 на 52 (настройка) | **0.777** |
| F1 на 51 (проверка) | **0.686** |
| валидатор на разметке 52 | **52/52 compliant** |
| валидатор на разметке 51 | 45/51 compliant (6 нарушений — список в `ПРАВИЛО.md` §5) |
| скорость | 0.31 с на предложение, 0.9 с на страницу из 3 предложений |

Подробности и пути вверх — `ПРАВИЛО.md` §4, открытые вопросы — `ВОПРОСЫ.md`.

## Лицензия

MIT, полный текст — `LICENSE` (© 2026 ppogrebnoj). Код, тексты документации и разметка
(`данные/`, `bench/sets/`) под теми же условиями: использовать, изменять и распространять
можно со сохранением уведомления об авторстве. Модели Stanza лицензию не переносят: их качает
Stanza от Stanford (USC-лицензия), в этом репозитории их нет.