# Нарезка немецкого текста на блоки для заучивания

Предложение режется на смысловые фразы по 2–6 слов. В руках — **правило** (`RULE.md`),
нарезчик, валидатор и MCP-сервер; все они используют одни и те же числа из
`rule/config.json`.

## Быстрый старт (Windows x64)

Нужны только **Windows x64** и **Windows PowerShell 5.1** (`powershell`, не `pwsh`;
PowerShell 7.7 — опционально). Скачайте установщик и хеш из **одного** релиза,
явно сверьте SHA256 и запустите — без `-Json`, чтобы видеть прогресс:

```powershell
$base = "https://github.com/ppogrebnoj/stanza-german-ppl/releases/latest/download"
curl.exe -s -L --retry 4 --retry-all-errors --retry-delay 2 -o bootstrap.ps1 "$base/bootstrap.ps1"
if ($LASTEXITCODE -ne 0) { throw "bootstrap.ps1 download failed (curl $LASTEXITCODE)" }
curl.exe -s -L --retry 4 --retry-all-errors --retry-delay 2 -o bootstrap.ps1.sha256 "$base/bootstrap.ps1.sha256"
if ($LASTEXITCODE -ne 0) { throw "bootstrap.ps1.sha256 download failed (curl $LASTEXITCODE)" }
$want = ((Get-Content .\bootstrap.ps1.sha256 -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
$got = (Get-FileHash .\bootstrap.ps1 -Algorithm SHA256).Hash.ToLowerInvariant()
if ($got -ne $want) { throw "SHA256 mismatch: $got != $want" }
powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 -Yes
```

В консоли видны шаги `n/11`, имя и объём загрузки, ETA. Каталог проекта задаётся
`-ProjectDir "D:\stanza"` (по умолчанию `%LOCALAPPDATA%\stanza-german-ppl\app`).
Всё остальное — `installer/INSTALL.md`.

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

Числа правила и объяснение исторического замера — `RULE.md` §4.

## Лицензия

MIT, полный текст — `LICENSE` (© 2026 ppogrebnoj). Код, документация и разметка
(`data/`, `bench/sets/`) — на тех же условиях, с сохранением уведомления об авторстве.
Модели Stanza лицензию не переносят: их скачивает Stanford, в репозитории их нет.
