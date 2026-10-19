# ЗАДАНИЕ (P0): написать rule.py + self_test() + check() — машинальный судья цикла

## Контекст / главный риск
Правило уже в **v3**, есть 3 verified-кейса в `CORPUS/verified.jsonl`, но реального исполнителя (`rule.py`) нет. Сейчас каждый новый verified-кейс «проверяется» LLM'й (см. PROMPT шаг D). Риск: если LLM ошибётся в переборе вариантов — ошибка закрепится ground truth → в v8+ уже сложно отделить «баг» от «дельты». Без `rule.py` нельзя гарантировать 100% детерминизм и 100% регресс.

> **Актуальные данные (после упрощения/реноумерации):** правило = единый `RULE.md` (v3), конфиг = единый `reference/config.json` (без номера, `"version":"v3"`, уже создан). Устаревшие ссылки «v7 / config/v7.json» — игнорировать.

## Что сделать
1. **Написать** `reference/rule.py` — статичный детерминированный референс-интерпретатор правила v3, по spec в [`TZ_rule_py.md`](./TZ_rule_py.md).
2. **Патчить** (если нужно) `reference/config.json`, чтобы он был «полным» (все правила RULE.md в config). rule.py не версируется — при новых версиях правится только config.
3. **Запустить** `self_test()` по текущему `CORPUS/verified.jsonl` (3 verified-кейса) → ожидается **3/3 pass** (soft match).
4. **Реализовать + проверить check()**: 3 corpus cases → match=true; 1 «сломанный» кейс (рез внутри NO-CUT, e.g. между det и NOUN) → match=false, diagnosis status=forbidden верно.
5. **Проверь** Determinism check (sha256 identical, §6 TЗ) и Config completeness (§9).
5. **Зафиксуй**: git commit (`reference/rule.py`, `config.json` если патчил); в `LOG/iterations.md` — строку (в секции 1), в GAPS — статус; changelog-история — в секции 2 LOG/iterations.

## Environment (обязательна)
- Python 3.11; Stanza 1.15.0, German depparse — **offline** из кэша MCP: `STANZA_CACHE_DIR=C:/Users/BIGTER/AppData/Local/StanfordNLP/stanza/Cache` (rule.py задаёт при запуске).
- **Stanza API:** класс `from stanza import Pipeline`; `m(text)`; поля в `token.words[-1]` (`id`(int),`deprel`,`head`,`upos`,`xpos`,`lemma`). **Не** `stanza.pipeline()`/`.predict()`.
- Кросс-проверка: вывод rule.py по деппарсу == MCP-инструменту `parse_german` (те же поля).

## Spec (обязательна к чтению до кода)
- **Алгоритм (детально):** [`TZ_rule_py.md`](./TZ_rule_py.md) §2 (C1–C5, NO-CUT, P1/P2, min_merge, rank).
- **Stanza API + окружение:** §3 + §11.
- **Точный формат вывода + check() API (soft match, diagnosis):** §8 TЗ.
- **Критерий pass self_test():** §9 — soft match (recommended[0] ИЛИ admissible; нормализация текста).

- **Ground-truth appendix:** §14 — 3 verified-кейса с эталонным `recommended`. rule.py должен давать ровно их.

## Acceptance / Definition of Done (все, одновременно)
| # | Условие | Как проверить |
|---|---------|---------------|
| 1 | `rule.py` существует и запускается (`python reference/rule.py "…"`, **и** `--check ... --blocks ...`) | run + §8 JSON |
| 2 | `self_test()` = **3/3 pass** по `CORPUS/verified.jsonl` (soft match) | `python reference/rule.py --self-test` |
| 3 | **check()**: 3 corpus cases → match=true; 1 «сломанный» кейс → match=false, diagnosis status=forbidden верно | §8 TЗ check() + §9 TЗ |
| 4 | Determinism check passes (sha256 identical) | §6 TЗ |
| 5 | Config completeness passes | §9 TЗ |
| 6 | Запуск без кэша даёт тот же результат | детерминизм |

## Ограничения / гейты
- **Только Stanza-поля** (depparse): `id,text,lemma,upos,xpos,feats,head,dep,is_mwt`. Никакой семантики, пауз и LLM-opinions в rule.py.
- **Детерминизм:** один input → один output; кэш по hash текста (факт, не «кэш»).
- **Правило = данные:** при v{n+1} патчится `config.json`, rule.py не трогаем.
- Формат вывода — §8 TЗ (единый источник).

## Следующий шаг после P0 — цикл
Новый ground-truth-кейс → LLM по PROMPT (пакетно) → **rule.py --check** → match? diagnosis?
- match=true + self_test 100% → человек подтверждает → commit.
- match=false → LLM готовит минимальную дельту по facts из diagnosis → патч config.json → repeat (max 5 попыток).
Регресс — кодом, без чтения корпуса LLM.
