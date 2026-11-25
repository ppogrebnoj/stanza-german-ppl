# Гейт мержа (`scripts/merge_gate.py`)

Один вызов даёт однозначный вердикт для указанного PR: **можно мержить / блокировать / ждать**
с причиной. Скрипт **не мержит**, не меняет файлы и не пишет комментарии в GitHub.
Решение о мерже остаётся за человеком/агентом; этот скрипт — единственная точка вердикта.

```powershell
python scripts/merge_gate.py --pr 4 --json
python scripts/merge_gate.py --pr 4 --explain
python scripts/merge_gate.py --pr 4 --repo owner/repo --json
```

`--repo` необязателен: по умолчанию берётся `git remote get-url origin`. Данные читаются
одним вызовом `gh api graphql` через уже используемый в проекте `gh` CLI. `urllib` не нужен.

**stdout** — только вердикт (текст или `--json`), **stderr** — логи. Поэтому `--json`
можно безопасно пайпить. При ошибке `gh` вердикт `ERROR:...`, код выхода `3`.

## Что считается проверкой HEAD

В v1 смотрятся **все GHA-контексты HEAD** (`state=OPEN`, `mergeable=MERGEABLE`).
`required_status_checks` из branch protection не подтягиваются — отдельная задача.
`mergeStateStatus` пишется в диагностику и **не является гейтом**: `UNSTABLE` сам по себе
ничего не блокирует.

Для каждого контекста проверяется `checkSuite.commit.oid` (или `commit.oid` для legacy status)
против `headRefOid` PR. Контексты с чужим или отсутствующим SHA отбрасываются и попадают в
`diagnostics.dropped_wrong_head`. Проверки группируются по ключу
`(источник, workflowName, name)`; внутри группы берётся самая новая запись
(сначала `run_id`, затем время). Остальные уходят в `ignored_history`.

Ключевая формулировка для устаревших отмен:

> «устаревший `CANCELLED`, вытесненный более поздним `SUCCESS` той же проверки при том же HEAD SHA»

Такой `CANCELLED` игнорируется. Новый `CANCELLED`, у которого нет более позднего `SUCCESS`,
блокируется с причиной «перезапустите проверку».

## Таблица правил

Первое сработавшее правило определяет вердикт:

| Условие | Вердикт |
|---|---|
| PR не `OPEN` или `merged=true` | `BLOCK:not_open` |
| `isDraft=true` | `BLOCK:draft_pr` |
| `mergeable=CONFLICTING` | `BLOCK:conflict` |
| `mergeable=UNKNOWN` | `WAIT:unknown_mergeability` — «GitHub ещё считает mergeability, повторите через несколько секунд» |
| Нет актуальных проверок (rollup пуст или всё отброшено) | `WAIT:no_checks` |
| Есть `IN_PROGRESS` / `QUEUED` / `PENDING` | `WAIT:pending_checks` |
| GHA `FAILURE` / `ERROR` / `TIMED_OUT` / `ACTION_REQUIRED` / `STARTUP_FAILURE` | `BLOCK:real_failure` |
| GHA `CANCELLED` без более позднего `SUCCESS` | `BLOCK:fresh_cancel_no_success` — актуальная (свежая) отмена, перезапустите проверку |
| GHA `SKIPPED` / `NEUTRAL` | OK, не блокируют |
| Внешняя проверка (`StatusContext` или CheckRun не `github-actions`) не `SUCCESS` | `BLOCK:external_not_success` — консервативно |
| Неизвестный `conclusion` у GHA | `BLOCK:unknown_conclusion` |
| Все актуальные проверки зелёные | `MERGE:all_checks_success` |

`mergeStateStatus=BEHIND`, `reviewDecision != APPROVED` и прочие незелёные `mergeStateStatus`
идут **только в диагностику**. Флаг `--require-approval` — на будущее.

## Коды выхода

**Эта таблица локальна для гейта и не конфликтует с семантикой установщика** (там
`0 OK/SKIP`, `1 FAIL non-retryable`, `2 BLOCK`, `3 FAIL retryable`, `4 BROKEN`, `5 DELIVERY`).

| Код | Вердикт | Смысл |
|---:|---|---|
| 0 | `MERGE` | можно мержить |
| 1 | `BLOCK` | реальный блокер или незелёная актуальная проверка |
| 2 | `WAIT` | данные ещё не стабилизировались, повторите позже |
| 3 | `ERROR` | ошибка `gh`/GraphQL/разбора; причина в `stderr` и в `reason` |

## `--explain` и `diagnostics`

`--json` всегда содержит `diagnostics`. `--explain` добавляет тот же набор в текстовый вывод:

- `mergeStateStatus`, `mergeable`, `reviewDecision`, `isDraft`, `headRefOid`, `baseRefName`
  (snake_case-агрегаты `merge_state_status`, `review_decision`, `is_draft`, `head_ref_oid`
  сохраняются как алиасы);
- `current` — актуальные проверки;
- `ignored_history` — все вытесненные записи: `name`, `conclusion`, `run_id`,
  `ignore_reason`, `ignore_detail`, `superseded_by_*`;
- `blocking` — актуальные блокеры с кодом причины; это подмножество `current`
  с дополнительными полями `reason`/`detail`;
- `pending`, `dropped_wrong_head`, `notes`.

Этот набор есть **во всех вердиктах**, включая `BLOCK:not_open` и `ERROR` (недостающие
значения — пустые строки/списки/`false`).

Пример для PR #4 (замержен, ожидаемо `BLOCK:not_open`):

```text
BLOCK:not_open — PR #4 не открыт (state=MERGED, merged=True)
```

## Известные ограничения

- GitHub не отдаёт в API причину отмены проверки. Критерий — структурный признак
  «superseded CANCELLED», описанный выше; доказать именно `concurrency` по API нельзя.
- Переименование job/workflow между прогонами ломает сопоставление: старый `CANCELLED`
  не будет сочтён вытесненным и останется блокером. Это намеренно консервативно.
- Re-run с тем же `run_id` различается по времени; при неоднозначности побеждает запись
  с большим `run_id`, затем с более поздним временем.
- Загружаются последние 100 контекстов (`contexts(last: 100)`); если старые есть,
  добавляется `notes`, вердикт от этого не меняется.
- Внешние CI всегда консервативны: `SKIPPED`/`NEUTRAL`/`CANCELLED` блокируют.
- Скрипт не проверяет одобрения ревью и не выполняет автоматический мерж.
- Поддерживаемая платформа — Windows; на Linux не тестировался.
