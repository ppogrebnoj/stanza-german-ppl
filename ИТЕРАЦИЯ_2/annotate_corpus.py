#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Разбор вашей разметки файла КОРПУС_52_для_разбивки.md -> блоки.

Граница обозначается ` / ` (пробел, слэш, пробел). Косая черта внутри слова
(CDU/CSU) границей не считается. Понимает и старый маркер `|`.

Запуск:
  python ИТЕРАЦИЯ_2/annotate_corpus.py ИТЕРАЦИЯ_2/КОРПУС_52_для_разбивки.md
  python ИТЕРАЦИЯ_2/annotate_corpus.py ИТЕРАЦИЯ_2/КОРПУС_52_для_разбивки.md --check

Выход: ИТЕРАЦИЯ_2/corpus52_annotations.jsonl
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RULE = os.path.join(ROOT, "MCP-stanza-german-RULE")
CORPUS = os.path.join(RULE, "CORPUS", "verified.jsonl")
OUT = os.path.join(HERE, "corpus52_annotations.jsonl")


def norm(s):
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    return s


def load_ref():
    ref = {}
    for line in open(CORPUS, encoding="utf-8"):
        if line.strip():
            d = json.loads(line)
            ref[d["id"]] = d["sentence"]
    return ref


def parse_md(path):
    lines = open(path, encoding="utf-8").read().split("\n")
    out, i = [], 0
    while i < len(lines):
        m = re.match(r"^\*\*\[([^\]]+)\]\*\*", lines[i])
        if not m:
            i += 1
            continue
        cid = m.group(1)
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        sentence = lines[j].strip() if j < len(lines) else ""
        k = j + 1
        while k < len(lines) and not lines[k].strip():
            k += 1
        answer = ""
        if k < len(lines) and lines[k].lstrip().startswith("→"):
            answer = lines[k].lstrip()[1:].strip()
        out.append((cid, sentence, answer))
        i = k + 1 if k < len(lines) else j + 1
    return out


def to_blocks(answer, ref):
    if not answer or answer in ("??", "?", "/", "|"):
        return None, True
    a = re.sub(r"\s+", " ", answer).strip()
    uncertain = bool(re.search(r"[/|]\?", a))
    a = re.sub(r"([/|])\?", r"\1", a)
    if norm(a) == norm(ref):
        return [ref], uncertain
    for pat in (r"\s+/\s+", r"\s+\|\s+"):
        parts = [p.strip() for p in re.split(pat, a) if p.strip()]
        if len(parts) > 1 and norm(" ".join(parts)) == norm(ref):
            return parts, uncertain
    parts = [p.strip() for p in re.split(r"\s*[/|]\s*", a) if p.strip()]
    if len(parts) > 1 and norm(" ".join(parts)) == norm(ref):
        return parts, uncertain
    return None, uncertain


def to_toks(blocks):
    toks, start = [], 1
    for b in blocks:
        n = len(b.split())
        toks.append([start, start + n - 1])
        start += n
    return toks


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_check = "--check" in sys.argv
    if not args:
        print("usage: python ИТЕРАЦИЯ_2/annotate_corpus.py <file.md> [--check]")
        return 2
    path = args[0]
    if not os.path.exists(path):
        print("нет файла:", path)
        return 2

    ref = load_ref()
    rows = parse_md(path)
    ann, problems, empty = [], [], 0
    for cid, sentence, answer in rows:
        if cid not in ref:
            continue  # пример из шапки файла и прочие не-корпусные id
        sentence_ref = ref[cid]
        blocks, uncertain = to_blocks(answer, sentence_ref)
        if blocks is None:
            if answer and answer not in ("??", "?"):
                problems.append((cid, "не удалось разобрать/сверить с предложением", answer[:80]))
            else:
                empty += 1
            continue
        toks = to_toks(blocks)
        total = len(sentence_ref.split())
        if toks[-1][1] != total:
            problems.append((cid, f"слов {toks[-1][1]}, в предложении {total}", ""))
            continue
        ann.append({"id": cid, "sentence": sentence_ref, "blocks": blocks, "toks": toks, "uncertain": uncertain})

    with open(OUT, "w", encoding="utf-8") as f:
        for r in ann:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"строк разметки: {len(rows)}; принято: {len(ann)}; пусто: {empty}; проблем: {len(problems)}")
    for p in problems[:15]:
        print("  !", p[0], p[1], "|", p[2])
    print("записано:", OUT)

    if do_check and ann:
        sys.path.insert(0, os.path.join(RULE, "reference"))
        import rule as R
        from collections import Counter
        cfg = R.load_config(os.path.join(RULE, "reference", "config.json"))
        verdicts, reasons, bad = Counter(), Counter(), []
        for r in ann:
            res = R.check(r["sentence"], r["blocks"], cfg, with_opinion=False)
            verdicts[res["verdict"]] += 1
            for v in res["violations"]:
                reasons[v["type"]] += 1
            if res["verdict"] != "compliant" and len(bad) < 20:
                bad.append((r["id"], res["verdict"], [v["type"] for v in res["violations"]]))
        print("судья:", dict(verdicts))
        print("нарушения:", dict(reasons))
        for b in bad:
            print("  ~", b[0], b[1], b[2])
        print("ВНИМАНИЕ: 'non_compliant' — это диагностика правила, а не ошибка вашей разметки.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
