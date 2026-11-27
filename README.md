# Нарезка немецкого текста на блоки для заучивания

Предложение режется на смысловые фразы по 2–6 слов. В руках — **правило** (`RULE.md`),
нарезчик, валидатор и MCP-сервер; все они используют одни и те же числа из
`rule/config.json`.

## Установка (Windows x64)

На чистой машине достаточно **Windows PowerShell 5.1** — он уже есть в системе.
`bootstrap.ps1` запускается через `powershell`, а не `pwsh`: иначе получается замкнутый круг
«pwsh ставит pwsh». PowerShell 7.7 — опционально, ставится без прав администратора
и перезагрузки; инструкция — `installer/INSTALL.md` §0.

Скачать установщик и хеш из **одного** релиза, сверить SHA256, запустить:

```powershell
$base = "https://github.com/ppogrebnoj/stanza-german-ppl/releases/latest/download"
curl.exe -L -o bootstrap.ps1 "$base/bootstrap.ps1"
curl.exe -L -o bootstrap.ps1.sha256 "$base/bootstrap.ps1.sha256"
# (Get-FileHash .\bootstrap.ps1 -Algorithm SHA256).Hash должен совпасть с .sha256
powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 -Yes -Json -ArtifactDir .tmp
```

Проверка после установки:

```powershell
.\install.ps1 -Check doctor -Json
.\install.ps1 -Check mcp -Json
```

Для уже склонированного репозитория — минимальный набор шагов:

```powershell
.\bootstrap.ps1 -Steps "python,git,workspace,venv,deps,models,snippet" -Yes
```

Пакеты ставятся только в `.venv`; системные компоненты — только с `-Yes`, при повторном
прогоне готовые шаги дают `SKIP`. Коды выхода: `0 OK/SKIP`, `1 FAIL`, `2 BLOCK`,
`3 retryable`, `4 BROKEN`, `5 DELIVERY`. Полный контракт — `docs/flags.json`,
подробности — `installer/INSTALL.md`.

### Архитектура установки

```text
bootstrap.ps1            entry: доставить исходники, передать флаги, вернуть код
installer/install.ps1    оркестратор: только список шагов и вызовы Invoke-Step*
installer/lib/*          библиотеки и шаги (env, download, state, progress, steps/*)
```

Корневой `install.ps1` — публичный forwarder на оркестратор. `scripts/all.ps1` удалён:
используйте `install.ps1`. Порядок шагов и реестр флагов — `docs/flags.json`
(или `-Check capabilities`).

## Документы

| Файл | Что внутри |
|---|---|
| `RULE.md` | как резать: запреты и коды, длины, исключения, замеры |
| `SPEC.md` | что нужно, рамки, как устроено, как проверяем качество |
| `QUESTIONS.md` | только открытые вопросы к заказчику |
| `installer/INSTALL.md` | установка, параметры, коды, отчёты, офлайн, MCP, приёмка |
| `docs/merge-gate.md` | гейт мержа: правила, коды выхода, ограничения |
| `docs/flags.json` | единственный реестр флагов, шагов и кодов выхода |
| `LICENSE` | MIT |

Истории решений отдельным файлом нет: принятое воплощено в `RULE.md` и `rule/config.json`,
ход обсуждения — в git. Все отслеживаемые пути — ASCII; контракт проверяет
`scripts/check_ascii_tree.py`.

## Как запустить

Используйте `.venv\Scripts\python.exe` вместо системного `python`. Шимы `python.cmd` (cmd.exe)
и `use.ps1` (PowerShell) создаёт шаг `snippet` установщика; они не хранятся в репозитории
и подставляют `STANZA_RESOURCES_DIR` и путь к интерпретатору из `.venv`.

```bash
# нарезать одно предложение / страницу (битый текст чистится автоматически)
python rule/segment.py --text "Ich habe bei der Firma gearbeitet."
python rule/segment.py --file страница.txt
python rule/normalize.py --file страница.txt --show

# проверить разбивку: одну или всю разметку 51
python rule/validator.py --text "Ich habe bei der Firma gearbeitet." --blocks "Ich habe|bei der Firma gearbeitet."
python rule/validator.py --set bench/sets/heldout_51.jsonl

# пересобрать машинные наборы после правки разметки
python bench/build_sets.py

# гейты
python rule/smoke_test.py            # быстро, без Stanza
python rule/smoke_test.py --full     # живой прогон
python scripts/run_checks.py --list
python scripts/run_checks.py --check doctor --json
python scripts/run_checks.py --check mcp_probe --json
python scripts/check_ascii_tree.py
```

Числа правила живут только в `rule/config.json`: правка правила = правка JSON, не кода.

### Гейт мержа

Вердикт по PR (`MERGE` / `BLOCK` / `WAIT`), мерж не выполняется:

```bash
python scripts/merge_gate.py --pr N --json
```

Подробности — `docs/merge-gate.md`.

## Как пополнять разметку

1. Открыть `data/LIST_150.md`, разметить очередную часть слэшами: `… фраза / фраза …`.
2. Положить файл в `data/MARKUP_<N>.md` (образец — `data/MARKUP_51.md`).
3. Запустить `bench/build_sets.py`, аудит и валидатор; посмотреть расхождения правила с вами.

## Состояние

| | |
|---|---|
| правило | V4, `rule/config.json` v10 |
| F1 на 52 (настройка) / 51 (проверка) | **0.777 / 0.686** — приёмка, `smoke_test --full` |
| валидатор | 52/52 compliant; 45/51 (6 нарушений — `RULE.md` §5) |

Исторический замер стенда `bench/` (0.684 на 51) и объяснение расхождения — `RULE.md` §4.

## Лицензия

MIT, полный текст — `LICENSE` (© 2026 ppogrebnoj). Код, документация и разметка
(`data/`, `bench/sets/`) — на тех же условиях, с сохранением уведомления об авторстве.
Модели Stanza лицензию не переносят: их скачивает Stanford, в репозитории их нет.
