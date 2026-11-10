# Stanza German — локальный MCP-сервер синтаксического анализа немецкого языка

Документация по библиотеке https://github.com/stanfordnlp/stanza

MCP-сервер (stdio) для **синтаксического анализа немецкого языка** на базе
[Stanford Stanza](https://stanfordnlp.github.io/stanza/index.html) 1.15.0 (CPU).
Работает **полностью офлайн**: модели берутся из локального кэша, сеть не
используется и повторная загрузка ресурсов не требуется.

## Окружение (уже установлено)

| Пакет   | Версия       |
|---------|--------------|
| Python  | 3.11         |
| stanza  | 1.15.0       |
| torch   | 2.14.0+cpu   |
| numpy   | 2.4.6        |
| mcp     | 1.27.2       |

Каталог кэша моделей:
`C:\Users\BIGTER\AppData\Local\StanfordNLP\stanza\Cache\1.15.0\resources`

В кэше на данный момент: только немецкий (`de`, ~809 МБ).

Сервер создаёт пайплайны с `download_method=None` — Stanza не обращается к сети
и читает модели только из этого кэша (это и есть каталог по умолчанию для
Windows).

## Запуск

```bat
python E:\KI_WORK\MCP-stanza-german\server.py
```

## Подключение к MCP-клиенту

Универсальный конфиг (stdio):

```json
{
  "mcpServers": {
    "stanza": {
      "command": "python",
      "args": ["E:\\KI_WORK\\MCP-stanza-german\\server.py"]
    }
  }
}
```

**LM Studio:** Settings → MCP Servers → Add — укажите `command: python` и
`args: E:\KI_WORK\MCP-stanza-german\server.py`.

## Инструменты

| Инструмент                     | Назначение                                                                 |
|--------------------------------|----------------------------------------------------------------------------|
| `parse_german(text)`           | Токены с леммой, UPOS/XPOS, морфологией (`features`) и зависимостями (`head`/`dep`) по предложениям — основной инструмент. Плюс MWT-поля (`is_mwt`, `mwt_id`), параллельный список `tokens` и offsets `start_char`/`end_char` |
| `constituency_german(text)`    | Фразовое дерево Penn Treebank в скобочной записи по предложениям          |
| `calc_pause(texts, chars_per_sec=4)` | Пакетный расчёт пауз в секундах: символы / скорость (симв./сек; по умолчанию 4, настраивается через `STANZA_CHARS_PER_SEC`) — по блокам + total |
| `pipeline_info()`              | Статус: загруженные процессоры, версии, путь к кэшу моделей, `rule_root`, `rule_registered` |
| `check_segmentation(items, with_opinion=false)` | **Судья правила V4.** Проверка соответствия вашей разбивки правилу. `verdict: compliant \| non_compliant \| invalid_input`, `violations` (код + где + как поправить), `warnings` (допустимо, но помечено), `penalties` (мягкие штрафы с весом), `cost`. Пакетный. Судит по **тому же** разбору, что отдаёт `parse_german` |
| `rule_self_test()`             | Регресс: ваша разметка `bench/sets/corpus52_v3.jsonl` должна проходить валидатор целиком (`gate_passed`, `failed_ids`, `error_codes`). ~30 с |
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
отдельного проекта правила — `MCP-stanza-german-RULE` (`reference/validator_v3.py`,
`reference/config.json`). Путь задаётся переменной `RULE_ROOT`
(дефолт `E:\KI_WORK\MCP-stanza-german-RULE`). **Правила нет — сервер работает как раньше:**
инструменты судьи просто не регистрируются, причина — в `pipeline_info().notes`.

`config.json` перечитывается на **каждый** вызов: цикл «дельта → перепроверка» работает без
перезапуска сервера, а в ответе лежит `config_hash` — им доказано, какой версией правила
судили.

```json
{
  "mcpServers": {
    "stanza-german": {
      "command": "python",
      "args": ["E:\\KI_WORK\\MCP-stanza-german\\server.py"],
      "env": { "STANZA_CHARS_PER_SEC": "6", "RULE_ROOT": "E:\\KI_WORK\\MCP-stanza-german-RULE" }
    }
  }
}
```

Пример пакетного вызова:

```json
check_segmentation({"sentence": "Ich weiß es, weil er müde ist.",
                    "blocks": ["Ich weiß es,", "weil er müde ist."]})
```

Канонический ввод — номера слов (надёжнее текста блока, защита от опечаток):
`{"sentence": "...", "toks": [[1,4],[5,9]]}`.

Лимиты (в `config.json`): `max_seam_positions` (перебор §8 = 2^|S|; при превышении —
явная ошибка `too_many_seams`, сервер не виснет) и `max_admissible` (сколько запасных
вариантов показывать). `with_opinion=true` включает ранжирование машины — по умолчанию выключено.

## Скорость для calc_pause (настройка в LM Studio)

По умолчанию паузы считаются со скоростью **4 симв./сек**. Значение по
умолчанию задаётся переменной окружения **`STANZA_CHARS_PER_SEC`** — это поле
ввода на «панели управления MCP»: в LM Studio 0.4.x серверы настраиваются в
`mcp.json` (Program → Install → Edit mcp.json), добавьте `env` в запись
`stanza-german`:

```json
{
  "mcpServers": {
    "stanza-german": {
      "command": "python",
      "args": ["E:\\KI_WORK\\MCP-stanza-german\\server.py"],
      "env": { "STANZA_CHARS_PER_SEC": "6" }
    }
  }
}
```

Конкретный вызов инструмента может переопределить скорость аргументом
`chars_per_sec`. Действующее значение по умолчанию видно в `pipeline_info()`
→ поле `chars_per_sec_default`; некорректное значение (не число, ≤ 0) даёт
сноску в `notes` и откат на 4.

## Файлы проекта

- `server.py` — сам MCP-сервер (FastMCP, stdio): анализ (Stanza) + судья правила (обёртка над `reference/validator_v3.py`)