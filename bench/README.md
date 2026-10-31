# Стенд испытания алгоритмов

Сравнение алгоритмов нарезки на одном каркасе: **одинаковый DP и ограничения**, отличается
только функция оценки границы. Поэтому разницу в цифрах даёт именно алгоритм.

## Запуск

```bash
# 52 предложения, все алгоритмы, сетка параметров, с вашими ограничениями Q3/Q4
python bench/run_bench.py --set corpus52 --algo all --grid --constraints

# только один алгоритм, «из коробки»
python bench/run_bench.py --set corpus52 --algo S1

# 150 предложений (слепой режим, пока нет разметки)
python bench/run_bench.py --set heldout --algo S1,S4,S12,S2,S6,S5,B1 --constraints \
       --params-json bench/results/best_params_c.json

# документ для просмотра глазами
python bench/make_review.py --set heldout --algos S5,S1:d,S1,S4,S12 --per-register 3
```

## Файлы

| Файл | Что |
|---|---|
| `core.py` | разбор Stanza (Parsed), ограничения, DP (`sum` и `mean`), метрики |
| `scorers.py` | 13 оценок границы (S1…S13) + прямые алгоритмы (S5) |
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
| S5 | наши 14 классов правил (`rule.py`, напрямую) | rule.py |
| S6 | TextTiling (эмбеддинги `all-MiniLM-L6-v2`) | sentence-transformers |
| S7 | MLM-пунктуация (mBERT) | transformers |
| S8–S10 | MLM-пунктуация (нем. BERT, 3 набора знаков) | transformers |
| S11 | MLM только запятая (mBERT) | transformers |
| S12–S13 | гибриды «составляющие + MLM» | оба |

## Ограничения (одинаковые для всех)

- `base` — всегда: не резать перед знаком препинания, внутри дефисного слова, после открывающей кавычки.
- `--constraints` — плюс ваши Q3 (не внутри PP) и Q4 (не после служебного слова).
- Длина блока: минимум 2, максимум 7 лексических слов (как в правиле).
