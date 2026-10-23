# ПРОТОКОЛ — цикл доработки правила (немецкая сегментация по Stanza)

## Файлы цикла
| Файл | Назначение |
|---|---|
| `RULE.md` | Текущее правило (единый файл, версия в шапке). |
| `reference/config.json` | Машинальная версия правила: условия C1..C5/NO-CUT/P1-P2, параметры min/pref/cap; единый файл без номера. Дельта LLM = патч конфига. |
| `PROMPT.md` | Промт для LLM (вход, шаги, секции вывода). |
| `CORPUS/verified.jsonl` | Хранимый корпус verified-разбиений человека (ground truth). |
| `GAPS/registry.md` | Реестр GAP-типов через Stanza-признаки. |
| `LOG/iterations.md` | Лог итераций + история правил. |
| `reference/rule.py` | Референс-интерпретатор: **судья** `check()` (verdict + подсказки) и справочный `run()` (мнение машины) + `self_test()`. |
| `reference/config.json` | Машинальная версия правила: C1..Cn, NO-CUT, P1-P2, min/pref/cap, **rank.criteria**. |

## Гейт приёма ground truth
Разбивку человека принимаем как **verified** только если: 1) `verdict=compliant` у судьи; 2) детерминированность (P1/P2, min/cap); 3) только Stanza-поля (deprel/xpos/lemma/is_mwt); 4) ноль регресса по всем ранее verified-кейсам (`--self-test` = все compliant); конфликты — явное решение в GAPS. Ранг машины (`human_rank`) гейтом **не является**.

## Итерация
Человек — разбивка → **rule.py --check** → verdict?
- **compliant** + self_test() 3/3 compliant → человек подтверждает → CORPUS verified, GAPS resolved, LOG, git commit + tag v{n+1} → следующее предложение.
- **non_compliant** → LLM готовит минимальную дельту **только по `delta_required=true`** (missing/forbidden) → патч config.json → repeat (max 5 попыток) → report человеку.
- **invalid_input** → дельту НЕ готовить: перечитать блоки у человека.
- git commit + tag — только при успехе; до этого config = черновик.

## Мандат судьи (жёстко)
`rule.py` **проверяет соответствие и объясняет**. Он не решает, как резать. `recommended`/`admissible`/`human_rank` — справочное мнение машины (`machine_opinion`, `rank_criteria`), в `verdict` и в гейты PROTOCOL оно не входит. Ground truth = разбивка человека, а не ранг машины.

## Команды цикла (буквально)
```bat
:: 1) разбор предложения (MCP-инструмент parse_german) — контекст для LLM
:: 2) судья по этому же разбору (SPEC §4):
python reference\rule.py --check "<Предложение>:" --blocks "<блок 1>" "<блок 2>" --parse-file parse.json
:: без --parse-file судья парсит сам (медленнее, parse_source=parse-cache|stanza)
:: 3) регресс:
python reference\rule.py --self-test
:: 4) полнота конфига:
python reference\rule.py --config-completeness
```

### Тот же цикл через MCP-сервер `stanza-german` (для клиента без терминала: LM Studio и т.п.)
| CLI | MCP-инструмент |
|---|---|
| `parse_german` | `parse_german(text)` |
| `--check ... --parse-file` | `check_segmentation({"sentence":..., "blocks":[...]} , with_opinion=false)` — сервер сам подаёт судье свой разбор (`parse_source=mcp-payload`) |
| `--self-test` | `rule_self_test()` → `{total, compliant, strict_rank1, gate_passed, failed_ids}` |
| `--config-completeness` | `rule_info()` → `config_completeness` + `config_hash` + `rank_criteria` |
| `--determinism` | **нет в MCP** — остаётся CLI/CI-гейтом |

Правило подключается через `env RULE_ROOT`; `config.json` перечитывается на каждый вызов,
`config_hash` в ответе. Нет `RULE_ROOT` → инструментов судьи нет, сервер работает как раньше.
Exit-коды: `--check` → 0 если `compliant`, иначе 1. `--self-test` → 0 если все verified compliant.

## Решения по verdict (таблица — исполнять буквально)
| verdict / violation | Что делает LLM | Чего НЕ делает |
|---|---|---|
| `compliant` | Предложение → в CORPUS (после подтверждения человека), следующий кейс | править config |
| `non_compliant` + `delta_required=true` (cut `missing`) | Новый C-класс или расширение C1..Cn по Stanza-признакам слова **справа** от границы (`features` в cut) | трогать NO-CUT/P1/P2 без данных |
| `non_compliant` + `delta_required=true` (cut `forbidden`) | Разъяснение/сужение NO-CUT по `rule`-id из cut | менять min/cap |
| `non_compliant` + `delta_required=false` (`min`,`cap`,`coverage`) | **Дельту не готовить.** Вернуть кейс человеку: разбивка не проходит §7/покрытие | придумывать новый C-класс |
| `invalid_input` (`block_not_found`) | Перечитать блоки у человека | править config, объявлять mismatch |
| `human_rank` > 1 при `compliant` | Ничего: ранг — мнение машины. Обсудить только `rank.criteria` в config, по решению человека | править seams ради ранга |

## Версионирование
Правило — единый RULE.md (версия в шапке); история — git-теги + LOG/iterations. Конфиг — единый config.json (внутренняя версия = версия правила). PROMPT.md обновляется только вместе с правилом.

## Счётчик N
N = номер последней зафиксированной версии правила (таблица в LOG/iterations.md); текущая базовая — v3, N=3.

## Критерии выхода в ТЗ
Выход допустим только когда **все** условия выполнены: 1) >=20 verified-кейсов в CORPUS/verified.jsonl (accepted=true); 2) GAP-реестр: все resolved + все seam-классы C1–Cn = verified («resolved» ≠ «verified»: необходимое, а не достаточное условие); 3) последние 3 итерации — только уточнения: без новых C-классов и без изменения NO-CUT/P1-P2; 4) регресс 100% — `--self-test` = все verified-кейсы `compliant` без конфликтов; 5) `--config-completeness` = `complete:true` (неподдерживаемые условия — закрыты или явно сняты из config).
