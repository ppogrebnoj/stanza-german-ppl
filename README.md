# Нарезка немецкого текста на блоки для заучивания

Предложение режется на смысловые фразы по 2–6 слов. В руках — **правило** (что считается
хорошей паузой) и **программа** (нарезает сама) + **валидатор** (проверяет вашу разметку).

## Установка

Windows x64, PowerShell 7.7+ (`pwsh`). Подробности —
[installer/INSTALL.md](installer/INSTALL.md). Единственная точка входа —
`bootstrap.ps1`; `install.ps1` и `scripts/all.ps1` — внутренние forwarder'ы.

### 1. PowerShell 7.7

```powershell
curl.exe -L --retry 3 -o "$env:TEMP\ps77.msixbundle" https://github.com/PowerShell/PowerShell/releases/download/v7.7.0/PowerShell-7.7.0.msixbundle
Add-AppxPackage -Path "$env:TEMP\ps77.msixbundle"
pwsh -v   # 7.7.0
```

Если MSIX недоступен — portable ZIP из того же релиза PowerShell 7.7.

### 2. Установка проекта

Безопасный one-liner: скачать `bootstrap.ps1` и `bootstrap.ps1.sha256` из одного релиза,
сверить SHA256, затем выполнить установщик:

```powershell
$base = "https://github.com/ppogrebnoj/stanza-german-ppl/releases/latest/download"
curl.exe -L -o bootstrap.ps1 "$base/bootstrap.ps1"
curl.exe -L -o bootstrap.ps1.sha256 "$base/bootstrap.ps1.sha256"
# (Get-FileHash .\bootstrap.ps1 -Algorithm SHA256).Hash сверить с .sha256
powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1
```

Проверка после установки:

```powershell
.\install.ps1 -Check ready -Json
.\install.ps1 -Check mcp -Json
```

Минимальный набор для уже склонированного репозитория:

```powershell
.\bootstrap.ps1 -Steps "python,git,workspace,venv,deps,models,snippet" -Yes
```

Пакеты ставятся **только в `.venv`**; глобальный Python не трогается. Системные
компоненты устанавливаются только с `-Yes`; при повторном запуске — `SKIP`.
Коды выхода: `0 OK/SKIP`, `1 FAIL non-retryable`, `2 BLOCK`, `3 FAIL retryable`,
`4 BROKEN`, `5 DELIVERY`. Полный контракт — `docs/flags.json` и `CHANGELOG.md`.

### 3. Архитектура и порядок шагов

```text
bootstrap.ps1            entry: получить исходники, вызвать оркестратор, вернуть код
installer/install.ps1    orchestrator: только список шагов и вызовы Invoke-Step*
installer/lib/*          библиотеки и шаги (env, download, state, progress, steps/*)
```

Порядок: `winget → powershell → python → git → workspace → venv → deps → models →
snippet → [precheck report] → doctor → [acceptance] → [final report]`.
`doctor` и `acceptance` — обычные шаги, без отдельного послевызова.

Список канонических флагов и шагов — `docs/flags.json` (или `-Check capabilities`).
`-Steps` — строка через запятую; в PowerShell 7 её надо закавычить.

## Документы

| Файл | Что внутри |
|---|---|
| `SPEC.md` | что нужно, рамки, как устроено, как проверяем качество |
| `RULE.md` | **как резать**: запреты и их коды, длины, исключения, цифры |
| `QUESTIONS.md` | только открытые вопросы к заказчику |
| `installer/INSTALL.md` | установка, параметры, коды, отчёты, офлайн, MCP, приёмка — подробности текущего контракта |
| `docs/merge-gate.md` | гейт мержа: правила, коды выхода, `superseded CANCELLED`, ограничения |
| `README.md` | этот файл: короткая установка и команды запуска |
| `LICENSE` | условия использования — MIT |

Истории решений отдельным файлом нет: принятое воплощено в `RULE.md` и `config.json`,
а ход обсуждения остаётся в git.

Все отслеживаемые пути в репозитории — ASCII: `rule/`, `data/`, `RULE.md`, `SPEC.md`,
`QUESTIONS.md`, `installer/INSTALL.md`, `MARKUP_51.md`, `MARKUP_52.md`, `LIST_150.md`.
Не-ASCII имена файлов и каталогов больше не используются: при распаковке архивов
они искажались, и установщик не находил `config.json`.

## Как запустить

Используйте `.venv\Scripts\python.exe` вместо системного `python`.
Шимы `python.cmd` (cmd.exe) и `use.ps1` (PowerShell) подставляют
`STANZA_RESOURCES_DIR` и путь к интерпретатору из `.venv`.

```bash
# нарезать одно предложение
python rule/segment.py --text "Ich habe bei der Firma gearbeitet."

# нарезать страницу целиком (битый текст чистится сам: NBSP, мягкие переносы, лигатуры, кавычки)
python rule/segment.py --file страница.txt

# что именно почистилось в тексте
python rule/normalize.py --file страница.txt --show

# нарезать из чата: segment_german("текст")  — MCP-инструмент сервера

# проверить мою разбивку
python rule/validator.py \
   --text "Ich habe bei der Firma gearbeitet." --blocks "Ich habe|bei der Firma gearbeitet."

# проверить целую разметку (52/51)
python rule/validator.py --set bench/sets/heldout_51.jsonl

# пересчитать машинные наборы из markdown-разметки (после правок заказчика)
python bench/build_sets.py

# гейт целостности (быстро / с проверкой живого кода)
python rule/smoke_test.py
python rule/smoke_test.py --full

# MCP-сервер: handshake, инструменты, гейт, судья — без запущенного клиента
python scripts/mcp_probe.py
```

Числа правила живут только в `config.json` → правка правила = правка JSON, без кода.

### Гейт мержа

Вердикт по указанному PR (`MERGE` / `BLOCK` / `WAIT`, мерж не выполняется):

```bash
python scripts/merge_gate.py --pr N --json
```

Подробности — [docs/merge-gate.md](docs/merge-gate.md): таблица правил, локальные коды
выхода `0/1/2/3`, `--explain`, ограничение «причина отмены в API недоступна».

## Как пополнять разметку

1. Открываете `data/LIST_150.md`, размечаете очередную часть слэшами: `… фраза / фраза …`.
2. Кладёте файл в `data/MARKUP_<N>.md` (как `MARKUP_51.md`).
3. Я собираю машинный набор (`bench/build_sets.py`), прогоняю аудит и валидатор,
   показываю, где правило с вами не согласно.

## Состояние

| | |
|---|---|
| правило | V4, `config.json` v10 |
| F1 на 52 (настройка) | **0.777** |
| F1 на 51 (проверка) | **0.686** |
| валидатор на разметке 52 | **52/52 compliant** |
| валидатор на разметке 51 | 45/51 compliant (6 нарушений — список в `RULE.md` §5) |

Подробности и пути вверх — `RULE.md` §4, открытые вопросы — `QUESTIONS.md`.

## Лицензия

MIT, полный текст — `LICENSE` (© 2026 ppogrebnoj). Код, тексты документации и разметка
(`data/`, `bench/sets/`) под теми же условиями: использовать, изменять и распространять
можно со сохранением уведомления об авторстве. Модели Stanza лицензию не переносят: их качает
Stanza от Stanford (USC-лицензия), в этом репозитории их нет.