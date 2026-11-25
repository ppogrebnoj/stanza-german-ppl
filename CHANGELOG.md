# CHANGELOG

## installer-v3 (unreleased)

### Окружение и перенос проверок (follow-up #3, п. 2 и 4)

- PyYAML `6.0.4` и platformdirs `4.14.5` — по `installer/requirements.lock`; расхождения
  между `pip freeze` и lock нет.
- Каталог моделей зафиксирован: `<root>\.stanza\models`. `STANZA_RESOURCES_DIR`
  выставляется в PI `mcp.json` и в сниппете установщика; дефолты `env.ps1`/`flags.json`/
  `models.ps1`/`snippet.ps1` синхронизированы с `_paths.py` и `check_models.py`.
  `mcp_probe` больше не сбрасывает переменную, а прибивает контрактный путь.
- `server_check.py` перенесён в `installer/lib/checks/` и зарегистрирован как
  `-Check server_check`; AST-разбор видит и декораторы, и динамическую регистрацию
  инструментов в `main()`. Упоминание удалённого `install_status.py` убрано из тестов.
- Следы LM Studio удалены из PI-конфига; managed PI обновлён `1.4.0 → 1.6.1`.
- CI `compileall` и документация приведены к контракту (`ready`, шимы `snippet`, `ModelsDir`).
- Версия MCP-сервера/релиза поднята до `4.0.5` для публикации ассетов с этими правками.

### Python-проверки (follow-up #3, п. 4)

- `doctor.py`, `check_models.py`, `acceptance.py`, `mcp_probe.py` перенесены в
  `installer/lib/checks/`; единая точка запуска — `scripts/run_checks.py`, реестр —
  `installer/lib/checks/manifest.json`.
- `-Check ready` заменён на `-Check doctor`; добавлены `models`, `acceptance`, `mcp_probe`.
  `-Check mcp` (проверка сниппета) не изменён.
- `mcp_probe` убран из `smoke.yml`; остался ручной запуск.

### ASCII-пути (follow-up #3)

- Все отслеживаемые файлы и каталоги переведены в ASCII без правки содержимого:
  код правила — `rule/`, разметка — `data/`, документы — `RULE.md`, `SPEC.md`,
  `QUESTIONS.md`, `installer/INSTALL.md`, `data/MARKUP_51.md`, `data/MARKUP_52.md`,
  `data/LIST_150.md`.
- Ссылки обновлены в коде, конфигах, CI и документации, включая `RULE_ROOT` в
  MCP-конфигах и пути в `smoke.yml`/`contract.yml`.
- Версия, тег, релиз, `bootstrap.ps1`, `bootstrap.ps1.sha256` и `actions/*` в workflows
  не тронуты; в `installer/` изменена только ссылка на документ, не логика шагов.

### Архитектура и порядок шагов

- Три слоя: `bootstrap.ps1` (entry), `installer/install.ps1` (orchestrator),
  `installer/lib/*` + `installer/lib/steps/*` (библиотеки и шаги).
- Entry не содержит логики установки; оркестратор только вызывает `Invoke-Step*`;
  `pip`, `curl`, `git`, `stanza.download` живут в библиотеках/шагах.
- `doctor` и `acceptance` — обычные шаги в цикле, без отдельного послевызова.
- Порядок: `winget → powershell → python → git → workspace → venv → deps → models →
  snippet → [precheck report] → doctor → [acceptance] → [final report]`.
- `docs/flags.json` — единственный реестр; читается только через
  `installer/lib/flags.ps1`. `-Check` ровно шесть режимов: `inventory`, `ready`, `plan`,
  `mcp`, `status`, `capabilities`. `-Json` и `-ProgressJson` взаимоисключающи (4/BROKEN).

### Exit codes

| Код | Статус | Значение |
|---|---|---|
| 0 | OK / SKIP | успех или шаг уже сделан |
| 1 | FAIL | non-retryable, повтор той же команды не поможет |
| 2 | BLOCK | нужно действие человека / недостающий prerequisite |
| 3 | FAIL | retryable, сеть/таймаут/временный сбой |
| 4 | BROKEN | сломан запуск, неизвестный флаг, битая раскладка после появления оркестратора |
| 5 | DELIVERY | исходники/ассеты не доставлены до появления `installer/install.ps1` |

Код 6 удалён. Код 2 переопределён как BLOCK; 5 введён отдельно. Граница 4/5: пока
оркестратор недоступен — 5; после его появления сломанный вызов — 4. Потребители
`release.yml`, `test-contract.ps1`, `docs/*`, `scripts/*` аудированы.

Для шагов `winget`, `powershell`, `python`, `git`, `workspace`, `models`, `snippet`,
`doctor`, `acceptance`: отсутствует prerequisite → 2; сеть/таймаут → 3; несовместимая
версия/битый конфиг → 1; сломан запуск → 4; не доставлены ассеты → 5.

### Контракт `venv`

Корректный venv: `<root>\.venv\Scripts\python.exe` существует; `sys.version_info[:2] == (3, 15)`
и `releaselevel == 'final'`; 64-bit; `pyvenv.cfg` есть; `sys.prefix` внутри `.venv`;
`python -m pip --version` → 0. Отсутствует — создаём; корректный — SKIP; некорректный —
BLOCK/2. `next_cmd` для BLOCK всегда содержит `-Steps venv,deps`:

```powershell
Remove-Item -Recurse -Force .\.venv; .\bootstrap.ps1 -Steps venv,deps
```

Для сломанного pip: `.venv\Scripts\python.exe -m ensurepip --upgrade` перед тем же вызовом.
Busy-check использует `ExecutablePath`; для destructive-действий busy → BLOCK, для
`deps/models/doctor` → WARN; `Remove-Item` в `try/catch` тоже даёт rc=2.

### Контракт `deps`

Корректные пакеты: `python -m pip check` → 0; версии из `importlib.metadata` совпадают с
`installer\requirements.lock`; import smoke `stanza, torch, numpy, mcp, pyphen` проходит.
 `-Resume -Steps deps` всегда выполняет `pip install -r installer\requirements.lock`
и ставит маркер только после rc=0. Конфликт после чистой установки из lock → 1,
`retryable:false`; сеть/таймаут → 3, `retryable:true`; доставка → 5.
Бюджет import smoke: `KI_DEPS_TOTAL_TIMEOUT_SEC=900` (alias `KI_IMPORT_TIMEOUT_SEC`);
при исчерпании detail = `import smoke timeout after Ns`. stderr сам по себе не ошибка,
в отчёт пишется `stderr_tail`.

### Прочее

- Отчёты пишутся атомарно (`*.tmp` → `Move-Item -Force`); `-Check status` fallback на precheck,
  иначе 2/BLOCK `no report yet`.
- Артефакты: `.tmp\install.log`, `.tmp\install-report-precheck.json`,
  `.tmp\install-report.json`, `.tmp\progress.ndjson`, `.tmp\mutex`,
  `mcp-snippet.json` (+ копия в корне).
- `bootstrap.ps1` передаёт `-Steps`, `-Resume`, `-Acceptance`, `-Force` без изменений.
- `-Force`: `workspace`, `models`, `-Uninstall`. `pins.py` перенесён в `install_tools/`.
- `bootstrap.ps1.sha256` хранится рядом с `bootstrap.ps1` в корне.
