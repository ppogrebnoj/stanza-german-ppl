#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка целостности отложенной выборки.

Проверяет:
  * ровно 150 предложений, id уникальны, тексты не дублируются;
  * в текстах нет символа '|' (иначе разметка сломается);
  * пересечение с CORPUS/verified.jsonl по 5-граммам не больше 0.35;
  * печатает распределение по регистрам/длинам и покрытие признаков.

Запуск: python heldout/check_set.py
Код возврата: 0 — всё в порядке, 1 — есть проблемы.
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CORPUS = os.path.join(ROOT, "MCP-stanza-german-RULE", "CORPUS", "verified.jsonl")
SET = os.path.join(HERE, "heldout_150.jsonl")

ORDER = ["wiki", "news", "kafka", "instruction", "legal", "easy", "job", "colloquial"]


def grams(s, k=5):
    w = re.findall(r"\w+", s.lower())
    return set(tuple(w[i:i + k]) for i in range(max(0, len(w) - k + 1)))


def bucket(n):
    return "S" if n <= 12 else "M" if n <= 20 else "L" if n <= 35 else "XL"


def main():
    problems = []
    if not os.path.exists(SET):
        print("FAIL: нет файла", SET)
        return 1
    rows = [json.loads(l) for l in open(SET, encoding="utf-8") if l.strip()]

    if len(rows) != 150:
        problems.append(f"предложений {len(rows)}, ожидается 150")
    ids = [r["id"] for r in rows]
    if len(set(ids)) != len(ids):
        problems.append("id не уникальны")
    texts = [r["text"] for r in rows]
    if len(set(texts)) != len(texts):
        dup = [t for t, c in Counter(texts).items() if c > 1][:3]
        problems.append(f"дубликаты текстов: {dup}")
    if any("|" in t for t in texts):
        problems.append("в тексте есть '|' — сломает разметку")
    if any(" / " in t for t in texts):
        problems.append("в тексте есть ' / ' — конфликтует с маркером границы")

    # пересечение с корпусом
    if os.path.exists(CORPUS):
        corpus = [json.loads(l) for l in open(CORPUS, encoding="utf-8") if l.strip()]
        cg = [grams(r["sentence"]) for r in corpus]
        worst = []
        for r in rows:
            g = grams(r["text"])
            if not g:
                continue
            m = max((len(g & c) / len(g | c)) for c in cg)
            worst.append((m, r["id"]))
        worst.sort(reverse=True)
        if worst and worst[0][0] > 0.35:
            problems.append(f"пересечение с корпусом: {worst[0][0]:.2f} у {worst[0][1]}")

    # распределения
    by_reg = Counter(r["register"] for r in rows)
    by_buk = Counter(bucket(len(r["text"].split())) for r in rows)
    tags = Counter()
    for r in rows:
        tags.update(r.get("tags", []))

    print(f"предложений: {len(rows)};  слов: {sum(len(r['text'].split()) for r in rows)}")
    print("регистры:", dict(by_reg))
    print("длины:", dict(by_buk))
    print("признаки:", dict(sorted(tags.items(), key=lambda x: -x[1])))
    print()
    print("| регистр | S | M | L | XL | итого |")
    print("|---|---|---|---|---|---|")
    for reg in ORDER:
        sub = [r for r in rows if r["register"] == reg]
        row = [sum(1 for r in sub if bucket(len(r["text"].split())) == b) for b in ("S", "M", "L", "XL")]
        print(f"| {reg} | " + " | ".join(str(x) for x in row) + f" | {len(sub)} |")

    if problems:
        print("\nПРОБЛЕМЫ:")
        for p in problems:
            print(" -", p)
        return 1
    print("\nOK: набор целостен")
    return 0


if __name__ == "__main__":
    sys.exit(main())
