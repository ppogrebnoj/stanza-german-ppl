# Чистый прогон установщика: доказательство (issue #14)

VM «Clone of Windows 11 x64» (Windows 11 IoT LTSC, build 26100.9168, PowerShell 5.1.26100.9168,
Python 3.15.2 x64), снятая с исходного snapshot. Никаких ручных действий установки: не ставились
Python/Git/pwsh/winget, не делались `git init`, копирование hook, `STANZA_RESOURCES_DIR`,
`-Resume` и ручное доскачивание моделей. bootstrap запускался из Windows PowerShell 5.1:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 -Yes -Json -ArtifactDir .tmp
```

## Результат

- `code=0`, `ok=true`, 11/11 шагов `OK` или `SKIP`, `stderr` пуст;
  `winget`/`powershell` — `SKIP` (опциональные), остальные 9 — `OK`.
- `doctor`: 18 OK / 0 WARN / 0 FAIL.
- `models`: `tokenize,mwt,pos,lemma,depparse` — все 5 на месте, 315 МБ, без `de/default.zip`.
- `acceptance`: `PASS`, F1 `0.777 / 0.686`, валидаторы 52/52 и 45/51.
- `inventory`: `code=0`, `project_venv=OK`, `stanza_cache=OK` (315 МБ), blocking-позиций нет.
- `mcp-snippet.json` создан и в артефактах, и в корне проекта; `STANZA_RESOURCES_DIR`
  выставляется шагом `acceptance` внутри установщика.

## Артефакты

Комплект attempt-5: `D:/common/runs/attempt-5` (гостевой `Z:\common\runs\attempt-5`) и копия
`E:/KI_WORK/KI_WORK_common/runs/attempt-5`.

| файл | SHA256 |
|---|---|
| `install-stdout.txt` | `9fc290511298d787649f7ea65b63e472b3383c7b96242b8934a391e6f24835b4` |
| `install-stderr.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (пуст) |
| `artifacts/install-report.json` | `5c3d72cce3a0483eb0e0f337896ccd31f0b0417a21d7ad7fa3a5193113893716` |
| `artifacts/install-report-precheck.json` | `dd02d2dc6807a1ab49b96ccb88b30cbc3101f97ec28f99782c6af2d624ccfea0` |
| `artifacts/progress.ndjson` | `a5234e658efffe9ee89130ea78534ea7dce80f42a0745f97bc10e330e3cf8e9f` |
| `artifacts/mcp-snippet.json` | `90513be9c69473538ccd45de56c74a709803cb9fe3f08390ae7497becf57385e` |
| `doctor.json` | `89cd9268c420d1a625ae89f5ab75de76c973feb5f67d703fa86ec9b9761fcda8` |
| `models.json` | `d3d2e8775cec8127a543fe8616e4c723c54b90008a9a112af066b8b1bdb461c3` |
| `acceptance.json` | `4013d9ad32ea9ca12d5139f01565dc854b4c936bf7f1eca334be35ccd23c30a9` |
| `inventory.json` | `196b897a2bd74da00edb5a69aa85fecc8c1ef27786616351a449b883219cc061` |

Хеш `bootstrap.ps1` в клоне/VM: `afce87cb67b9de9c2b3dc05571dd3abb4360195520e58f264b98cdee7926cbe9`
(совпадает с перегенерированным `bootstrap.ps1.sha256`).

## Исправления

PR #15 (A), #16–#19 + #20 (B–E), #21 (F), #22 (G), #23 (H), #24 (I).
Подробности — issue #14.
