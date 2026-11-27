# -*- coding: utf-8 -*-
"""Аудит разметки заказчика (V4): что на самом деле следует из 103 предложений.

Считает по каждому резу, какой запрет/штраф он нарушает:
  ADP|NP        — рез между предлогом и его существительным («in | seiner Firma»)
  NP|PP-mod     — рез между вершиной NP и её предложным определением («zur Bezeichnung | neben …»)
  Q4            — блок кончается служебным словом (ADP/DET/CCONJ/SCONJ/PART)
  before_punct  — рез перед знаком препинания
  AUX           — рез перед вспомогательным глаголом
  subj|verb     — рез между подлежащим-местоимением и сказуемым
  np_inner      — рез между существительным и его адъективным/генитивным зависимым
  hyphen/quote  — механика

  python bench/audit.py
"""
import io
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bench.core import FUNC_UPOS, NP_INNER, truth_cuts
from bench.pcache import get_parses

HERE = os.path.dirname(os.path.abspath(__file__))
SETS = [("corpus52", os.path.join(HERE, "sets", "corpus52.jsonl")),
        ("heldout51", os.path.join(HERE, "sets", "heldout_51.jsonl"))]


def pp_span(p, strict):
    """множества позиций реза внутри PP: strict (ADP..head) или broad (+ nmod-определения)."""
    children = {}
    for idx, h in enumerate(p.heads_tok):
        if h >= 0:
            children.setdefault(h, []).append(idx)
    bad = set()
    for idx, (dep, up) in enumerate(zip(p.deprel, p.upos)):
        if dep != "case" or up != "ADP":
            continue
        h = p.heads_tok[idx]
        if h < 0:
            continue
        members = {idx, h}
        if not strict:
            stack = [h]
            while stack:
                cur = stack.pop()
                for ch in children.get(cur, []):
                    if p.deprel[ch] in NP_INNER:
                        members.add(ch)
                        stack.append(ch)
        lo, hi = min(members), max(members)
        for pos in range(lo + 1, hi + 1):
            bad.add(pos)
    return bad


def audit(name, path):
    rows, parses = get_parses(path)
    lens, syl_lens = [], []
    cats = Counter()
    per_ex = {k: [] for k in ("ADP|NP", "NP|PP-mod", "FUNC", "before_punct", "AUX", "subj|verb",
                              "np_inner", "hyphen", "one_word_verb")}
    patterns = Counter()
    blocked = Counter()
    ncuts = 0
    one_word_final_verb = 0
    one_word_other = 0
    long_blocks = Counter()
    for (rid, s, p), r in zip(parses, rows):
        blocks = r.get("blocks") or []
        if not blocks:
            continue
        tc = truth_cuts(s, blocks, p)
        pp_strict, pp_broad = pp_span(p, True), pp_span(p, False)
        func = p.forbidden_after_funcword()
        pen = p.penalty_positions()
        ncuts += len(tc)
        for i in tc:
            left, right = p.tokens[i - 1][0], p.tokens[i][0]
            hit = False
            if i in pp_strict:
                cats["ADP|NP"] += 1
                hit = True
                if len(per_ex["ADP|NP"]) < 6:
                    per_ex["ADP|NP"].append(f"{rid}: …{left} | {right}…")
            elif i in pp_broad:
                cats["NP|PP-mod"] += 1
                if len(per_ex["NP|PP-mod"]) < 6:
                    per_ex["NP|PP-mod"].append(f"{rid}: …{left} | {right}…")
            if i in func:
                cats["FUNC"] += 1
                hit = True
                if len(per_ex["FUNC"]) < 6:
                    per_ex["FUNC"].append(f"{rid}: …{left} | {right}…")
            if p.upos[i] == "PUNCT":
                cats["before_punct"] += 1
                hit = True
                if len(per_ex["before_punct"]) < 6:
                    per_ex["before_punct"].append(f"{rid}: …{left} | {right}…")
            if i in pen["before_aux"]:
                cats["AUX"] += 1
                hit = True
                if len(per_ex["AUX"]) < 6:
                    per_ex["AUX"].append(f"{rid}: …{left} | {right}…")
            if i in pen["subj_verb"]:
                cats["subj|verb"] += 1
                hit = True
                if len(per_ex["subj|verb"]) < 6:
                    per_ex["subj|verb"].append(f"{rid}: …{left} | {right}…")
            if i in pen["np_inner"]:
                cats["np_inner"] += 1
                if len(per_ex["np_inner"]) < 6:
                    per_ex["np_inner"].append(f"{rid}: …{left} | {right}…")
            if p.tokens[i - 1][0].endswith("-") or p.tokens[i][0].startswith("-"):
                cats["hyphen"] += 1
                hit = True
            # что за рез (для понимания, а не для запрета)
            patterns[(p.upos[i - 1], p.deprel[i - 1], "→", p.upos[i], p.deprel[i])] += 1
            blocked[(i in pp_broad, i in func, p.upos[i] == "PUNCT")] += 1
        for b in blocks:
            n = len(re.findall(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\-']*", b))
            lens.append(n)
            if n > 6:
                long_blocks[n] += 1
            if n == 1:
                # Q22: блок из одного слова — это финитный глагол в конце?
                st = p.syllables()
                idx = [j for j, t in enumerate(p.tokens) if t[0] in b]
                if idx:
                    j = idx[0]
                    if j == p.n - 1 and p.upos[j] in ("VERB", "AUX"):
                        one_word_final_verb += 1
                        if len(per_ex["one_word_verb"]) < 6:
                            per_ex["one_word_verb"].append(f"{rid}: «{b}» ({p.upos[j]}/{p.deprel[j]})")
                    else:
                        one_word_other += 1
    n = len(lens)
    print(f"\n{'='*104}\n{name}: предложений {len(parses)}, блоков {n}, резов {ncuts}\n{'='*104}")
    print(f"длина блока (слов): среднее {sum(lens)/max(n,1):.2f} | "
          + ", ".join(f"{k}:{v}" for k, v in sorted(Counter(lens).items())))
    print(f"блоков из 1 слова: {one_word_final_verb + one_word_other} "
          f"(финитный глагол в конце — {one_word_final_verb}, прочее — {one_word_other})")
    print(f"блоков длиннее 6 слов: {sum(long_blocks.values())} {dict(long_blocks)}")
    print(f"\nнарушения по классам (на {ncuts} резов):")
    for k in ("ADP|NP", "NP|PP-mod", "FUNC", "before_punct", "AUX", "subj|verb", "np_inner", "hyphen"):
        print(f"  {k:12} {cats[k]:4}  {100.0*cats[k]/max(ncuts,1):5.1f}%")
    for k, v in per_ex.items():
        if v and k != "one_word_verb":
            print(f"\n  {k}:")
            for e in v:
                print(f"     {e}")
    print("\nтоп-15 типов реза (upos/deprel слева → справа):")
    for pat, cnt in patterns.most_common(15):
        print(f"  {cnt:4}  {pat[0]:6}{pat[1]:12} → {pat[3]:6}{pat[4]}")
    return {"name": name, "blocks": n, "cuts": ncuts, "lens": lens, "cats": dict(cats),
            "one_word_final_verb": one_word_final_verb, "one_word_other": one_word_other}


def main():
    out = [audit(n, p) for n, p in SETS]
    out.append(audit("all_103", None) if False else None)
    json.dump([o for o in out if o], open(os.path.join(HERE, "results", "audit.json"), "w",
                                          encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    print("\nсохранено: bench/results/audit.json")


if __name__ == "__main__":
    main()
