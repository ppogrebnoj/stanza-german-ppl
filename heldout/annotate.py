#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Разбор вашей разметки: ` / ` в предложении -> блоки и Word-ID диапазоны.

Граница обозначается косой чертой: ` / ` (пробел, слэш, пробел).
Косая черта внутри слова (CDU/CSU, 90/Die) границей не считается.
Совместимость: старый маркер `|` тоже понимается.

Вход:
  * heldout_150.md — рабочий файл (ответ в строке `→`), или
  * простой текст: по строке на предложение, «ID текст / с / границами».

Выход:
  * heldout/annotations.jsonl — {id, sentence, blocks, toks, uncertain}
  * с флагом --check — сводка по текущему судье rule.py (диагностика, не оценка)

Запуск:
  python heldout/annotate.py heldout/heldout_150.md
  python heldout/annotate.py heldout/heldout_150.md --check
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RULE = os.path.join(ROOT, "MCP-stanza-german-RULE")
SET = os.path.join(HERE, "heldout_150.jsonl")
OUT = os.path.join(HERE, "annotations.jsonl")


def norm(s):
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    return s


def load_ids():
    if not os.path.exists(SET):
        return {}
    return {r["id"]: r["text"] for r in (json.loads(l) for l in open(SET, encoding="utf-8") if l.strip())}


def parse_md(path):
    """-> list[(id, sentence, answer_line)] из рабочего MD."""
    lines = open(path, encoding="utf-8").read().split("\n")
    out, i = [], 0
    while i < len(lines):
        m = re.match(r"^\*\*\[([A-Z]\d{2})\]\*\*", lines[i])
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


def parse_plain(path):
    """-> list[(id, '', answer_line)] из простого формата «ID текст»."""
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        m = re.match(r"^([A-Z]\d{2})\s+(.+)$", line)
        if m:
            out.append((m.group(1), "", m.group(2)))
    return out


def to_blocks(answer, ref):
    """Разметка -> (blocks, uncertain) или (None, False).

    Порядок попыток:
      1) строгий маркер ` / ` или ` | ` (пробелы обязательны) — безопасно для CDU/CSU;
      2) любой `/` или `|` — если текст после удаления маркеров совпадает с предложением;
      3) маркеров нет — один блок.
    """
    if not answer or answer in ("??", "?", "/", "|"):
        return None, True
    a = re.sub(r"\s+", " ", answer).strip()
    uncertain = bool(re.search(r"[/|]\?", a))
    a = re.sub(r"([/|])\?", r"\1", a)  # снять знак сомнения рядом с границей

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
        print("usage: python heldout/annotate.py <file.md|file.txt> [--check]")
        return 2
    path = args[0]
    if not os.path.exists(path):
        print("нет файла:", path)
        return 2

    known = load_ids()
    rows = parse_md(path) if path.lower().endswith(".md") else parse_plain(path)

    ann, problems = [], []
    empty = 0
    for cid, sentence, answer in rows:
        ref = known.get(cid, sentence)
        blocks, uncertain = to_blocks(answer, ref)
        if blocks is None:
            if answer and answer not in ("??", "?"):
                problems.append((cid, "не удалось разобрать/сверить с предложением", answer[:90], norm(ref)[:90]))
            else:
                empty += 1
            continue
        toks = to_toks(blocks)
        total = len(ref.split()) if ref else toks[-1][1]
        if toks[-1][1] != total:
            problems.append((cid, f"слов {toks[-1][1]}, в предложении {total}", "", ""))
            continue
        ann.append({"id": cid, "sentence": ref, "blocks": blocks, "toks": toks, "uncertain": uncertain})

    with open(OUT, "w", encoding="utf-8") as f:
        for r in ann:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"строк разметки: {len(rows)}; принято: {len(ann)}; пусто: {empty}; проблем: {len(problems)}")
    for p in problems[:15]:
        print("  !", p[0], p[1], "|", p[2])
    print("записано:", OUT)

    if do_check and ann:
        sys.path.insert(0, os.path.join(RULE, "reference"))
        import rule as R  # noqa: N812
        cfg = R.load_config(os.path.join(RULE, "reference", "config.json"))
        from collections import Counter
        verdicts, reasons = Counter(), Counter()
        bad = []
        for r in ann:
            res = R.check(r["sentence"], r["blocks"], cfg, with_opinion=False)
            verdicts[res["verdict"]] += 1
            for v in res["violations"]:
                reasons[v["type"]] += 1
            if res["verdict"] != "compliant" and len(bad) < 15:
                bad.append((r["id"], res["verdict"], [v["type"] for v in res["violations"]]))
        print("судья:", dict(verdicts))
        print("нарушения:", dict(reasons))
        for b in bad:
            print("  ~", b[0], b[1], b[2])
        print("ВНИМАНИЕ: 'non_compliant' — это диагностика правила, а не ошибка вашей разметки.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
