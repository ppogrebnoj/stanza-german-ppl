# Stanza German — локальный MCP-сервер: разбор, нарезка на блоки, судья правила

Документация по библиотеке https://github.com/stanfordnlp/stanza

MCP-сервер (stdio) для **синтаксического анализа немецкого языка** на базе
[Stanford Stanza](https://stanfordnlp.github.io/stanza/index.html) 1.15.0 (CPU).
Работает **полностью офлайн**: модели берутся из локального кэша, сеть не
используется и повторная загрузка ресурсов не требуется.

## Окружение (уже установлено)

| Пакет   | Версия       |
|---------|--------------|
| Python  | 3.15         |
| stanza  | 1.15.0       |
| torch   | 2.15.0+cpu   |
| numpy   | 2.5.5        |
| mcp     | 1.27.2       |

Каталог кэша моделей (по умолчанию для Windows):
`%LOCALAPPDATA%\StanfordNLP\stanza\Cache\1.15.0\resources`

Переопределяется переменной `STANZA_RESOURCES_DIR` — ею же пользуется
`scripts/unpack_models.py`, если модели распакованы не в стандартный каталог.

В кэше на данный момент: только немецкий (`de`, ~809 МБ).

Сервер создаёт пайплайны с `download_method=None` — Stanza не обращается к сети
и читает модели только из этого кэша (это и есть каталог по умолчанию для
Windows).

## Запуск

```bat
REM из корня проекта (путь к проекту любой: E:\KI_WORK, C:\KI_WORK, ...)
python MCP-stanza-german\server.py
```

## Подключение к MCP-клиенту

Универсальный конфиг (stdio):

```json
{
  "mcpServers": {
    "stanza": {
      "command": "python",
      "args": ["<КОРЕНЬ ПРОЕКТА>\\MCP-stanza-german\\server.py"]
    }
  }
}
```

Замените `<КОРЕНЬ ПРОЕКТА>` на каталог, куда склонирован проект (в JSON нужен
абсолютный путь — в конфиге клиента относительные не работают).

**LM Studio:** Settings → MCP Servers → Add — укажите `command: python` и
`args: <КОРЕНЬ ПРОЕКТА>\MCP-stanza-german\server.py`.

## Инструменты

| Инструмент                     | Назначение                                                                 |
|--------------------------------|----------------------------------------------------------------------------|
| `segment_german(text, with_check=false)` | **Нарезка на блоки по правилу V4.** `text` — строка или список (абзац/страница делятся на предложения сами). Возвращает `blocks` (текстом, как в исходнике), `lens` (слов в блоке), `blocks_total`; при `with_check=true` — ещё `verdict` и `cost` (цена штрафов) |
| `parse_german(text)`           | Токены с леммой, UPOS/XPOS, морфологией (`features`) и зависимостями (`head`/`dep`) по предложениям. Плюс MWT-поля (`is_mwt`, `mwt_id`), параллельный список `tokens` и offsets `start_char`/`end_char` |
| `pipeline_info()`              | Статус: загруженные процессоры, версии, путь к кэшу моделей, `rule_root`, `rule_registered` |
| `check_segmentation(items, with_opinion=false)` | **Судья правила V4.** Проверка соответствия вашей разбивки правилу. `verdict: compliant \| non_compliant \| invalid_input`, `violations` (код + где + как поправить), `warnings` (допустимо, но помечено), `penalties` (мягкие штрафы с весом), `cost`. Пакетный. Судит по **тому же** разбору, что отдаёт `parse_german` |
| `rule_self_test()`             | Регресс: ваша разметка `bench/sets/corpus52.jsonl` должна проходить валидатор целиком (`gate_passed`, `failed_ids`, `error_codes`). ~30 с |
| `rule_info()`                  | Паспорт правила: версия, `config_hash`, параметры нарезки, запреты, штрафы, измеренные цифры, путь регресс-набора |

Пример запроса LLM: «Разбери синтаксис предложения *Der schneller Braunhund
jagt die kleine Katze im Garten*» → клиент вызывает `parse_german` и получает JSON с
леммами, POS-тегами и зависимостями каждого токена.

## MWT в `parse_german`

**MWT (multi-word tokens)** — поверхностные токены Stanza, расширяющиеся
несколько синтаксических слов (например `im` → `in dem`). Поля:

- **`words[].is_mwt`** — bool: часть ли это MWT. Источником значения
  является только `Token.is_mwt()` в Stanza (не вычисляется из text/lemma).
- **`words[].mwt_id`** — идентификатор поверхностного токена: для MWT —
  диапазон Word-ID `[a, b]`, для одиночного — свой int id. Слова одного MWT
  собираются по единому ключу `mwt_id` (внутри MWT резать нельзя).
- **`tokens[]`** — параллельный список: один объект на каждый поверхностный
  токен (`id`, `text`, `is_mwt`, `word_ids`). Нужен для восстановления
  поверхностного текста/пунктуации и диапазона MWT.

> Для K1-предложения Stanza MWT не даёт (TRUNC-цепь — отдельное правило);
> MWT появляются при других конструкциях (например `im` → `in dem`).

## Судья правила: `RULE_ROOT`

Инструменты судьи (`check_segmentation`, `rule_self_test`, `rule_info`) работают поверх
отдельного проекта правила — `rule` (`validator.py`, `config.json`). Путь задаётся переменной `RULE_ROOT`
(дефолт — папка `rule` рядом с сервером, то есть `<КОРЕНЬ ПРОЕКТА>\rule`:
`server.py` вычисляет его от своего расположения, `E:\...` в коде не зашит). **Правила нет — сервер работает как раньше:**
инструменты судьи просто не регистрируются, причина — в `pipeline_info().notes`.

`config.json` перечитывается на **каждый** вызов: цикл «дельта → перепроверка» работает без
перезапуска сервера, а в ответе лежит `config_hash` — им доказано, какой версией правила
судили.

```json
{
  "mcpServers": {
    "stanza-german": {
      "command": "python",
      "args": ["<КОРЕНЬ ПРОЕКТА>\\MCP-stanza-german\\server.py"],
      "env": { "RULE_ROOT": "<КОРЕНЬ ПРОЕКТА>\\rule", "PYTHONUTF8": "1" }
    }
  }
}
```

Пример нарезки (страница целиком):

```json
segment_german("Meine Dienstleistungen umfassen nicht nur die Arbeit an Heizungsanlagen. ...")
→ {"count": 3, "blocks_total": 14, "sentences": [{"blocks": ["Meine Dienstleistungen umfassen",
   "nicht nur", "die Arbeit", ...], "lens": [3, 2, 2, ...]}, ...]}
```

Пример проверки:

```json
check_segmentation({"sentence": "Ich weiß es, weil er müde ist.",
                    "blocks": ["Ich weiß es,", "weil er müde ist."]})
```

Канонический ввод — номера слов (надёжнее текста блока, защита от опечаток):
`{"sentence": "...", "toks": [[1,4],[5,9]]}`.

Перебора вариантов нет: судья проверяет **только вашу** разбивку, поэтому отвечает
быстро и без ограничений на длину предложения.

## Файлы проекта

- `server.py` — сам MCP-сервер (FastMCP, stdio): анализ (Stanza) + судья правила (обёртка над `rule/validator.py`)