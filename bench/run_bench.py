# -*- coding: utf-8 -*-
"""Испытание алгоритмов на корпусе (52) или на heldout (150, слепой режим).

Примеры:
  python bench/run_bench.py --set corpus52 --algo all
  python bench/run_bench.py --set corpus52 --algo S2 --grid
  python bench/run_bench.py --set corpus52 --algo S2,S4 --constraints
  python bench/run_bench.py --set heldout --algo S2 --blind

Выход:
  bench/results/<set>_<algo>.jsonl   — нарезки по предложениям (для просмотра)
  bench/results/summary_<set>.md     — таблица сравнения
  bench/results/summary_<set>.json   — те же цифры машинно
"""
import argparse
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from bench.core import (apply_penalties, block_stats, bounds_to_blocks, build_parse, dp_segment,
                        dp_try, load_corpus, load_heldout, score_metrics, truth_cuts)
from bench.scorers import DIRECT, SCORERS

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
CACHE = os.path.join(HERE, "cache")
DEFAULT = {"min_lex": 2, "ideal": 4.0, "cap": 7, "w_len": 1.0}


# ------------------------------------------------------------------ ограничения блоков

def enforce(bounds, p, params):
    """Привести границы к 2..cap лексических слов: длинные разрезать, короткие слить."""
    min_lex, cap = params["min_lex"], params["cap"]
    bounds = sorted(set(bounds))
    for _ in range(50):
        # 1) разрезать длинные
        out = [bounds[0]]
        for b in bounds[1:]:
            while p.lex_count(out[-1], b) > cap:
                a, cnt, i = out[-1], 0, out[-1]
                while i < b:
                    if p.lex[i]:
                        cnt += 1
                        if cnt == cap:
                            break
                    i += 1
                if i + 1 >= b:
                    break
                out.append(i + 1)
            out.append(b)
        bounds = out
        # 2) слить короткие
        changed = False
        for k in range(len(bounds) - 1):
            if p.lex_count(bounds[k], bounds[k + 1]) < min_lex:
                del bounds[k if k > 0 else k + 1]
                changed = True
                break
        if not changed and len(bounds) > 1 and p.lex_count(bounds[-2], bounds[-1]) < min_lex:
            bounds = bounds[:-2] + [bounds[-1]]
            changed = True
        if not changed:
            break
    return bounds


# ------------------------------------------------------------------ базовые линии

def baseline_b0(p, params, forbidden):
    return [0, p.n]


def baseline_b1(p, params, forbidden):
    cuts = {0}
    for i in range(1, p.n):
        if p.tokens[i - 1][0] in (",", ";", ":", "\u2013", "\u2014"):
            cuts.add(i)
    cuts.add(p.n)
    return enforce(sorted(cuts), p, params)


def baseline_b2(p, params, forbidden):
    ideal = max(2, int(round(params["ideal"])))
    cuts, cnt = {0}, 0
    for i in range(p.n):
        if not p.lex[i]:
            continue
        if cnt == ideal:
            cuts.add(i)
            cnt = 0
        cnt += 1
    cuts.add(p.n)
    return enforce(sorted(cuts), p, params)


BASELINES = {
    "B0": ("без резов (всё предложение)", baseline_b0),
    "B1": ("только пунктуация", baseline_b1),
    "B2": ("только длина (по ideal слов)", baseline_b2),
}


# ------------------------------------------------------------------ кэш оценок

def safe(name):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)


def get_scores(algo, set_name, parses):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"scores_{safe(set_name)}_{algo}.json")
    if os.path.exists(path):
        d = json.load(open(path, encoding="utf-8"))
        if len(d["scores"]) == len(parses):
            return d["scores"], d["ok"]
    fn = SCORERS[algo][1]
    scores, ok = [], []
    for i, (rid, s, p) in enumerate(parses):
        try:
            sc = fn(p)
        except Exception as e:
            print(f"    ! {algo} {rid}: {type(e).__name__}: {e}")
            sc = None
        ok.append(sc is not None)
        scores.append(sc if sc is not None else [0.0] * (p.n + 1))
    json.dump({"scores": scores, "ok": ok}, open(path, "w", encoding="utf-8"))
    return scores, ok


# ------------------------------------------------------------------ прогон

PEN = {"np_inner": 0.35, "before_aux": 0.25, "subj_verb": 0.25}


def run(set_name, algos, grid, use_constraints, blind=False, limit=None, params_json=None,
        use_syl=False, use_pen=False):
    per_algo = {}
    if params_json and os.path.exists(params_json):
        per_algo = json.load(open(params_json, encoding="utf-8"))
    os.makedirs(RESULTS, exist_ok=True)
    import stanza
    nlp = stanza.Pipeline("de", processors="tokenize,pos,lemma,depparse,constituency",
                          verbose=False, download_method=None)

    if set_name.startswith("file:"):
        path = set_name.split(":", 1)[1]
        rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
        if all(not r.get("blocks") for r in rows):
            blind = True
    else:
        rows = load_corpus() if set_name == "corpus52" else load_heldout()
    if limit:
        rows = rows[:limit]
    print(f"набор: {set_name}, предложений: {len(rows)}")

    parses, truth = [], []
    t0 = time.time()
    for k, r in enumerate(rows):
        s = r.get("sentence") or r.get("text")
        p = build_parse(s, nlp)
        if p is None:
            continue
        parses.append((r.get("id", f"#{k}"), s, p))
        truth.append(None if blind or not r.get("blocks") else truth_cuts(s, r["blocks"], p))
    print(f"разбор: {len(parses)} предложений за {time.time()-t0:.1f} с")

    variants = [("по умолчанию", DEFAULT)]
    if grid:
        variants += [(f"{obj} ideal={ideal} w={w} cap={cap}" + (" syl" if use_syl else "")
                      + (" pen" if use_pen else ""),
                      {"min_lex": 2, "ideal": ideal, "cap": cap, "w_len": w, "objective": obj,
                       **({"syl_max_words": 3, "syl_from": 7} if use_syl else {}),
                       **({"pen": PEN} if use_pen else {})})
                     for obj in ("sum", "mean")
                     for ideal in (3.0, 4.0, 5.0) for w in (0.3, 1.0, 2.5) for cap in (6, 7)]

    summary = []
    for algo in algos:
        t_algo = time.time()
        name = (SCORERS.get(algo) or BASELINES.get(algo) or DIRECT.get(algo))[0]
        scores = None
        if algo in DIRECT:
            pass
        elif algo in SCORERS:
            scores, ok = get_scores(algo, set_name, parses)
            print(f"  {algo} {name}: оценок нет у {ok.count(False)} предл.")

        f_q4, f_pp = [], []
        for rid, s, p in parses:
            base = p.forbidden_base()
            f4 = (p.forbidden_after_funcword() if use_constraints else set()) | base
            fpp = (p.pp_inner_positions() if use_constraints else set()) | base
            f_q4.append(f4)
            f_pp.append(fpp)

        algo_variants = variants
        if per_algo.get(algo):
            algo_variants = [("лучшая на 52", per_algo[algo])] + variants
        for vname, params in algo_variants:
            pairs, stats = [], []
            for i, (rid, s, p) in enumerate(parses):
                if algo in DIRECT:
                    bounds = enforce(DIRECT[algo][1](p) or [0, p.n], p, params)
                elif algo in BASELINES:
                    bounds = BASELINES[algo][1](p, params, f_q4[i])
                else:
                    sc = apply_penalties(scores[i], p, params.get("pen")) if params.get("pen") else scores[i]
                    bounds, _lvl = dp_try(sc, p, params,
                                          [f_q4[i] | f_pp[i], f_q4[i], p.pp_inner_positions()])
                    bounds = enforce(bounds, p, params)
                stats.append(block_stats(p, bounds))
                pairs.append((set(bounds[1:-1]), truth[i]))
            m = score_metrics([x for x in pairs if x[1] is not None]) if not blind else None
            nb = sum(st["nblocks"] for st in stats)
            row = {
                "algo": algo, "name": name, "variant": vname, "params": params,
                "exact": (m or {}).get("exact", None), "n": (m or {}).get("n", 0),
                "P": (m or {}).get("P", None), "R": (m or {}).get("R", None),
                "F1": (m or {}).get("F1", None),
                "blocks": nb,
                "blocks_out_of_range": sum(1 for st in stats for L in st["lens"] if L < 2 or L > 7),
                "func_end": sum(st["func_end"] for st in stats),
                "pp_inner": sum(st["pp_inner"] for st in stats),
                "mean_len": round(sum(L for st in stats for L in st["lens"]) / max(nb, 1), 2),
            }
            summary.append(row)
        print(f"  {algo}: готов за {time.time()-t_algo:.1f} с")

    write_predictions(set_name, parses, truth, algos, use_constraints,
                      DEFAULT, per_algo)
    write_summary(set_name, summary, blind, use_constraints, use_syl, use_pen)
    print_summary(summary, blind)
    return summary


def write_predictions(set_name, parses, truth, algos, use_constraints, params, per_algo=None):
    for algo in algos:
        params = (per_algo or {}).get(algo, params)
        suffix = "_c" if use_constraints else ""
        path = os.path.join(RESULTS, f"{safe(set_name)}_{algo}{suffix}.jsonl")
        scores = None
        if algo in DIRECT:
            pass
        elif algo in SCORERS:
            scores, _ = get_scores(algo, set_name, parses)
        with open(path, "w", encoding="utf-8") as f:
            for i, (rid, s, p) in enumerate(parses):
                base = p.forbidden_base()
                f4 = (p.forbidden_after_funcword() if use_constraints else set()) | base
                fpp = (p.pp_inner_positions() if use_constraints else set()) | base
                if algo in DIRECT:
                    bounds = enforce(DIRECT[algo][1](p) or [0, p.n], p, params)
                elif algo in BASELINES:
                    bounds = BASELINES[algo][1](p, params, f4)
                else:
                    sc = apply_penalties(scores[i], p, params.get("pen")) if params.get("pen") else scores[i]
                    bounds, _lvl = dp_try(sc, p, params, [f4 | fpp, f4, fpp])
                    bounds = enforce(bounds, p, params)
                f.write(json.dumps({"id": rid, "sentence": s,
                                    "blocks": bounds_to_blocks(p, bounds),
                                    "cuts": bounds[1:-1],
                                    "truth": sorted(truth[i]) if truth[i] is not None else None},
                                   ensure_ascii=False) + "\n")


def write_summary(set_name, summary, blind, use_constraints=False, use_syl=False, use_pen=False):
    suffix = ("_c" if use_constraints else "") + ("_syl" if use_syl else "") +              ("_pen" if use_pen else "") + ("_blind" if blind else "")
    json.dump(summary, open(os.path.join(RESULTS, f"summary_{safe(set_name)}{suffix}.json"), "w",
                            encoding="utf-8"), ensure_ascii=False, indent=1)
    md = [f"# Сравнение алгоритмов: {set_name}{' (слепой режим)' if blind else ''}\n",
          "| алгоритм | вариант | exact | P | R | **F1** | блоков | вне 2–7 | кончается служ. | рез в PP | ср. длина |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(summary, key=lambda x: (x["algo"], -(x["F1"] or 0))):
        md.append(f"| {r['algo']} {r['name']} | {r['variant']} | {r['exact']}/{r['n']} | {r['P']} | "
                  f"{r['R']} | **{r['F1']}** | {r['blocks']} | {r['blocks_out_of_range']} | "
                  f"{r['func_end']} | {r['pp_inner']} | {r['mean_len']} |")
    open(os.path.join(RESULTS, f"summary_{safe(set_name)}{suffix}.md"), "w", encoding="utf-8").write(
        "\n".join(md) + "\n")


def print_summary(summary, blind):
    print("\n" + "=" * 122)
    print(f"{'алг':4} {'вариант':36} {'exact':>8} {'P':>5} {'R':>5} {'F1':>5} {'блоков':>7} {'вне2-7':>7} {'функ':>5} {'PP':>4}")
    print("-" * 122)
    for r in summary:
        if blind:
            print(f"{r['algo']:4} {r['variant']:36} {'—':>8} {'—':>5} {'—':>5} {'—':>5} "
                  f"{r['blocks']:7} {r['blocks_out_of_range']:7} {r['func_end']:5} {r['pp_inner']:4}")
        else:
            print(f"{r['algo']:4} {r['variant']:36} {str(r['exact'])+'/'+str(r['n']):>8} "
                  f"{r['P']:5.2f} {r['R']:5.2f} {r['F1']:5.2f} {r['blocks']:7} "
                  f"{r['blocks_out_of_range']:7} {r['func_end']:5} {r['pp_inner']:4}")
    print("=" * 122)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="corpus52",
                    help="corpus52 | heldout | file:<путь к jsonl>")
    ap.add_argument("--algo", default="all")
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--constraints", action="store_true")
    ap.add_argument("--blind", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--params-json", default=None)
    ap.add_argument("--syl", action="store_true", help="включить Q17(г): 7+ слогов -> max 3 слова")
    ap.add_argument("--pen", action="store_true", help="включить мягкие штрафы (np_inner/before_aux/subj_verb)")
    a = ap.parse_args()

    algos = list(BASELINES) + list(SCORERS) + list(DIRECT) if a.algo == "all" else a.algo.split(",")
    unknown = [x for x in algos if x not in SCORERS and x not in BASELINES and x not in DIRECT]
    if unknown:
        print("неизвестные алгоритмы:", unknown)
        print("доступны:", list(BASELINES) + list(SCORERS) + list(DIRECT))
        return 2
    if a.set == "heldout":
        a.blind = True
    if a.syl:
        DEFAULT["syl_max_words"] = 3
        DEFAULT["syl_from"] = 7
    if a.pen:
        DEFAULT["pen"] = dict(PEN)
    run(a.set, algos, a.grid, a.constraints, a.blind, a.limit, a.params_json, a.syl, a.pen)
    return 0


if __name__ == "__main__":
    sys.exit(main())
