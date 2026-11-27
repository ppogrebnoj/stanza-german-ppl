# Установка и управление (Windows x64)

Текущий контракт. Версия MCP-сервера и релиза берётся из
`MCP-stanza-german/version.json` (сейчас `4.0.5`).

Этот файл, `requirements.txt` и `requirements.lock` лежат в `installer/`.
`bootstrap.ps1.sha256` лежит рядом с `bootstrap.ps1` в корне; в релизе он публикуется
плоским ассетом рядом с установщиком.

## 0. PowerShell: что реально нужно

Требования: Windows x64 и **Windows PowerShell 5.1** — он есть на любой Windows и его
достаточно для чистого прогона. `bootstrap.ps1` намеренно запускается через `powershell`, а не
через `pwsh`: иначе получается замкнутый круг «pwsh ставит pwsh». Шаг `powershell` при отсутствии
7.7 даёт `SKIP`, а не `FAIL`; рекомендованный режим для интерактивной работы и CI — PowerShell
7.7+ (`pwsh`).

Если нужен PowerShell 7.7, ставится из Windows PowerShell 5.1 без администратора и без
перезагрузки:

```powershell
curl.exe -L --retry 3 -o "$env:TEMP\ps77.msixbundle" https://github.com/PowerShell/PowerShell/releases/download/v7.7.0/PowerShell-7.7.0.msixbundle
Add-AppxPackage -Path "$env:TEMP\ps77.msixbundle"
```

Затем закрыть окно и открыть **PowerShell 7** из меню Пуск:

```powershell
pwsh -v          # 7.7.0
```

Если `Add-AppxPackage` отказал (нет App Installer / MSIX отключён) — portable ZIP, тоже без
администратора:

```powershell
$d = "$env:LOCALAPPDATA\Programs\PowerShell\7.7.0"
New-Item -ItemType Directory -Force $d | Out-Null
curl.exe -L --retry 3 -o "$env:TEMP\ps77.zip" https://github.com/PowerShell/PowerShell/releases/download/v7.7.0/PowerShell-7.7.0-win-x64.zip
Expand-Archive "$env:TEMP\ps77.zip" -DestinationPath $d -Force
& "$d\pwsh.exe" -v
```

Проверка окружения перед установкой проекта:

```powershell
powershell -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'   # 5.1.xxxx (достаточно)
pwsh -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'         # 7.7.0, если установлен
```

## 1. Установка одной командой

На чистой машине достаточно `bootstrap.ps1` из последнего релиза. Хеш файла сверяется с
`bootstrap.ps1.sha256`, который лежит **в том же релизе рядом с установщиком**; в README
значение хеша не публикуется.

```powershell
curl.exe -L -o bootstrap.ps1 https://github.com/ppogrebnoj/stanza-german-ppl/releases/latest/download/bootstrap.ps1
curl.exe -L -o bootstrap.ps1.sha256 https://github.com/ppogrebnoj/stanza-german-ppl/releases/latest/download/bootstrap.ps1.sha256
(Get-FileHash .\bootstrap.ps1 -Algorithm SHA256).Hash      # сверить с bootstrap.ps1.sha256 из того же релиза
powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 -Yes -Json -ArtifactDir .tmp
```

`-Yes` разрешает установку компонентов; без него шаги с системными изменениями дают `BLOCK`.
Команда из issue #12 использует `pwsh` — это устаревшая формулировка: на чистой машине
применяйте вариант выше (или явно установите 7.7 по §0).

Бутстрап:

1. проверяет `AMD64` и 64-битный PowerShell (иначе код `4`, загрузки не начинаются);
2. standalone-ветка (нет локального `installer\`) берёт `flags.ps1`/`flags.json` из **своего тега**
   релиза, а не из `master`, с `--retry-all-errors`; неудачная доскачка парсера — код `5/DELIVERY`;
3. скачивает `stanza-german-ppl-source.zip` из `releases/latest/download`, проверяет `SHA256`
   и распаковывает каталог с `installer\install.ps1` (`-Path` с `*`; `-LiteralPath` тут не работает);
4. winget опционален: нет App Installer → шаг даёт `SKIP`, а не `FAIL rc=3`;
5. вызывает `install.ps1`, передавая параметры вызова без изменений (для полного прогона сам
   добавляет `-Yes`, если не задан `-Check`).

Если репозиторий уже есть, можно вызвать `install.ps1` напрямую:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Yes
```

Минимальный набор шагов (без winget, приёмки и doctor) — быстрее и без лишних сетевых
зависимостей:

```powershell
.\install.ps1 -Steps "python,git,deps,models,snippet" -Yes -Force
```

Список шагов `-Steps` — строка через запятую; в PowerShell 7 её надо **закавычить**,
иначе массив приходит одним аргументом и установщик отвечает «неизвестный шаг» (код `4`).
Шаг `git` для ZIP-копии выполняет `git init`/`fetch`/`reset --mixed` в каталоге проекта
и ставит `pre-commit` hook, поэтому запускать установщик можно из любого каталога.

`install.ps1` — публичный интерфейс; `scripts/all.ps1` удалён, используйте `install.ps1`. Неизвестный параметр даёт код `4`.

## 2. Что ставится

| Компонент | Источник | Версия / configuration |
|---|---|---|
| winget (App Installer) | опционально; установщик не требует | нет → `SKIP`, прямых загрузок достаточно |
| Python | официальный `python-3.15.2-amd64.exe` | 3.15.2 x64, per-user: реестр `PythonCore\3.15`, `py launcher`, `PATH`, «Установка и удаление программ» |
| Git | winget `Git.Git` или git-scm.com | последний стабильный |
| Пакеты | PyPI, `installer/requirements.lock` | `--only-binary=:all:`, компилятор не нужен; `pip check` + сверка версий через `importlib.metadata` |
| Модели Stanza | StanfordNLP / Hugging Face | `tokenize,mwt,pos,lemma,depparse` (5 процессоров, 8 каталогов в `de`), ≈315 МБ, **без `de/default.zip`**; каталог `<root>\.stanza\models`, переопределяется `STANZA_RESOURCES_DIR`; `-Models` добавляет `ner`/`sentiment`/`all` |
| MCP-клиент | клиент человека | запись в конфиг (`mcp.json` и аналоги) выполняет человек; установщик его не трогает |

Проверка достаточности колёс одной командой:

```powershell
python -m pip install --dry-run --only-binary=:all: -r installer/requirements.lock
```

`rc 0` = зависимости готовы. Если dry-run указывает на sdist, установщик называет пакет и
возвращает `fix_cmd` (обновить пин до версии с колесом `cp315-win_amd64`; например,
`PyYAML 6.0.4` подходит, `6.0.3` — нет).

## 3. Машинный контракт

### Параметры

Полный реестр — `docs/flags.json`; `-Check capabilities -Json` выдаёт его же.

| Ключ | Назначение |
|---|---|
| `-Yes` | разрешить установку системного софта и связанные шаги |
| `-Check <область>` | только чтение: `inventory`, `doctor`, `models`, `acceptance`, `mcp_probe`, `server_check`, `plan`, `mcp`, `status`, `capabilities` |
| `-Acceptance` | приёмка с F1 |
| `-Json`, `-ProgressJson` | финальный JSON и NDJSON-поток в stdout (в файл поток пишется всегда). Для работы руками лучше без `-Json`: в этом режиме на экране живая строка прогресса |
| `-ArtifactDir`, `-Python`, `-TargetDir`, `-ModelsDir` | каталоги и явный интерпретатор |
| `-Models`, `-OfflineKit`, `-Steps`, `-Resume`, `-Force` | дополнительные процессоры, офлайн-набор, выбор/продолжение шагов |
| `-Repair`, `-Uninstall`, `-Update`, `-CheckUpdates`, `-RaisePython`, `-MakeOfflineKit` | жизненный контур |

Сетевые настройки передаются переменными окружения процесса: `HTTP_PROXY` / `HTTPS_PROXY`
(curl, pip), `HF_ENDPOINT` (зеркало Hugging Face), `PIP_CACHE_DIR`, `HF_HOME`.

### Режимы только чтения

```powershell
.\install.ps1 -Check inventory -Json       # что есть на машине, у каждой позиции — fix
.\install.ps1 -Check doctor -Json          # код 0 на установленной машине
.\install.ps1 -Check models -Json          # ресурсы Stanza по манифесту
.\install.ps1 -Check acceptance -Json      # полная приёмка (~51 с)
.\install.ps1 -Check mcp_probe -Json       # живой MCP-сервер (~12 с тёплый прогон)
.\install.ps1 -Check server_check -Json    # статическая диагностика сервера (AST, правило, модели)
.\install.ps1 -Check plan -Json            # какие шаги будут выполнены
.\install.ps1 -Check mcp -Json             # валидность сниппета и причина «клиент не видит сервер»
.\install.ps1 -Check status -Json          # сводка по install-report.json
.\install.ps1 -Check capabilities -Json    # реестр параметров
```

Эти режимы не пишут install-report/progress и не меняют реестр/переменные окружения.
Медленные проверки могут оставлять `server.log` и `__pycache__` — это их собственные
побочные эффекты, а не запись отчёта установщика.

`-Check doctor` сначала смотрит `.venv`, затем явный `-Python`. Неканонические флаги
дают `code 4` (неизвестный параметр).

### Долгие шаги и прогресс

`deps` (pip install torch/stanza, ~800 МБ) и `models` (315 МБ) идут минутами и молчат.
Прогресс виден двумя способами:

- без `-Json` — обновляющаяся строка в консоли (`[2/4] deps · pip torch · 43% · ETA 6 мин`);
- `-Json -ProgressJson` — NDJSON-события в stdout, по одному на подшаг, со сбросом
  буфера на каждой записи (`AutoFlush`), то есть в реальном времени, а не в конце.

Дополнительно каждые 2 секунды пишется heartbeat в `.tmp\progress.ndjson` с размером
вывода процесса — по нему видно, что шаг жив, даже если внешний инструмент ничего не печатает.
Если шаг действительно завис, в `<шаг>.log` будет только строка `> <exe> <аргументы>`.

### Коды выхода

| Код | Значение | Действие агента |
|---|---|---|
| 0 | Установка завершена и проверена; регистрация MCP остаётся человеку | выполнить `next_action.command`, если заполнен |
| 2 | Нужен компонент, автоматического пути нет | выполнить `blockers[].fix_cmd` |
| 3 | Шаг упал, `retryable: true` | выполнить `next_action.command` |
| 4 | Ошибка скрипта/среды, не-x64, неизвестный параметр | эскалация |
| 5 | DELIVERY: исходник/ассет недоставлен до `installer\install.ps1` | повторить загрузку релиза |

Каждый шаг автономен: падение одного не прерывает независимые шаги.

### Артефакты и отчёт

Всё создаваемое лежит в `-ArtifactDir` (по умолчанию `<проект>\.tmp`) под фиксированными
именами: `install.log`, `progress.ndjson`, `install-report-precheck.json`,
`install-report.json`, `mcp-snippet.json` (копия — в корне проекта). Параллельные
прогоны разделяет mutex.

Честный чистый прогон (без `-Resume` и без ручных действий) должен удовлетворить чек-листу:

- 11 шагов из `docs/flags.json` (`winget,powershell,python,git,workspace,venv,deps,models,snippet,doctor,acceptance`) присутствуют в отчёте, каждый `OK` или `SKIP`, итог `code=0`;
- `stderr` пуст, `progress.ndjson` построчно парсится, `mcp-snippet.json` есть и в артефактах, и в корне;
- `doctor` — 18 OK / 0 WARN / 0 FAIL, `acceptance` — `PASS`, F1 `0.777 / 0.686`;
- `inventory` не даёт ложных required-провалов (`project_venv=OK`);
- хеш `bootstrap.ps1` из релиза совпадает с посчитанным локально; артефакты копируются вместе с хешами.

Доказательство чистого прогона v4.0.5+fixes — issue #14 и PR #15–#24 (артефакты, хеши
и история исправлений там); отдельный отчёт в репозитории не хранится.
Последняя проверка после чистки репозитория — attempt-6 (27.11.2026, `master @ b1e28fe`):
`code=0`, 11/11 OK/SKIP, doctor 18/0/0, F1 `0.777 / 0.686`, `verify-run.py` 17/17
(merge_gate не применялся: нет открытого PR); хеши и детали — комментарий в issue #14.

`-Resume` — только продолжение после сбоя; отчёт с шагами `resume: already done` **не является
доказательством чистого прогона**.

На каждый шаг пишутся три файла: `<шаг>.log` (сводный — команда и весь вывод),
`<шаг>.stdout.log` и `<шаг>.stderr.log` (потоки процесса по отдельности, наполняются
по ходу работы). По размеру этих файлов heartbeat показывает, что шаг жив.

Структура шага: `id, status, seconds, phase, rc, detail, remedy, retryable, next_cmd, bytes`.
Итог: `code, ok, arch, mode, mcp_registration, report_path,
mcp_snippet_path, python_path, stanza_resources, steps[], blockers[], failures[],
next_action, sizes, timings, acceptance`.

## 4. Сеть, офлайн и объёмы

Загрузки идут с ретраями, `-4`, `--http1.1`, `-C -`, фоллбэком `Invoke-WebRequest`,
зеркалами (`HF_ENDPOINT`, `KI_DOWNLOAD_MIRRORS`) и проверкой SHA256. Preflight делает
Range GET по фактическим ассетам. Обрывы TLS (`10054`, reset) переживаются повтором шага:
после `-Resume` готовые шаги дают `SKIP`, итоговый код остаётся `0`.

Офлайн-набор (архив репозитория + колёса + модели + SHA256):

```powershell
.\install.ps1 -MakeOfflineKit -Yes       # собрать в ArtifactDir
.\install.ps1 -OfflineKit <zip> -Yes     # установить из набора
```

Базовые объёмы фиксируются в полях отчёта `sizes`: пакеты ≈170 МБ, модели ≈315 МБ.

## 5. MCP и приёмка

Установщик создаёт `mcp-snippet.json` (UTF-8 без BOM, кириллица в `\uXXXX`, абсолютные
пути) с записью `stanza-german` и `env: { PYTHONUTF8: "1", STANZA_RESOURCES_DIR: <путь> }`.
`RULE_ROOT` сервер определяет сам. Конфиг MCP-клиента установщик не пишет: человек
добавляет запись из сниппета и перезапускает клиент. Если сервер не видит правило, он
пишет в журнал причину и фактический `RULE_ROOT`, а каждый ответ инструмента содержит
поле `rule_status`.

Шимы для запуска сервера и скриптов создаёт шаг `snippet` в корне проекта:
`python.cmd` (cmd.exe) и `use.ps1` (PowerShell); оба подставляют `STANZA_RESOURCES_DIR`
и абсолютный путь к интерпретатору из `.venv`. До установки их нет (они в `.gitignore`).

Проверка сервера без запущенного клиента:

```powershell
.\python.cmd scripts\run_checks.py --check server_check --json
.\python.cmd scripts\run_checks.py --check mcp_probe --json
```

Список инструментов сервера: `parse_german`, `segment_german`, `check_segmentation`,
`rule_self_test`, `rule_info`, `pipeline_info`. `server_check` разбирает и декораторы, и
динамическую регистрацию в `main()`, поэтому видит все шесть.

Приёмка:

```powershell
.\install.ps1 -Acceptance -Json
```

Прогоняются `doctor`, smoke fast/full, валидаторы (`corpus52` 52/52, `heldout_51` 45/51),
`mcp_probe`; в отчёт попадают F1 и вердикт. Эталон F1: `0.777 / 0.686`.

## 6. Повторные прогоны

```powershell
.\install.ps1 -Resume -Steps models -Yes
.\install.ps1 -Repair -Yes
.\install.ps1 -Update -Yes
.\install.ps1 -Uninstall -Force -Yes
```

Шаг `venv` создаёт `.venv`, шаг `deps` ставит пакеты туда (`mode: "venv"`).
`-Force` включает только потенциально разрушительные/сетевые операции: `git fetch` с таймаутом
90 с и `git reset --mixed`, удаление моделей, uninstall. Для ZIP-копии без `.git` он **не нужен**:
`workspace` сам делает `git init`, добавляет `origin` и ставит хук
`rule\git-hooks\pre-commit` (только LF). Повторный `models` при на месте даёт `SKIP`.

Финальный gate по PR можно запускать без `gh`: `scripts\merge_gate.py` при отсутствии `gh`
переключается на публичный REST API (`GH_TOKEN`/`GITHUB_TOKEN` — опционально):

```powershell
.\.venv\Scripts\python.exe scripts\merge_gate.py --pr <номер> --repo ppogrebnoj/stanza-german-ppl --explain
```

Вердикт `MERGE:all_checks_success` / `BLOCK` / `WAIT`; скрипт ничего не мержит.

## 7. Проверки в CI

```powershell
powershell -File scripts\tests\test-contract.ps1
python -m compileall -q scripts rule bench MCP-stanza-german
```

Контрактный тест проверяет: неизвестный параметр → код `4`, `-Check` не пишет файлы,
`-Check capabilities` совпадает с `docs/flags.json`, отчёт имеет обязательные поля, NDJSON построчно парсится, `-Resume` даёт
`SKIP`, нормализация архитектуры работает.

Версию релиза задаёт `installer/install_tools/release.ps1` из первого заголовка
`MCP-stanza-german/version.json`: тег `v<версия>`, ассеты `bootstrap.ps1`,
`bootstrap.ps1.sha256`, `stanza-german-ppl-source.zip(.sha256)`.

## 8. Регулярная проверка обновлений (deps-watch)

Workflow `.github/workflows/deps-watch.yml` раз в неделю (пн 06:00 UTC) или по кнопке
`workflow_dispatch` собирает отчёт по **всем 62 позициям** `installer/requirements.lock`:
`current` ↔ `latest` с PyPI и отдельный блок колёс под Python 3.15 `win_amd64`.
Никаких триггеров `push`/`pull_request`, коммитов и авто-PR: это info-прогон.

Где смотреть:

- постоянный issue **«📦 Обновления зависимостей — только информация»** — таблица между
  маркерами `<!-- deps-report:start -->` / `<!-- deps-report:end -->`; если набор обновлений
  не изменился (hash отчёта тот же), issue и коммент не трогаются;
- `$GITHUB_STEP_SUMMARY` и artifact `deps-update-report` (`deps-update.md`, `deps-update.json`).

PyPI недоступен → строка «нет данных», `::warning::` и `exit 0`; реальная проблема
с колёсами под 3.15 остаётся failure. GitHub может задерживать scheduled-запуски и
отключать их после 60 дней без активности — используйте `workflow_dispatch`.

Обновлять зависимости **вручную**: правится `installer/requirements.txt` и
`installer/requirements.lock`, затем локально проверяются колёса и контракт:

```powershell
python installer/install_tools/pins.py
python installer/install_tools/pins.py --report --out-md .tmp\deps-update.md --out-json .tmp\deps-update.json
python -m unittest discover -s scripts/tests -p 'test_pins*.py'
powershell -NoProfile -File scripts\tests\test-contract.ps1
```

`bench/results/deps.json` — ручной снимок для MCP-сервера, его обновляет разработчик
командой `python installer/install_tools/pins.py --write bench/results/deps.json` вместе
с решением об апдейте. В `pipeline_info().updates` сервер показывает `as_of` и поле
`stale: true`, если снимок старше 14 дней.
