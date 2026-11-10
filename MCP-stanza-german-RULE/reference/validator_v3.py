# -*- coding: utf-8 -*-
"""Валидатор разбивки V3 (итерация 4).

Проверяет готовую разбивку предложения на блоки по правилам, выведенным из разметки
заказчика (52 + 51 = 103 предложения, 467 блоков, 415 резов).

Три уровня:
  error   — так делать нельзя (блок невалиден);
  warning — можно, но лучше не надо (предупреждение);
  info    — допустимо, но правило считает это слабым местом (мягкий штраф).

Ни одного немецкого слова в коде: все списки и числа — в DEFAULT_CFG (и в config.json,
раздел "segment", если он есть).

CLI:
  python reference/validator_v3.py --text "Ich habe bei der Firma gearbeitet." --blocks "Ich habe|bei der Firma gearbeitet."
  python reference/validator_v3.py --set E:/KI_WORK/bench/sets/heldout_51.jsonl
  python reference/validator_v3.py --self-test
"""
import argparse
import io
import json
import os
import re
import sys

DEFAULT_CFG = {
    "objective": "mean",
    "w_len": 0.3,
    "min_lex": 2,
    "ideal_lex": 3,
    "cap_lex": 6,
    "warn_above_lex": 7,
    "bans": {
        "before_punct": [",", ".", "!", "?", ";", ":", "\u2026"],
        "after_upos": ["ADP", "DET", "CCONJ", "SCONJ", "PART"],
        "inside_pp": "strict",          # strict: только ADP -> его существительное
        "inside_hyphen": True,
        "after_open_quote": True,
    },
    "one_word": {
        "allow_final_verb": True,
        "allow_abbrev": ["etc.", "etc", "usw.", "usw", "bzw.", "bzw", "bzw", "vgl.", "ca."],
        "allow_parenthetical": True,
    },
    "syllables": {"from": 7, "max_words": 3},
    "penalties": {"np_inner": 0.35, "before_aux": 0.25, "subj_verb": 0.25},
    "np_inner_deprels": ["det", "det:poss", "amod", "nummod", "nmod", "nmod:poss",
                         "flat", "compound", "appos"],
    "open_quotes": ["\u201e", "\u00bb", "\u00ab", "\u201a"],  # „ » « ‚ — только открывающие
    "stats_marks": {"terminal": [".", "?", "!"], "comma": [","]},
}

_nlp = None


def nlp():
    global _nlp
    if _nlp is None:
        import stanza
        _nlp = stanza.Pipeline("de", processors="tokenize,pos,lemma,depparse",
                               verbose=False, download_method=None)
    return _nlp


# ------------------------------------------------------------------ разбор

class Sent:
    def __init__(self, text, sent):
        self.text = text
        toks = list(sent.tokens)
        ids = [(t.id if isinstance(t.id, tuple) else (t.id,)) for t in toks]
        w2t = {}
        for i, ii in enumerate(ids):
            for wid in ii:
                w2t.setdefault(wid, i)
        byid = {w.id: w for w in sent.words if not isinstance(w.id, tuple)}
        self.tokens = []
        heads = []
        for i, t in enumerate(toks):
            w = byid.get(ids[i][0])
            upos = w.upos if w else ""
            dep = w.deprel if w else ""
            heads.append(w.head if w else 0)
            self.tokens.append((t.text, upos, dep, t.start_char, t.end_char))
        self.n = len(self.tokens)
        self.heads_tok = [w2t.get(h, -1) for h in heads]
        self.upos = [x[1] for x in self.tokens]
        self.deprel = [x[2] for x in self.tokens]

    def lex_count(self, a, b):
        return sum(1 for i in range(a, b) if self.upos[i] != "PUNCT")

    def syllables(self):
        if getattr(self, "_syl", None) is None:
            import pyphen
            dic = pyphen.Pyphen(lang="de_DE")
            out = []
            for txt, upos, *_ in self.tokens:
                w = re.sub(r"^[^A-Za-zÄÖÜäöüß]+|[^A-Za-zÄÖÜäöüß]+$", "", txt)
                if upos == "PUNCT" or not w:
                    out.append(0)
                elif "-" in w:
                    out.append(sum(dic.inserted(x).count("-") + 1 for x in w.split("-") if x))
                else:
                    out.append(dic.inserted(w).count("-") + 1)
            self._syl = out
        return self._syl

    def max_syl(self, a, b):
        s = self.syllables()
        return max(s[a:b]) if b > a else 0


def parse(text, pipeline=None):
    doc = (pipeline or nlp())(text)
    return Sent(text, doc.sentences[0])


# ------------------------------------------------------------------ позиции

def pp_positions(s, mode, np_inner):
    """Позиции реза внутри предложной группы.

    strict — только между предлогом и его существительным («in | seiner Firma»);
    broad  — плюс между существительным и его предложным определением
             («zur Bezeichnung | neben …») — заказчик так режет в 17.7% случаев,
             поэтому это не запрет, а мягкий штраф (см. penalties.ppmod).
    """
    kids = {}
    for i, h in enumerate(s.heads_tok):
        if h >= 0:
            kids.setdefault(h, []).append(i)
    bad = set()
    for i, (dep, up) in enumerate(zip(s.deprel, s.upos)):
        if dep != "case" or up != "ADP":
            continue
        h = s.heads_tok[i]
        if h < 0:
            continue
        members = {i, h}
        if mode == "broad":
            stack = [h]
            while stack:
                cur = stack.pop()
                for ch in kids.get(cur, []):
                    if s.deprel[ch] in np_inner:
                        members.add(ch)
                        stack.append(ch)
        lo, hi = min(members), max(members)
        bad.update(range(lo + 1, hi + 1))
    return bad


def np_inner_positions(s, np_inner):
    out = set()
    for i in range(1, s.n):
        l, r = i - 1, i
        if s.deprel[r] in np_inner and s.heads_tok[r] == l:
            out.add(i)
        if s.deprel[l] in np_inner and s.heads_tok[l] == r:
            out.add(i)
    return out


def aux_positions(s):
    return {i for i in range(1, s.n) if s.upos[i] == "AUX"}


def subj_verb_positions(s):
    return {i for i in range(1, s.n)
            if s.upos[i - 1] == "PRON" and s.deprel[i - 1] in ("nsubj", "nsubj:pass")
            and s.heads_tok[i - 1] == i}


def blocks_text(s, bounds):
    """Текст блоков по границам токенов (сохраняя пунктуацию и кавычки как в исходнике)."""
    out = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b > a and s.tokens[a][3] is not None and s.tokens[b - 1][4] is not None:
            out.append(s.text[s.tokens[a][3]:s.tokens[b - 1][4]].strip())
        else:
            out.append(" ".join(t[0] for t in s.tokens[a:b]))
    return out


def blocks_to_bounds(s, blocks):
    """Границы блоков в токенах. Сверяем по символам, а не по словам (пунктуация)."""
    bounds, pos = [0], 0
    for b in blocks[:-1]:
        pos += len(b) + 1          # блок + пробел
        cut = pos - 1
        idx = next((i for i, t in enumerate(s.tokens) if t[3] >= cut), None)
        if idx is None or idx <= bounds[-1]:
            return None
        bounds.append(idx)
    bounds.append(s.n)
    return bounds


# ------------------------------------------------------------------ проверка

def check(text, blocks, cfg=None, pipeline=None):
    cfg = cfg or DEFAULT_CFG
    bans = cfg["bans"]
    s = parse(text, pipeline)
    bounds = blocks_to_bounds(s, blocks)
    if bounds is None:
        return {"verdict": "invalid_input",
                "reason": "блоки не складываются в предложение (проверьте пробелы)",
                "errors": [], "warnings": [], "info": []}
    pp_strict = pp_positions(s, "strict", cfg["np_inner_deprels"])
    pp_broad = pp_positions(s, "broad", cfg["np_inner_deprels"])
    ppmod = pp_broad - pp_strict
    npinner = np_inner_positions(s, cfg["np_inner_deprels"])
    aux = aux_positions(s)
    sv = subj_verb_positions(s)

    errors, warnings, info = [], [], []

    def add(lst, code, message, at, suggestion=""):
        lst.append({"code": code, "message": message, "at": at, "suggestion": suggestion})

    cost = 0.0
    for k, (a, b) in enumerate(zip(bounds[:-1], bounds[1:])):
        lc = s.lex_count(a, b)
        left = " ".join(t[0] for t in s.tokens[a:b])
        # ---- длина блока
        if lc < cfg["min_lex"]:
            single = min((t[0] for t in s.tokens[a:b] if t[1] != "PUNCT"), default="", key=len)
            ok_final_verb = (cfg["one_word"]["allow_final_verb"] and b == s.n
                             and s.upos[a] in ("VERB", "AUX"))
            ok_abbrev = single.strip(".,;:") in [x.strip(".,;:") for x in cfg["one_word"]["allow_abbrev"]]
            ok_paren = (cfg["one_word"]["allow_parenthetical"] and any(
                t[1] == "PUNCT" and t[0] in ("(", ")", "[", "]") for t in s.tokens[a:b]))
            if ok_final_verb or ok_abbrev or ok_paren:
                warnings.append({"code": "L1", "message": f"блок из одного слова «{left}»",
                                 "at": k + 1, "suggestion": "допустимо: финитный глагол/сокращение/вставка"})
            else:
                add(errors, "L1", f"блок из одного слова «{left}» (минимум {cfg['min_lex']})", k + 1,
                    "присоединить к соседнему блоку")
        elif lc > cfg["cap_lex"]:
            (add(errors, "L2", f"блок из {lc} слов (предел {cfg['cap_lex']}): «{left}»", k + 1,
                 "разрезать")
             if lc > cfg["warn_above_lex"] else
             warnings.append({"code": "L2", "message": f"блок из {lc} слов (предел {cfg['cap_lex']})",
                              "at": k + 1, "suggestion": "разрезать, если есть где"}))
        # ---- слоговая страховка
        syl = cfg["syllables"]
        if syl and lc > syl["max_words"] and s.max_syl(a, b) >= syl["from"]:
            warnings.append({"code": "S1",
                             "message": f"в блоке из {lc} слов есть слово длиной "
                                        f"{s.max_syl(a, b)} слогов", "at": k + 1,
                             "suggestion": f"не длиннее {syl['max_words']} слов"})
        # ---- рез
        if b < s.n:
            i = b
            pair = f"«{s.tokens[i - 1][0]} | {s.tokens[i][0]}»"
            if i in pp_strict and s.upos[i - 1] == "ADP":
                add(errors, "Q3", f"рез сразу после предлога {pair}", i,
                    "резать перед предлогом, а не после")
            elif s.upos[i - 1] in bans["after_upos"]:
                add(errors, "Q4", f"блок кончается служебным словом {pair}", i,
                    "сдвинуть рез на слово влево или вправо")
            elif i in pp_strict:
                warnings.append({"code": "Q3", "message": f"рез внутри предложной группы {pair}",
                                 "at": i, "suggestion": "можно, но правило считает это слабым местом"})
            if s.upos[i] == "PUNCT" and s.tokens[i][0] in bans["before_punct"]:
                add(errors, "P2", f"рез перед знаком препинания {pair}", i, "знак — к левому блоку")
            if bans["inside_hyphen"] and s.tokens[i - 1][0].endswith("-") \
                    and not s.tokens[i][0].startswith("("):
                add(errors, "H1", f"рез внутри дефисного слова {pair}", i, "держать слово целиком")
            if bans["after_open_quote"] and s.tokens[i - 1][0] in cfg["open_quotes"]:
                add(errors, "H2", f"рез сразу после открывающей кавычки {pair}", i, "кавычка — к правому блоку")
            if i in ppmod:
                cost += 1.0
                info.append({"code": "PP", "message": f"рез на границе PP-определения {pair}", "at": i,
                             "weight": "ppmod"})
            if i in npinner:
                cost += cfg["penalties"]["np_inner"]
                info.append({"code": "N1", "message": f"рез внутри именной группы {pair}", "at": i,
                             "weight": cfg["penalties"]["np_inner"]})
            if i in aux:
                cost += cfg["penalties"]["before_aux"]
                info.append({"code": "AUX", "message": f"рез перед вспомогательным глаголом {pair}", "at": i,
                             "weight": cfg["penalties"]["before_aux"]})
            if i in sv:
                cost += cfg["penalties"]["subj_verb"]
                info.append({"code": "SV", "message": f"рез между подлежащим и сказуемым {pair}", "at": i,
                             "weight": cfg["penalties"]["subj_verb"]})
    # ---- P1: терминальный знак в последнем блоке
    if s.n and s.upos[-1] == "PUNCT" and s.tokens[-1][0] in cfg["stats_marks"]["terminal"]:
        last = bounds[-2]
        if last == s.n - 1:
            add(errors, "P1", "последний блок — только знак препинания", len(bounds) - 1,
                "знак — к предыдущему блоку")
    return {"verdict": "non_compliant" if errors else "compliant",
            "errors": errors, "warnings": warnings, "info": info,
            "cost": round(cost, 3), "n_blocks": len(bounds) - 1,
            "lens": [s.lex_count(a, b) for a, b in zip(bounds[:-1], bounds[1:])]}


# ------------------------------------------------------------------ прогон по набору

def run_set(path, cfg=None):
    cfg = cfg or DEFAULT_CFG
    pipeline = nlp()
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    stat = {"n": 0, "compliant": 0, "non_compliant": 0, "invalid": 0}
    codes = {}
    details = []
    for r in rows:
        if not r.get("blocks"):
            continue
        rep = check(r["sentence"], r["blocks"], cfg, pipeline)
        stat["n"] += 1
        stat[rep["verdict"] if rep["verdict"] in stat else "invalid"] += 1
        for e in rep["errors"]:
            codes[e["code"]] = codes.get(e["code"], 0) + 1
        if rep["errors"]:
            details.append((r["id"], rep))
    print(f"\n=== {os.path.basename(path)}: {stat['n']} предложений ===")
    print(f"  compliant {stat['compliant']} | non_compliant {stat['non_compliant']} | "
          f"invalid {stat['invalid']}")
    print("  ошибки по кодам: " + (", ".join(f"{k}:{v}" for k, v in sorted(codes.items())) or "нет"))
    for rid, rep in details:
        print(f"\n  {rid}: {len(rep['errors'])} ошибок")
        for e in rep["errors"][:6]:
            print(f"     [{e['code']}] {e['message']}")
    return stat, codes, details


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    ap.add_argument("--blocks", help="блоки через |")
    ap.add_argument("--set")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.set:
        run_set(a.set)
        return 0
    if not (a.text and a.blocks):
        ap.print_help()
        return 2
    blocks = [x.strip() for x in a.blocks.split("|")]
    rep = check(a.text, blocks)
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        print(f"{rep['verdict']}: блоков {rep.get('n_blocks')}, длина {rep.get('lens')}, "
              f"цена штрафов {rep.get('cost')}")
        for e in rep["errors"]:
            print(f"  ОШИБКА [{e['code']}] {e['message']} → {e['suggestion']}")
        for w in rep["warnings"]:
            print(f"  внимание [{w['code']}] {w['message']} → {w['suggestion']}")
        for i in rep["info"]:
            print(f"  штраф   [{i['code']}] {i['message']}")
    return 0 if rep["verdict"] == "compliant" else 1


if __name__ == "__main__":
    sys.exit(main())
