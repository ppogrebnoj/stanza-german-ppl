# Installer v3 — решения и план

Документ фиксирует решения, принятые при разборе проекта `stanza-german-ppl`
(ветка `installer-v3`, база `42aa48b` / `v4.0.4`). Изменения кода применяются
только в рамках этого плана. Остальное переносится в следующую сессию.

## 1. Базовые решения

| Тема | Решение |
|---|---|
| MCP-сервер | Оставить `4.0.4` без отката. |
| Ветка | `master` оставляем, `main` не вводим. |
| Пакеты | Только `<root>\.venv`; глобальный Python не трогаем. |
| Системные компоненты | Устанавливаются только при `-Yes`; при повторном запуске — проверка/`SKIP`. |
| PowerShell 7.7 | Компонент установки; на текущем ПК будет `SKIP`. |
| Bootstrap | Оставляем как единственную документированную точку входа; поддерживается безопасный one-liner с загрузкой в файл и сверкой SHA256. |
| `bootstrap.ps1.sha256` | Лежит рядом с `bootstrap.ps1` в корне. |
| Алиасы | Все legacy-алиасы убраны; `docs/flags.json` — единственный реестр. |
| `scripts/setup.ps1` | Не восстанавливается. |
| `-Force` | Оставляем, но на текущем ПК не применяем. |
| Отчёты | `install-report-precheck.json` после `snippet`; `install-report.json` после проверок. В `-Check` — только stdout, файлы не пишутся. |
| `progress.ndjson` + mutex | Оставляем. Подробные per-step stdout/stderr-логи и `downloads\` убраны из целевого набора. |
| Служебные скрипты | `install_tools/`: `release.ps1`, `offline_kit.ps1`. |

## 2. Архитектура трёх слоёв

```text
bootstrap.ps1                       entry: получить исходники, вызвать оркестратор, вернуть код
bootstrap.ps1.sha256                рядом с entry
installer/
  install.ps1                       orchestrator: только список шагов и вызовы
  lib/
    env.ps1  download.ps1  state.ps1  progress.ps1  inventory.ps1
    steps/
      winget.ps1  powershell.ps1  python.ps1  git.ps1  workspace.ps1
      venv.ps1    deps.ps1        models.ps1  snippet.ps1
      doctor.ps1  acceptance.ps1
    checks/  (Python-проверки: doctor.py, acceptance.py, check_models.py, ...)
  install_tools/
    release.ps1  offline_kit.ps1
```

- Entry не содержит логики установки.
- Оркестратор не содержит `pip`, `curl`, `git`, `stanza.download`; только вызовы `Invoke-Step*`.
- Библиотеки содержат переиспользуемые функции.
- `doctor` и `acceptance` — шаги в цикле, без отдельного послевызова.
- Шаг `workspace` заменяет former `source`: он работает с уже полученным проектом.

## 3. Exit codes

| Код | Статус | Значение |
|---|---|---|
| 0 | `OK` / `SKIP` | Успех или шаг пропущен |
| 1 | `FAIL` | Не-retryable отказ |
| 2 | `BLOCK` | Нужно действие человека / недостающий prerequisite |
| 3 | `FAIL` | Retryable отказ |
| 4 | `BROKEN` | Сломан запуск / неизвестный флаг |
| 5 | `DELIVERY` | Ошибка доставки исходников или ассетов |

Код 6 удалён.

## 4. Контракт `venv`

Корректный venv — одновременно:

1. `<root>\.venv\Scripts\python.exe` существует;
2. Python `3.15.x`;
3. 64-bit;
4. `pyvenv.cfg` есть и `sys.prefix != sys.base_prefix`;
5. `sys.prefix` внутри `<root>\.venv`;
6. `python -m pip --version` → 0.

Отсутствует — создаём. Корректный — `SKIP`. Некорректный — `BLOCK / rc=2`.

`next_cmd` для BLOCK всегда содержит пару:

```powershell
Remove-Item -Recurse -Force .\.venv; .\bootstrap.ps1 -Steps venv,deps
```

Для сломанного pip:

```powershell
.\.venv\Scripts\python.exe -m ensurepip --upgrade; .\bootstrap.ps1 -Steps venv,deps
```

Repair-path: отдельного `-RepairVenv` нет. Перед удалением проверяется busy-процесс;
для destructive-действий busy → `BLOCK`, для `deps/models/doctor` → `WARN`.
`Remove-Item` выполняется в `try/catch`; гонка тоже даёт `rc=2`.

## 5. Контракт `deps`

Корректные пакеты — одновременно:

1. `python -m pip check` → 0;
2. версии из `importlib.metadata` совпадают с `installer\requirements.lock`;
3. import smoke: `stanza`, `torch`, `numpy`, `mcp`, `pyphen`.

| Ситуация | Код | Retryable |
|---|---|---|
| `.venv` отсутствует | 2 / BLOCK | false |
| 셰 network / TLS / timeout | 3 / FAIL | true |
| Доставка сорвана | 5 / DELIVERY | true |
| Конфликт после чистой установки из lock | 1 / FAIL | false |
| Импорт упал без маркера чистой установки | 3 / FAIL | true |

Import smoke: таймаут 300 с (`KI_IMPORT_TIMEOUT_SEC`), stderr не является ошибкой
сам по себе; в отчёт пишется `stderr_tail`.

## 6. Порядок шагов

```text
winget -> powershell -> python -> git -> workspace -> venv -> deps ->
models -> snippet -> [precheck report] -> doctor -> [acceptance] -> [final report]
```

## 7. Отложено в следующую сессию

- ASCII-переименование 13 локальных / ~12 удалённых кириллических путей
  (`rule/`, `data/`, `RULE.md`, `SPEC.md`, `QUESTIONS.md`, `INSTALL.md`,
  `MARKUP_*.md`, `LIST_150.md`) и всех ссылок в коде/доках/MCP-конфигах.
- Приведение окружения этого ПК: `PyYAML 6.0.3 -> 6.0.4`, `platformdirs`,
  каталог моделей `STANZA_RESOURCES_DIR`, конфиг LM Studio.
- Ревизия CI (`smoke.yml`, `contract.yml`, `release.yml`) под новую структуру.
- Полный физический перенос Python-проверок в `installer/lib/checks/`.
- Обновление пользовательской документации после ASCII-переименования.
