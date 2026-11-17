# -*- coding: utf-8 -*-
"""Сборка документа для просмотра глазами: предложение -> нарезка разными алгоритмами.

  python bench/make_review.py --set heldout --per-register 3 --algos S1,S4,S11
  python bench/make_review.py --set corpus52 --algos S1,S4 --out bench/results/review_52.md

Скоры берутся из кэша (bench/cache/scores_<set>_<algo>.json) — без повторных прогонов.
"""
import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bench.core import bounds_to_blocks, build_parse, dp_try, load_corpus, load_heldout
from bench.run_bench import BASELINES, DEFAULT, enforce
from bench.scorers import DIRECT, SCORERS

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
BEST = os.path.join(HERE, "results", "best_params.json")


def load_scores(set_name, algo, n):
    p = os.path.join(CACHE, f"scores_{set_name}_{algo}.json")
    if not os.path.exists(p):
        return None
    d = json.load(open(p, encoding="utf-8"))
    return d["scores"] if len(d["scores"]) == n else None


def segment(algo, i, p, scores, params, use_constraints=True):
    base = p.forbidden_base()
    f4 = (p.forbidden_after_funcword() if use_constraints else set()) | base
    fpp = (p.pp_inner_positions() if use_constraints else set()) | base
    if algo in DIRECT:
        return enforce(DIRECT[algo][1](p) or [0, p.n], p, params)
    if algo in BASELINES:
        return BASELINES[algo][1](p, params, f4)
    sc = scores[algo][i]
    b, _ = dp_try(sc, p, params, [f4 | fpp, f4, fpp])
    return enforce(b, p, params)


def pick(rows, per_register):
    if per_register <= 0:
        return list(range(len(rows)))
    by = {}
    for i, r in enumerate(rows):
        by.setdefault(r.get("register", "?"), []).append(i)
    out = []
    for reg, idxs in by.items():
        step = max(1, len(idxs) // per_register)
        out += idxs[::step][:per_register]
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="heldout", choices=["heldout", "corpus52"])
    ap.add_argument("--algos", default="S1,S4,S11")
    ap.add_argument("--per-register", type=int, default=3)
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-words", type=int, default=0, help="пропускать предложения длиннее N слов")
    a = ap.parse_args()

    import stanza
    nlp = stanza.Pipeline("de", processors="tokenize,pos,lemma,depparse,constituency",
                          verbose=False, download_method=None)
    rows = load_heldout() if a.set == "heldout" else load_corpus()
    idxs = pick(rows, a.per_register)
    algos = a.algos.split(",")
    base_algo = [x.split(":")[0] for x in algos]
    best = json.load(open(BEST, encoding="utf-8")) if os.path.exists(BEST) else {}

    parsed, scores_all = [], {}
    for algo in base_algo:
        if algo in scores_all:
            continue
        scores_all[algo] = None if algo in DIRECT or algo in BASELINES else load_scores(a.set, algo, len(rows))
        if scores_all[algo] is None and algo not in DIRECT and algo not in BASELINES:
            print(f"  ! нет кэша оценок для {algo} — сначала прогон run_bench.py --set {a.set}")
    for i in idxs:
        r = rows[i]
        s = r.get("sentence") or r.get("text")
        if a.max_words and len(s.split()) > a.max_words:
            continue
        parsed.append((i, r, s, build_parse(s, nlp)))

    names = {}
    for al in algos:
        b0 = al.split(":")[0]
        names[al] = (SCORERS.get(b0) or DIRECT.get(b0) or BASELINES.get(b0))[0]

    out = [f"# Просмотр глазами: {a.set}\n",
           f"Алгоритмы: " + "; ".join(f"**{al}** — {names[al]}" for al in algos) + "\n",
           "Параметры — лучшие на корпусе 52 (с вашими ограничениями Q3/Q4). "
           "Блоки разделены ` / `.\n"]
    if a.set == "corpus52":
        out.append("Внизу каждого примера — **ваша** разметка (эталон).\n")
    out.append("\n---\n")

    for i, r, s, p in parsed:
        out.append(f"\n**[{r['id']}]** {len(s.split())} слов · регистр: {r.get('register','—')}\n")
        out.append(s + "\n\n")
        for al in algos:
            b0, _, mode = al.partition(":")
            params = DEFAULT if mode == "d" else best.get(b0, DEFAULT)
            bounds = segment(b0, i, p, scores_all, params)
            blocks = bounds_to_blocks(p, bounds)
            mark = f"{al}"
            out.append(f"- `{mark}`: " + " / ".join(blocks) + "\n")
        if a.set == "corpus52" and r.get("blocks"):
            out.append("- `человек`: " + " / ".join(r["blocks"]) + "\n")

    path = a.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), "results",
                                 f"review_{a.set}.md")
    open(path, "w", encoding="utf-8", newline="\n").write("".join(out))
    print("записано:", path, "| примеров:", len(parsed))


if __name__ == "__main__":
    main()
