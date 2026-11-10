# -*- coding: utf-8 -*-
"""Эксперименты V3 на НОВОЙ разметке (52 + 51): что меняется, если поправить запреты.

Главный вопрос итерации: старая формулировка Q3 («нельзя резать внутри предложной группы»)
в реализации запрещает не только «in | seiner Firma», но и «zur Bezeichnung | neben …».
Новая разметка (энциклопедический и новостной стиль) режет по второму типу в 17.7% случаев.

Стадии:
  constraints : Q3 выкл / строгий (ADP→сущ.) / широкий (как было)
  punct       : рез перед скобкой/тире/кавычкой — можно или нельзя
  cap         : предел длины блока (Q26)
  q22         : блок из 1 слова (финитный глагол в конце)
  pen         : штрафы (Q25), включая новый «NP | PP-определение»
  grid        : ideal × w_len × objective при лучших запретах

Каркас — тот же, что в bench/run_bench.py (dp_try + enforce), поэтому цифры сравнимы
с прошлыми итерациями.

  python bench/experiments.py --stage constraints
"""
import argparse
import io
import itertools
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bench.core import (dp_try, enforce, pp_spans, score_metrics, score_with_pen,
                        truth_cuts, constraint_chain, base_forbidden_v4)
from bench.pcache import get_parses

HERE = os.path.dirname(os.path.abspath(__file__))
SET_DIR = os.path.join(HERE, "sets")
CACHE = os.path.join(HERE, "cache")

FUNC_UPOS = {"ADP", "DET", "CCONJ", "SCONJ", "PART"}
ATTACHED = {",", ".", "!", "?", ";", ":", "…"}     # приклеены к левому блоку


# ------------------------------------------------------------------ запреты/каркас из core

def spans(p):
    return pp_spans(p)


def base_forbidden(p, punct_v2):
    return base_forbidden_v4(p, punct_v2)


# ------------------------------------------------------------------ оценка

def evaluate(parses, truth, scores, cfg, mode, punct_v2):
    pairs = []
    stat = {"blocks": 0, "oor": 0, "func_end": 0, "pp_strict": 0, "punct": 0, "hyphen": 0,
            "one_word": 0}
    for i, (rid, s, p) in enumerate(parses):
        chain = constraint_chain(p, mode, punct_v2)
        sc = score_with_pen(scores[i], p, cfg.get("pen"))
        b, _lvl = dp_try(sc, p, cfg, chain)
        b = enforce(b, p, cfg)
        pairs.append((set(b[1:-1]), truth[i]))
        st, _ = spans(p)
        for a, c in zip(b[:-1], b[1:]):
            if c <= a:
                continue
            stat["blocks"] += 1
            lc = p.lex_count(a, c)
            last1 = (c == p.n and lc == 1 and p.upos[a] in ("VERB", "AUX"))
            if lc < cfg["min_lex"]:
                stat["one_word"] += 1
                if not last1:
                    stat["oor"] += 1
            if lc > cfg["cap"]:
                stat["oor"] += 1
            if a > 0 and p.upos[a - 1] in FUNC_UPOS:
                stat["func_end"] += 1
            if a > 0 and a in st:
                stat["pp_strict"] += 1
            if a > 0 and p.upos[a] == "PUNCT" and p.tokens[a][0] in ATTACHED:
                stat["punct"] += 1
            if a > 0 and p.tokens[a - 1][0].endswith("-") and not p.tokens[a][0].startswith("("):
                stat["hyphen"] += 1
    m = score_metrics(pairs)
    m.update(stat)
    return m


def load(set_name, algo):
    path = os.path.join(SET_DIR, set_name + ".jsonl")
    rows, parses = get_parses(path)
    key = set_name          # имена файлов = имя набора (см. run_bench.set_key)
    sc_path = os.path.join(CACHE, f"scores_{key}_{algo}.json")
    if not os.path.exists(sc_path):
        raise SystemExit(f"нет кэша оценок: {sc_path}\nсначала:\n"
                         f"  python bench/run_bench.py --set file:{path} --algo {algo}")
    d = json.load(open(sc_path, encoding="utf-8"))
    keep = [i for i, r in enumerate(rows) if r.get("blocks")]
    truth = [truth_cuts(rows[i]["sentence"], rows[i]["blocks"], parses[j][2])
             for j, i in enumerate(keep)]
    scores = [d["scores"][j] for j, i in enumerate(keep)]
    parses = [parses[j] for j, i in enumerate(keep)]
    return parses, truth, scores


BASE = {"min_lex": 2, "ideal": 3.0, "cap": 6, "w_len": 0.3, "objective": "mean",
        "syl_max_words": 3, "syl_from": 7}
PEN_BASE = {"np_inner": 0.35, "before_aux": 0.25, "subj_verb": 0.25}


def header(title):
    print(f"\n{'=' * 124}\n{title}\n{'=' * 124}")
    print(f"{'вариант':50} {'F1@52':>5} {'F1@51':>5}  {'exact52':>7} {'exact51':>7}"
          f" {'блок51':>6} {'вне':>4} {'Q4':>3} {'PP':>3} {'пункт':>5}")


def row(label, m52, m51):
    print(f"{label:50} {m52['F1']:.3f} {m51['F1']:.3f}  {str(m52['exact']) + '/' + str(m52['n']):>9}"
          f" {str(m51['exact']) + '/' + str(m51['n']):>9}"
          f" {m51['blocks']:6} {m51['oor']:4} {m51['func_end']:3} {m51['pp_strict']:3} {m51['punct']:5}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="constraints")
    ap.add_argument("--algo", default="S1")
    a = ap.parse_args()

    P52, T52, S52 = load("corpus52", a.algo)
    P51, T51, S51 = load("heldout_51", a.algo)
    print(f"алгоритм {a.algo}: настройка — 52 предложения, проверка — 51 предложение")

    def both(cfg, mode="strict", pv=True):
        return (evaluate(P52, T52, S52, cfg, mode, pv),
                evaluate(P51, T51, S51, cfg, mode, pv))

    if a.stage in ("constraints", "all"):
        header("Q3: что считать «резом внутри предложной группы» (остальное — как было)")
        for mode in ("broad", "strict", "off"):
            for pv in (False, True):
                cfg = dict(BASE, pen=PEN_BASE)
                row(f"Q3={mode:6} пункт-нов.={'да' if pv else 'нет':3} штрафы", *both(cfg, mode, pv))

    if a.stage in ("punct", "all"):
        header("Рез перед пунктуацией: приклеена только «, . ! ? ; :», перед скобкой/тире/кавычкой — можно")
        for mode in ("broad", "strict"):
            for pv in (False, True):
                cfg = dict(BASE, pen=PEN_BASE)
                row(f"Q3={mode:6} пункт-нов.={'да' if pv else 'нет':3}", *both(cfg, mode, pv))

    if a.stage in ("cap", "all"):
        header("Предел длины блока (Q26): 4 / 5 / 6 / 7 / 8 слов")
        for cap in (4, 5, 6, 7, 8):
            cfg = dict(BASE, cap=cap, pen=PEN_BASE)
            row(f"cap={cap}", *both(cfg))

    if a.stage in ("q22", "all"):
        header("Q22: блок из одного слова — разрешить финитному глаголу в конце")
        for allow in (False, True):
            cfg = dict(BASE, pen=PEN_BASE, allow_one_word_final=allow)
            row(f"1 слово в конце: {'да' if allow else 'нет'}", *both(cfg))

    if a.stage in ("pen", "all"):
        header("Штрафы (Q25): какие веса полезны (Q3=strict, пункт-нов.=да)")
        variants = {
            "без штрафов": None,
            "как было 0.35/0.25/0.25": PEN_BASE,
            "только ppmod 0.20": {"ppmod": 0.20},
            "только ppmod 0.35": {"ppmod": 0.35},
            "ppmod 0.20 + старые": {"ppmod": 0.20, **PEN_BASE},
            "ppmod 0.35 + старые": {"ppmod": 0.35, **PEN_BASE},
            "ppmod 0.20 + aux/subj": {"ppmod": 0.20, "before_aux": 0.25, "subj_verb": 0.25},
            "ppmod 0.35, без np_inner": {"ppmod": 0.35, "before_aux": 0.25, "subj_verb": 0.25},
            "ppmod 0.20 + np_inner 0.15": {"ppmod": 0.20, "np_inner": 0.15,
                                           "before_aux": 0.25, "subj_verb": 0.25},
        }
        for name, pen in variants.items():
            cfg = dict(BASE, pen=pen)
            row(name, *both(cfg))

    if a.stage in ("grid", "all"):
        header("Сетка параметров при Q3=strict, пункт-нов.=да, штрафы ppmod 0.2 + старые")
        pen = {"ppmod": 0.20, **PEN_BASE}
        res = []
        for obj, ideal, w, cap in itertools.product(("sum", "mean"), (3.0, 3.5, 4.0),
                                                    (0.1, 0.3, 0.6, 1.0), (5, 6, 7)):
            cfg = {"min_lex": 2, "ideal": ideal, "w_len": w, "cap": cap, "objective": obj,
                   "syl_max_words": 3, "syl_from": 7, "pen": pen}
            m52 = evaluate(P52, T52, S52, cfg, "strict", True)
            res.append((m52["F1"], obj, ideal, w, cap, m52))
        res.sort(reverse=True, key=lambda x: x[0])
        print("  (сортировка по F1 на 52; последняя колонка — что вышло на 51)")
        for f1, obj, ideal, w, cap, m52 in res[:10]:
            cfg = {"min_lex": 2, "ideal": ideal, "w_len": w, "cap": cap, "objective": obj,
                   "syl_max_words": 3, "syl_from": 7, "pen": pen}
            row(f"{obj} ideal={ideal} w={w} cap={cap}", m52,
                evaluate(P51, T51, S51, cfg, "strict", True))


    if a.stage in ("final", "all"):
        header("Итоговые сборки: старые правила против предлагаемых")
        fin = [
            ("как было: Q3=широкий, пункт-стар., штрафы", "broad", False, PEN_BASE, 6, 3.0, "mean"),
            ("Q3=строгий, пункт-стар., штрафы", "strict", False, PEN_BASE, 6, 3.0, "mean"),
            ("Q3=строгий, пункт-стар., без штрафов", "strict", False, None, 6, 3.0, "mean"),
            ("Q3=строгий, пункт-стар., штрафы 0.20/0.15/0.15", "strict", False,
             {"np_inner": 0.20, "before_aux": 0.15, "subj_verb": 0.15}, 6, 3.0, "mean"),
            ("Q3=строгий, пункт-стар., ppmod 0.20", "strict", False, {"ppmod": 0.20}, 6, 3.0, "mean"),
            ("Q3=строгий, пункт-стар., штрафы, cap=5", "strict", False, PEN_BASE, 5, 3.0, "mean"),
            ("Q3=строгий, пункт-стар., штрафы, ideal=3.5", "strict", False, PEN_BASE, 6, 3.5, "mean"),
            ("Q3=строгий, пункт-стар., штрафы, ideal=4", "strict", False, PEN_BASE, 6, 4.0, "mean"),
            ("Q3=строгий, пункт-стар., штрафы, w=0.6", "strict", False, PEN_BASE, 6, 3.0, "mean"),
            ("Q3=строгий, пункт-стар., штрафы, сумма", "strict", False, PEN_BASE, 6, 3.0, "sum"),
        ]
        for label, mode, pv, pen, cap, ideal, obj in fin:
            cfg = {"min_lex": 2, "ideal": ideal, "cap": cap,
                   "w_len": 0.6 if "w=0.6" in label else 0.3, "objective": obj,
                   "syl_max_words": 3, "syl_from": 7, "pen": pen}
            row(label, *both(cfg, mode, pv))

    if a.stage in ("tune2", "all"):
        header("Подбор весов штрафов (Q3=strict, пункт-стар., cap=6)")
        vs = {
            "старые 0.35/0.25/0.25": PEN_BASE,
            "0.20/0.15/0.15": {"np_inner": 0.20, "before_aux": 0.15, "subj_verb": 0.15},
            "0.20/0.15/0.15 + ppmod 0.15": {"np_inner": 0.20, "before_aux": 0.15,
                                            "subj_verb": 0.15, "ppmod": 0.15},
            "0.15/0.10/0.10 + ppmod 0.15": {"np_inner": 0.15, "before_aux": 0.10,
                                            "subj_verb": 0.10, "ppmod": 0.15},
            "ppmod 0.15": {"ppmod": 0.15},
            "ppmod 0.10": {"ppmod": 0.10},
            "0.25/0.20/0.20": {"np_inner": 0.25, "before_aux": 0.20, "subj_verb": 0.20},
        }
        for name, pen in vs.items():
            cfg = dict(BASE, pen=pen)
            row(name, *both(cfg, "strict", False))

if __name__ == "__main__":
    main()
