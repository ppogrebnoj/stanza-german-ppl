# Стенд испытания алгоритмов

Сравнение алгоритмов нарезки на одном каркасе: **одинаковый DP и ограничения**, отличается
только функция оценки границы. Поэтому разницу в цифрах даёт именно алгоритм.

## Запуск

```bash
# 52 предложения, все алгоритмы, сетка параметров, с запретами V4
python bench/run_bench.py --set corpus52 --algo all --grid --constraints

# только один алгоритм, «из коробки»
python bench/run_bench.py --set corpus52 --algo S1

# 150 предложений (слепой режим, пока нет разметки)
python bench/run_bench.py --set heldout --algo S1,S4,S12,S2,S6,B1 --constraints \
       --params-json bench/results/best_params.json

# документ для просмотра глазами
python bench/make_review.py --set heldout --algos S1:d,S1,S4,S11 --per-register 3

# НОВОЕ (итерация 4): сборка наборов прямо из markdown-файлов заказчика
python bench/build_sets.py                    # -> sets/corpus52.jsonl, sets/heldout_51.jsonl
python bench/pcache.py                        # кэш разборов (один раз)
python bench/audit.py                         # что нарушает сама разметка заказчика
python bench/experiments.py --stage all       # все замеры (варианты запретов, cap, однословные блоки, штрафы, сетка)
python правило/validator.py --set bench/sets/heldout_51.jsonl

# новые наборы из ИТЕРАЦИИ_3 (новая разметка заказчика)
python bench/run_bench.py --set file:bench/sets/corpus52.jsonl   --algo all --grid --constraints --syl --pen
python bench/run_bench.py --set file:bench/sets/heldout_51.jsonl --algo S1,S2,S3,S4,S11,B1 --constraints --syl --pen --params-json bench/results/best_params.json

# статистика эталонной разметки (длины, слоги, где резать нельзя)
python bench/analyze_gold.py --set bench/sets/corpus52.jsonl
```

Флаги: `--constraints` (запреты V4), `--syl` (7+ слогов → max 3 слова),
`--pen` (мягкие штрафы: внутри NP / перед AUX / подлежащее+глагол), `--grid` (сетка параметров),
`--params-json` (найденные лучшие параметры).

## Файлы

| Файл | Что |
|---|---|
| `core.py` | разбор Stanza (Parsed), ограничения, DP (`sum` и `mean`), метрики |
| `scorers.py` | 12 оценок границы (S1…S13) |
| `run_bench.py` | прогон, таблицы, `results/summary_*.md/.json`, `results/<set>_<algo>.jsonl` |
| `make_review.py` | документ «предложение × алгоритмы» для просмотра глазами |
| `cache/` | кэш оценок (чтобы сетка параметров не пересчитывала модели) |
| `results/` | все цифры и нарезки |

## Алгоритмы

| ID | Что | Нужно |
|---|---|---|
| B0 | без резов | — |
| B1 | только пунктуация | — |
| B2 | только длина | — |
| S1 | LCA по дереву зависимостей (порт `subtitle2go`, Apache-2.0) | Stanza depparse |
| S2 | расстояние по дереву составляющих (EMNLP-2024) | Stanza constituency |
| S3 | тип составляющей на границе | Stanza constituency |
| S4 | гибрид S1+S2 | оба |
| S6 | TextTiling (эмбеддинги `all-MiniLM-L6-v2`) | sentence-transformers |
| S7 | MLM-пунктуация (mBERT) | transformers |
| S8–S10 | MLM-пунктуация (нем. BERT, 3 набора знаков) | transformers |
| S11 | MLM только запятая (mBERT) | transformers |
| S12–S13 | гибриды «составляющие + MLM» | оба |

## Ограничения (одинаковые для всех)

- `base` — всегда: не резать перед знаком препинания, внутри дефисного слова, после открывающей кавычки.
- `--constraints` — запреты V4: не резать сразу после предлога, блок не кончается
  служебным словом, механика пунктуации. Рез на границе PP-определения НЕ запрещён
  (это мягкий штраф, см. `ПРАВИЛО.md` §2).
- Длина блока: минимум 2, максимум 7 лексических слов (как в правиле).
