# -*- coding: utf-8 -*-
"""Нарезка немецкого предложения на блоки (V4) — рабочая программа, не стенд.

Алгоритм: S1 (расстояние между соседними словами по дереву зависимостей Stanza) +
динамическое программирование по всем вариантам нарезки. Ограничения и веса — из
config.json (раздел "segment"), в коде немецких слов и чисел нет.

Правила (что запрещено и почему — RULE_V3.md):
  * 2–6 слов в блоке (7 — предупреждение), 7+ слогов в слове -> не длиннее 3 слов;
  * нельзя резать сразу после служебного слова (ADP/DET/CCONJ/SCONJ/PART);
  * нельзя резать между предлогом и его существительным;
  * нельзя резать перед «, . ! ? ; :», внутри дефисного слова, после открывающей кавычки;
  * мягкие штрафы: внутри именной группы, перед вспомогательным глаголом,
    между подлежащим-местоимением и сказуемым.

CLI:
  python правило/segment.py --text "Ich habe bei der Firma gearbeitet."
  python правило/segment.py --file page.txt        # страница целиком
  python правило/segment.py --set ../../bench/sets/heldout_51.jsonl --f1
  python правило/segment.py --text "..." --check   # + проверка валидатором
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import normalize as N
import validator as V

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


load_cfg = V.load_cfg   # числа — из config.json (раздел segment)


# ------------------------------------------------------------------ оценка границы (S1)

def _lca(s, a, b):
    """Расстояние между двумя токенами по дереву зависимостей."""
    anc, cur, d = {}, a, 0
    while cur >= 0:
        anc.setdefault(cur, d)
        cur = s.heads_tok[cur]
        d += 1
    cur, d = b, 0
    while cur >= 0:
        if cur in anc:
            return anc[cur] + d
        cur = s.heads_tok[cur]
        d += 1
    return 99


def _norm(v):
    v = [float(x) for x in v]
    lo, hi = min(v), max(v)
    if hi - lo < 1e-9:
        return [0.0] * len(v)
    return [(x - lo) / (hi - lo) for x in v]


def score_s1(s):
    """score[i] — сила границы перед токеном i (0..1). Порт subtitle2go (Apache-2.0)."""
    sc = [0.0] * (s.n + 1)
    cand = [i for i in range(1, s.n) if s.lex_count(0, i) >= 1 and s.lex_count(i, s.n) >= 1]
    vals = []
    for i in cand:
        d = _lca(s, i - 1, i)
        vals.append(d / (1.0 + d))
    if not vals:
        return sc
    for i, v in zip(cand, _norm(vals)):
        sc[i] = v
    return sc


# ------------------------------------------------------------------ DP

def _forbidden(s, cfg):
    bans = cfg["bans"]
    base = set()
    for i in range(1, s.n):
        tok = s.tokens[i][0]
        # алгоритму выгоднее не резать перед ЛЮБЫМ знаком (валидатор при этом
        # пропускает резы перед «(», «–», «„» — заказчик так делает)
        if s.upos[i] == "PUNCT" and (bans.get("before_punct_segment") == "any"
                                     or tok in bans["before_punct"]):
            base.add(i)
        if bans["inside_hyphen"] and s.tokens[i - 1][0].endswith("-") and not tok.startswith("("):
            base.add(i)
        if bans["after_open_quote"] and s.tokens[i - 1][0] in bans["open_quotes"]:
            base.add(i)
    pp = V.pp_positions(s, bans.get("inside_pp", "strict"), cfg["np_inner_deprels"])
    # PP «в широкой трактовке» больше не запрет (17.7% резов заказчика), см. config.json
    q4 = {i for i in range(1, s.n) if s.upos[i - 1] in bans["after_upos"]}
    full = base | q4 | pp
    return [full, base | q4, pp]


def dp_mean(sc, s, cfg, forbidden):
    n = s.n
    min_lex, cap, ideal, w = cfg["min_lex"], cfg["cap_lex"], cfg["ideal_lex"], cfg["w_len"]
    syl = cfg.get("syllables") or {}
    # Q22 (блок из 1 слова) — исключение ТОЛЬКО для валидатора: в нарезке оно
    # ухудшает F1 на 52 (0.777 -> 0.759), на 51 не меняет.
    allow1 = False
    KMAX = max(2, n // max(min_lex, 1))
    NEG = float("-inf")
    best = [[NEG] * (KMAX + 1) for _ in range(n + 1)]
    prev = [[-1] * (KMAX + 1) for _ in range(n + 1)]
    best[0][0] = 0.0
    for end in range(1, n + 1):
        for k in range(1, KMAX + 1):
            for start in range(max(0, end - 60), end):
                if best[start][k - 1] == NEG:
                    continue
                lc = s.lex_count(start, end)
                if lc > cap:
                    continue
                if syl and lc > syl["max_words"] and s.max_syl(start, end) >= syl["from"]:
                    continue
                if start > 0:
                    if start in forbidden:
                        continue
                    if lc < min_lex and not (allow1 and end == n and lc == 1
                                             and s.upos[start] in ("VERB", "AUX")):
                        continue
                cand = best[start][k - 1] - w * abs(ideal - float(max(lc, 1)))
                if start > 0:
                    cand += sc[start]
                if cand > best[end][k]:
                    best[end][k] = cand
                    prev[end][k] = start
    bk, bv = None, NEG
    for k in range(1, KMAX + 1):
        if best[n][k] == NEG:
            continue
        v = best[n][k] / k
        if v > bv:
            bv, bk = v, k
    if bk is None:
        return None
    bounds, cur, k = [n], n, bk
    while cur > 0:
        cur = prev[cur][k]
        if cur < 0:
            return None
        bounds.append(cur)
        k -= 1
    return sorted(bounds)


def enforce(bounds, s, cfg):
    min_lex, cap = cfg["min_lex"], cfg["cap_lex"]
    # Q22 (блок из 1 слова) — исключение ТОЛЬКО для валидатора: в нарезке оно
    # ухудшает F1 на 52 (0.777 -> 0.759), на 51 не меняет.
    allow1 = False
    bounds = sorted(set(bounds))
    for _ in range(50):
        out = [bounds[0]]
        for b in bounds[1:]:
            while s.lex_count(out[-1], b) > cap:
                a, cnt, i = out[-1], 0, out[-1]
                while i < b:
                    if s.upos[i] != "PUNCT":
                        cnt += 1
                        if cnt == cap:
                            break
                    i += 1
                if i + 1 >= b:
                    break
                out.append(i + 1)
            out.append(b)
        bounds = out
        changed = False
        for k in range(len(bounds) - 1):
            if s.lex_count(bounds[k], bounds[k + 1]) < min_lex:
                if allow1 and bounds[k + 1] == s.n:
                    continue
                del bounds[k if k > 0 else k + 1]
                changed = True
                break
        if not changed and len(bounds) > 1 and s.lex_count(bounds[-2], bounds[-1]) < min_lex:
            if not (allow1 and s.lex_count(bounds[-2], bounds[-1]) == 1):
                bounds = bounds[:-2] + [bounds[-1]]
                changed = True
        if not changed:
            break
    return bounds


def bounds_of(sentence, cfg=None, pipeline=None):
    """Границы блоков в токенах: [0, c1, ..., n].

    sentence — текст или уже разобранное V.Sent (тогда разбор не повторяется).
    """
    cfg = cfg or load_cfg()
    # разбор уже есть — не парсим второй раз; иначе парсим текст
    parsed = hasattr(sentence, "tokens") and hasattr(sentence, "lex_count")
    s = sentence if parsed else V.parse(sentence, pipeline)
    sc = score_s1(s)
    pen = cfg.get("penalties") or {}
    pos = {"np_inner": V.np_inner_positions(s, cfg["np_inner_deprels"]),
           "before_aux": V.aux_positions(s),
           "subj_verb": V.subj_verb_positions(s)}
    for name, w in pen.items():
        for i in pos.get(name, ()):
            if 0 <= i < len(sc):
                sc[i] -= w
    bounds = None
    for fset in _forbidden(s, cfg):
        bounds = dp_mean(sc, s, cfg, fset)
        if bounds:
            break
    bounds = enforce(bounds or [0, s.n], s, cfg)
    return s, bounds


def segments_of_text(text, cfg=None, pipeline=None, do_normalize=True):
    """Страница/абзац -> (список предложений с блоками, правки нормализации).

    Нормализация (Q13) чинит только технический мусор: неразрывные пробелы, мягкие
    переносы, лигатуры, прямые кавычки, переводы строк. Слова не меняются.
    """
    cfg = cfg or load_cfg()
    clean, fixes = N.normalize(text) if do_normalize else (text, [])
    pipe = pipeline or V.nlp()
    doc = pipe(clean)
    out = []
    for sent in doc.sentences:
        s = V.Sent(clean, sent)
        bounds = bounds_of(s, cfg)[1]
        out.append({
            "text": sent.text,
            "blocks": V.blocks_text(s, bounds),
            "lens": [s.lex_count(a, b) for a, b in zip(bounds[:-1], bounds[1:])],
        })
    return out, fixes


def segment(sentence, cfg=None, pipeline=None, do_normalize=True):
    """Список блоков одного предложения (строки — как в исходном тексте)."""
    if hasattr(sentence, "tokens"):
        return V.blocks_text(sentence, bounds_of(sentence, cfg)[1])
    clean, _ = N.normalize(sentence) if do_normalize else (sentence, [])
    s, bounds = bounds_of(clean, cfg, pipeline)
    return V.blocks_text(s, bounds)


# ------------------------------------------------------------------ CLI

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    ap.add_argument("--file")
    ap.add_argument("--set")
    ap.add_argument("--f1", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--config")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-normalize", action="store_true", help="не чистить технический мусор")
    a = ap.parse_args()
    cfg = load_cfg(a.config)
    print(f"[правило: {cfg.get('_version', '?')} / {os.path.basename(str(cfg.get('_source')))}; "
          f"алгоритм S1; min {cfg['min_lex']}, ideal {cfg['ideal_lex']}, cap {cfg['cap_lex']}]",
          file=sys.stderr)

    if a.set:
        rows = [json.loads(l) for l in open(a.set, encoding="utf-8") if l.strip()]
        pipeline = V.nlp()
        tp = fp = fn = exact = 0
        for r in rows:
            if not r.get("blocks"):
                continue
            s, pred = bounds_of(r["sentence"], cfg, pipeline)
            truth = V.blocks_to_bounds(s, r["blocks"])
            if truth is None:
                continue
            p, t = set(pred[1:-1]), set(truth[1:-1])
            tp += len(p & t)
            fp += len(p - t)
            fn += len(t - p)
            exact += (p == t)
        prec = tp / (tp + fp) if tp + fp else 0
        rec = tp / (tp + fn) if tp + fn else 0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
        n = len([r for r in rows if r.get("blocks")])
        print(f"{os.path.basename(a.set)}: exact {exact}/{n}, P {prec:.3f}, R {rec:.3f}, F1 {f1:.3f}")
        return 0

    if a.file:
        text = open(a.file, encoding="utf-8").read()
        sentences, fixes = segments_of_text(text, cfg, do_normalize=not a.no_normalize)
        out = [{"sentence": x["text"], "blocks": x["blocks"]} for x in sentences]
        if fixes:
            print(f"[нормализация: {N.describe(fixes)}]", file=sys.stderr)
        if a.json:
            print(json.dumps(out, ensure_ascii=False, indent=1))
        else:
            for b in out:
                print("\n".join(f"  {x}" for x in b["blocks"]))
                print()
        return 0

    if not a.text:
        ap.print_help()
        return 2
    blocks = segment(a.text, cfg, do_normalize=not a.no_normalize)
    if a.json:
        print(json.dumps({"sentence": a.text, "blocks": blocks}, ensure_ascii=False, indent=1))
    else:
        print(f"блоков: {len(blocks)}")
        for i, b in enumerate(blocks, 1):
            print(f"  {i}. {b}")
    if a.check:
        rep = V.check(a.text, blocks, cfg)
        print(f"\nвалидатор: {rep['verdict']}, цена штрафов {rep.get('cost')}")
        for e in rep["errors"]:
            print(f"  ОШИБКА [{e['code']}] {e['message']}")
        for w in rep["warnings"]:
            print(f"  внимание [{w['code']}] {w['message']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
