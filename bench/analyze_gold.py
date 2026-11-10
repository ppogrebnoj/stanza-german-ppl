# -*- coding: utf-8 -*-
"""Анализ эталонной разметки заказчика: какие ограничения из неё следуют.

  python bench/analyze_gold.py --set bench/sets/corpus52_v3.jsonl
  python bench/analyze_gold.py --set bench/sets/heldout_51.jsonl

Печатает: длины блоков, нарушения кандидатов в запреты (служебное слово в конце блока,
рез внутри PP, рез перед пунктуацией, дефисные слова), слоговую статистику (Q17).
"""
import argparse
import io
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bench.core import build_parse, truth_cuts

TOKEN = re.compile(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\-']*")


def syl(word, dic):
    w = word.strip("-'\u2019")
    if not w:
        return 0
    if "-" in w:
        return sum(syl(p, dic) for p in w.split("-") if p)
    return dic.inserted(w).count("-") + 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True)
    a = ap.parse_args()
    import stanza
    import pyphen

    dic = pyphen.Pyphen(lang="de_DE")
    nlp = stanza.Pipeline("de", processors="tokenize,pos,lemma,depparse,constituency",
                          verbose=False, download_method=None)
    rows = [json.loads(l) for l in open(a.set, encoding="utf-8") if l.strip()]

    lens, cuts = [], 0
    end_func, end_aux, end_pron = Counter(), 0, 0
    bad_pp, bad_punct, bad_hyphen, bad_short = 0, 0, 0, 0
    syl_blocks, q17_bad, q17_total = [], 0, 0
    examples = {"func": [], "pp": [], "punct": []}

    for r in rows:
        blocks = r.get("blocks") or []
        if not blocks:
            continue
        p = build_parse(r["sentence"], nlp)
        if p is None:
            continue
        # длины блоков в лексических словах и слогах
        for b in blocks:
            words = TOKEN.findall(b)
            lc = max(1, len(words))
            lens.append(lc)
            s = sum(syl(w, dic) for w in words)
            syl_blocks.append(s)
            if lc < 2:
                bad_short += 1
            mx = max([syl(w, dic) for w in words] or [0])
            if mx >= 7:
                q17_total += 1
                if lc > 3:
                    q17_bad += 1
        # резы
        tc = truth_cuts(r["sentence"], blocks, p)
        cuts += len(tc)
        funcset = p.forbidden_after_funcword()
        ppset = p.pp_inner_positions()
        for i in tc:
            u = p.upos[i - 1]
            end_func[u] += 1
            if u in ("ADP", "DET", "CCONJ", "SCONJ", "PART"):
                if len(examples["func"]) < 8:
                    examples["func"].append((r["id"], p.tokens[i - 1][0], u))
            if u == "AUX":
                end_aux += 1
            if u == "PRON":
                end_pron += 1
            if i in ppset:
                bad_pp += 1
                if len(examples["pp"]) < 8:
                    examples["pp"].append((r["id"], p.tokens[i - 1][0], blocks))
            if p.upos[i] == "PUNCT":
                bad_punct += 1
            if p.tokens[i - 1][0].endswith("-") or p.tokens[i][0].startswith("-"):
                bad_hyphen += 1

    n = len(lens)
    print(f"\n=== {os.path.basename(a.set)}: предложений {len([r for r in rows if r.get('blocks')])}, "
          f"блоков {n}, резов {cuts} ===")
    print(f"длина блока (слов): среднее {sum(lens)/max(n,1):.2f}, мин {min(lens)}, макс {max(lens)}")
    print(f"  распределение: " + ", ".join(f"{k} слов: {v}" for k, v in sorted(Counter(lens).items())))
    print(f"слоги в блоке: среднее {sum(syl_blocks)/max(n,1):.2f}, медиана {sorted(syl_blocks)[len(syl_blocks)//2]}, макс {max(syl_blocks)}")
    print(f"блоков из 1 слова: {bad_short}")
    print(f"\nрезы: всего {cuts}")
    print(f"  кончается служебным (ADP/DET/CCONJ/SCONJ/PART): "
          f"{sum(v for k, v in end_func.items() if k in ('ADP','DET','CCONJ','SCONJ','PART'))}")
    print(f"  кончается AUX: {end_aux} | кончается PRON: {end_pron}")
    print(f"  внутри PP: {bad_pp} | перед пунктуацией: {bad_punct} | внутри дефисного слова: {bad_hyphen}")
    print(f"\nQ17 (7+ слогов -> max 3 слова): блоков с таким словом {q17_total}, нарушений {q17_bad}")
    print("\nпримеры «кончается служебным»:", *examples["func"], sep="\n  ")
    print("примеры «рез внутри PP»:", *examples["pp"], sep="\n  ")


if __name__ == "__main__":
    main()
