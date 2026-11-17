# -*- coding: utf-8 -*-
"""Каркас испытания алгоритмов сегментации: разбор, DP, метрики.

Идея: у всех алгоритмов одинаковый каркас (DP + ограничения), отличается только
функция оценки границы (bench/scorers.py). Поэтому сравнение честное.
"""
import json
import os
import re
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # корень проекта
SETS = os.path.join(ROOT, "bench", "sets")
CORPUS = os.path.join(SETS, "corpus52.jsonl")     # разметка заказчика, 52 (настройка)
HELDOUT = os.path.join(SETS, "heldout_150.jsonl")    # 150 предложений (список для разметки)

FUNC_UPOS = {"ADP", "DET", "CCONJ", "SCONJ", "PART"}  # решение Q4 (без глаголов-связок)
NP_INNER = {"det", "det:poss", "amod", "nummod", "nmod", "nmod:poss", "flat", "compound", "appos"}


# ---------------------------------------------------------------- разбор

class Parsed:
    """Предложение в удобном виде: токены (upos/deprel/head/offset) + дерево составляющих.

    В Stanza 1.15 id токена — КОРТЕЖ: (1,) для обычного слова, (3,4) для MWT («im»).
    Поэтому строим явные карты: токен -> слово и слово -> токен.
    """

    def __init__(self, sent):
        self.sent = sent
        self.text = sent.text
        self.const = sent.constituency if hasattr(sent, "constituency") else None
        toks = list(sent.tokens)
        tok_ids = [(t.id if isinstance(t.id, tuple) else (t.id,)) for t in toks]
        tok_of_word = {}
        for i, ids in enumerate(tok_ids):
            for wid in ids:
                tok_of_word.setdefault(wid, i)
        byid = {w.id: w for w in sent.words if not isinstance(w.id, tuple)}

        self.tokens = []
        head_ids = []
        for i, t in enumerate(toks):
            w = byid.get(tok_ids[i][0])
            upos = w.upos if w is not None else ""
            deprel = w.deprel if w is not None else ""
            h = w.head if w is not None else 0
            head_ids.append(h)
            self.tokens.append((t.text, upos, deprel, h, t.start_char, t.end_char,
                                upos != "PUNCT"))
        self.n = len(self.tokens)
        self.tok_of_word = tok_of_word
        self.heads_tok = [tok_of_word.get(h, -1) for h in head_ids]
        self.upos = [x[1] for x in self.tokens]
        self.deprel = [x[2] for x in self.tokens]
        self.head = [x[3] for x in self.tokens]
        self.lex = [x[6] for x in self.tokens]
        self.lexpref = [0]
        for f in self.lex:
            self.lexpref.append(self.lexpref[-1] + (1 if f else 0))

    # -- сериализация (кэш разборов: Stanza считается один раз на набор)

    @classmethod
    def from_dict(cls, d):
        obj = cls.__new__(cls)
        obj.sent = None
        obj.const = None
        obj.tok_of_word = {}
        obj.text = d["text"]
        obj.tokens = [tuple(t) for t in d["tokens"]]
        obj.n = len(obj.tokens)
        obj.heads_tok = list(d["heads_tok"])
        obj.upos = [x[1] for x in obj.tokens]
        obj.deprel = [x[2] for x in obj.tokens]
        obj.head = [x[3] for x in obj.tokens]
        obj.lex = [x[6] for x in obj.tokens]
        obj.lexpref = [0]
        for f in obj.lex:
            obj.lexpref.append(obj.lexpref[-1] + (1 if f else 0))
        return obj

    def to_dict(self):
        return {"text": self.text, "tokens": [list(t) for t in self.tokens],
                "heads_tok": list(self.heads_tok)}

    def syllables(self):
        """слогов в каждом токене (pyphen, de_DE); ленивый кэш."""
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

    def lex_count(self, a, b):
        """лексических слов в токенах [a, b) (0-based, b не включается)."""
        return self.lexpref[b] - self.lexpref[a]

    def forbidden_after_funcword(self):
        """позиции i, где резать нельзя: слева служебное слово (Q4)."""
        return {i for i in range(1, self.n) if self.upos[i - 1] in FUNC_UPOS}

    def forbidden_base(self):
        """Механика, не зависящая от вкуса: не резать перед знаком препинания,
        не резать внутри дефисного слова, не резать после открывающей кавычки."""
        bad = set()
        for i in range(1, self.n):
            if self.upos[i] == "PUNCT":
                bad.add(i)                     # пунктуация приклеена к левому блоку (P2)
            if self.tokens[i - 1][0].endswith("-") or self.tokens[i][0].startswith("-"):
                bad.add(i)                     # внутри дефисного слова/цепочки
            if self.tokens[i - 1][0] in ("„", "«", "“", "”", '"'):
                bad.add(i)                     # открывающая кавычка -> к следующему слову
        return bad

    def penalty_positions(self):
        """Позиции для МЯГКИХ штрафов (заказчик: «запреты + штрафы»).

        Возвращает dict: имя штрафа -> множество позиций.
          np_inner   — рез между NOUN и его NP-зависимым (генитив/прилагательное/PP-модификатор)
          before_aux — рез непосредственно ПЕРЕД вспомогательным глаголом (ist/hat/wird …)
          subj_verb  — рез между подлежащим-местоимением и его сказуемым
        """
        out = {"np_inner": set(), "before_aux": set(), "subj_verb": set()}
        for i in range(1, self.n):
            l, r = i - 1, i
            # NP-внутренний рез: один из соседей — NP-зависимое другого
            if self.deprel[r] in NP_INNER and self.heads_tok[r] == l:
                out["np_inner"].add(i)
            if self.deprel[l] in NP_INNER and self.heads_tok[l] == r:
                out["np_inner"].add(i)
            if self.upos[r] in ("AUX",):
                out["before_aux"].add(i)
            if self.upos[l] == "PRON" and self.deprel[l] in ("nsubj", "nsubj:pass") and self.heads_tok[l] == r:
                out["subj_verb"].add(i)
        return out

    def pp_inner_positions(self):
        """позиции реза СТРОГО внутри предложной группы (ADP + head-NP)."""
        children = {}
        for idx, dep in enumerate(self.deprel):
            h = self.heads_tok[idx]
            if h >= 0:
                children.setdefault(h, []).append(idx)
        bad = set()
        for idx, (dep, up) in enumerate(zip(self.deprel, self.upos)):
            if dep != "case" or up != "ADP":
                continue
            h = self.heads_tok[idx]
            if h < 0:
                continue
            members = {idx, h}
            stack = [h]
            while stack:
                cur = stack.pop()
                for ch in children.get(cur, []):
                    if self.deprel[ch] in NP_INNER:
                        members.add(ch)
                        stack.append(ch)
            lo, hi = min(members), max(members)
            for p2 in range(lo + 1, hi + 1):
                bad.add(p2)
        return bad


# ---------------------------------------------------------------- запреты V4 (общие)

ATTACHED_PUNCT = {",", ".", "!", "?", ";", ":", "\u2026"}   # приклеены к левому блоку


def base_forbidden_v4(p, punct_v2=False):
    """Механика. punct_v2=True: резать перед «(», «–», «„» МОЖНО (так делает заказчик).

    Алгоритму выгоднее punct_v2=False (F1 0.777 против 0.749) — так и стоит в config.json.
    """
    bad = set()
    for i in range(1, p.n):
        tok = p.tokens[i][0]
        if p.upos[i] == "PUNCT" and (not punct_v2 or tok in ATTACHED_PUNCT):
            bad.add(i)
        if p.tokens[i - 1][0].endswith("-") and not p.tokens[i][0].startswith("("):
            bad.add(i)
        if p.tokens[i - 1][0] in ("\u201e", "\u00ab", "\u201c", '"'):
            bad.add(i)
    return bad


def pp_spans(p, np_inner=None):
    """PP: (strict, ppmod).

    strict — рез между предлогом и его существительным («in | seiner Firma») — запрет;
    ppmod  — рез между существительным и его предложным определением
             («zur Bezeichnung | neben …») — заказчик так режет в 17.7% случаев,
             поэтому НЕ запрет, а мягкий штраф.
    """
    np_inner = np_inner or NP_INNER
    children = {}
    for idx, h in enumerate(p.heads_tok):
        if h >= 0:
            children.setdefault(h, []).append(idx)
    strict, broad = set(), set()
    for idx, (dep, up) in enumerate(zip(p.deprel, p.upos)):
        if dep != "case" or up != "ADP":
            continue
        h = p.heads_tok[idx]
        if h < 0:
            continue
        s_members = {idx, h}
        b_members = set(s_members)
        stack = [h]
        while stack:
            cur = stack.pop()
            for ch in children.get(cur, []):
                if p.deprel[ch] in np_inner:
                    b_members.add(ch)
                    stack.append(ch)
        lo, hi = min(s_members), max(s_members)
        strict.update(range(lo + 1, hi + 1))
        lo, hi = min(b_members), max(b_members)
        broad.update(range(lo + 1, hi + 1))
    return strict, broad - strict


def constraint_chain(p, mode="strict", punct_v2=False, q4=True):
    """Уровни отката для dp_try: все запреты -> механика+Q4 -> только Q3 -> ничего.

    mode: "strict" (как в config.json) | "broad" (старая трактовка) | "off".
    """
    base = base_forbidden_v4(p, punct_v2)
    if q4:
        base = base | p.forbidden_after_funcword()
    strict, ppmod = pp_spans(p)
    if mode == "off":
        return [base]
    pp = strict if mode == "strict" else strict | ppmod
    return [base | pp, base, pp]


def score_with_pen(scores, p, pen):
    """Мягкие штрафы. Ключ "ppmod" — рез на границе PP-определения (см. pp_spans)."""
    if not pen:
        return scores
    sc = list(scores)
    pos = dict(p.penalty_positions())
    if "ppmod" in pen:
        pos["ppmod"] = pp_spans(p)[1]
    for name, w in pen.items():
        for i in pos.get(name, ()):
            if 0 <= i < len(sc):
                sc[i] -= w
    return sc


def enforce(bounds, p, params):
    """2..cap лексических слов: длинные разрезать, короткие слить."""
    min_lex, cap = params["min_lex"], params["cap"]
    allow1 = params.get("allow_one_word_final", False)
    bounds = sorted(set(bounds))
    for _ in range(50):
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
        changed = False
        for k in range(len(bounds) - 1):
            if p.lex_count(bounds[k], bounds[k + 1]) < min_lex:
                if allow1 and bounds[k + 1] == p.n and p.lex_count(bounds[k], bounds[k + 1]) == 1:
                    continue
                del bounds[k if k > 0 else k + 1]
                changed = True
                break
        if not changed and len(bounds) > 1 and p.lex_count(bounds[-2], bounds[-1]) < min_lex:
            if not (allow1 and p.lex_count(bounds[-2], bounds[-1]) == 1):
                bounds = bounds[:-2] + [bounds[-1]]
                changed = True
        if not changed:
            break
    return bounds


def build_parse(sentence, nlp):
    doc = nlp(sentence)
    return Parsed(doc.sentences[0]) if doc.sentences else None


# ---------------------------------------------------------------- DP

def dp_segment(scores, p, min_lex=2, ideal=4.0, cap=7, w_len=1.0, forbidden=frozenset(),
               allow_short_whole=True, _relaxed=False, syl_max_words=None, syl_from=7,
               allow_one_word_final=False):
    """Возвращает список границ [0, c1, ..., n] (индексы токенов).

    scores[i] — сила границы перед токеном i (1..n-1).
    Длина и ограничения считаются в ЛЕКСИЧЕСКИХ словах (как в правиле).
    """
    n = p.n
    NEG = float("-inf")
    best = [NEG] * (n + 1)
    prev = [-1] * (n + 1)
    best[0] = 0.0
    for end in range(1, n + 1):
        for start in range(max(0, end - 60), end):
            if best[start] == NEG:
                continue
            lc = p.lex_count(start, end)
            is_last = (end == n)
            if start > 0:
                if lc < min_lex and not (allow_one_word_final and end == n and lc == 1
                                         and p.upos[start] in ("VERB", "AUX")):
                    continue
                if start in forbidden:
                    continue
            if lc > cap:
                continue
            if syl_max_words and lc > syl_max_words and p.max_syl(start, end) >= syl_from:
                continue
            if start == 0 and end == n and allow_short_whole:
                pass  # всё предложение одним блоком — short-sentence exception
            cand = best[start] - w_len * abs(ideal - float(max(lc, 1)))
            if start > 0:
                cand += scores[start] if start < len(scores) else 0.0
            if cand > best[end]:
                best[end] = cand
                prev[end] = start
    if best[n] == NEG:
        if forbidden and not _relaxed:
            # ограничения несовместимы с предложением (напр. длинная группа без легальных резов)
            return dp_segment(scores, p, min_lex=min_lex, ideal=ideal, cap=cap, w_len=w_len,
                              forbidden=frozenset(), allow_short_whole=allow_short_whole,
                              _relaxed=True)
        return [0, n]
    bounds, cur = [n], n
    while cur > 0:
        cur = prev[cur]
        if cur < 0:
            return [0, n]
        bounds.append(cur)
    return sorted(bounds)


def dp_segment_mean(scores, p, min_lex=2, ideal=4.0, cap=7, w_len=1.0, forbidden=frozenset(),
                    syl_max_words=None, syl_from=7, allow_one_word_final=False):
    """То же, что dp_segment, но цель — СРЕДНЯЯ оценка блока (не сумма).

    Максимизируем (Σ score − w·Σ|ideal−len|) / k, где k — число блоков.
    Это естественно мешает «резать везде» на длинных предложениях.
    """
    n = p.n
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
                lc = p.lex_count(start, end)
                if start > 0:
                    if lc < min_lex and not (allow_one_word_final and end == n and lc == 1
                                             and p.upos[start] in ("VERB", "AUX")):
                        continue
                    if start in forbidden:
                        continue
                if lc > cap:
                    continue
                if syl_max_words and lc > syl_max_words and p.max_syl(start, end) >= syl_from:
                    continue
                cand = best[start][k - 1] - w_len * abs(ideal - float(max(lc, 1)))
                if start > 0:
                    cand += scores[start] if start < len(scores) else 0.0
                if cand > best[end][k]:
                    best[end][k] = cand
                    prev[end][k] = start
    best_k, best_v = None, NEG
    for k in range(1, KMAX + 1):
        if best[n][k] == NEG:
            continue
        v = best[n][k] / k
        if v > best_v:
            best_v, best_k = v, k
    if best_k is None:
        return [0, n]
    bounds, cur, k = [n], n, best_k
    while cur > 0:
        cur = prev[cur][k]
        if cur < 0:
            return [0, n]
        bounds.append(cur)
        k -= 1
    return sorted(bounds)


def apply_penalties(scores, p, weights):
    """Мягкие штрафы: вычитаем вес из оценки в «плохих» позициях.

    weights: {"np_inner": w, "before_aux": w, "subj_verb": w}
    """
    if not weights:
        return scores
    pos = p.penalty_positions()
    out = list(scores)
    for name, w in weights.items():
        for i in pos.get(name, ()):
            if 0 <= i < len(out):
                out[i] = out[i] - w
    return out


def dp_try(scores, p, params, forbidden_sets):
    """Пробуем ограничения по очереди (все -> только Q4 -> без ограничений).

    Возвращает (bounds, level): level=0 все, 1 только первое множество, 2 без ограничений.
    """
    obj = params.get("objective", "sum")
    last = [0, p.n]
    for level, fset in enumerate(forbidden_sets + [frozenset()]):
        b = (dp_segment_mean if obj == "mean" else dp_segment)(
            scores, p, min_lex=params["min_lex"], ideal=params["ideal"],
            cap=params["cap"], w_len=params["w_len"], forbidden=fset,
            syl_max_words=params.get("syl_max_words"), syl_from=params.get("syl_from", 7),
            allow_one_word_final=params.get("allow_one_word_final", False))
        last = (b, level)
        if sum(1 for a, c in zip(b[:-1], b[1:]) if p.lex_count(a, c) > params["cap"]) == 0 and len(b) > 1:
            return b, level
    return last


def bounds_to_blocks(p, bounds):
    out = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b > a and p.tokens[a][4] is not None and p.tokens[b - 1][5] is not None:
            out.append(p.text[p.tokens[a][4]:p.tokens[b - 1][5]].strip())
        else:
            out.append(" ".join(t[0] for t in p.tokens[a:b]))
    return out


# ---------------------------------------------------------------- эталон и метрики

def truth_cuts(sentence, blocks, p):
    """Индексы токенов, с которых начинается каждый человеческий блок (кроме первого)."""
    cuts, pos = set(), 0
    for b in blocks[:-1]:
        pos += len(b) + 1
        cut_char = pos - 1
        idx = next((i for i, t in enumerate(p.tokens)
                    if t[4] is not None and t[4] >= cut_char), None)
        if idx is not None:
            cuts.add(idx)
    return cuts


def load_corpus():
    return [json.loads(l) for l in open(CORPUS, encoding="utf-8") if l.strip()]


def load_heldout():
    """150 предложений. Если появилась разметка заказчика (annotations.jsonl),
    подставляем блоки -> прогон автоматически становится оценочным, а не слепым."""
    return [json.loads(l) for l in open(HELDOUT, encoding="utf-8") if l.strip()]


def score_metrics(pairs):
    """pairs: [(pred_set, truth_set)] -> exact, P, R, F1."""
    exact = tp = fp = fn = 0
    for pred, truth in pairs:
        exact += (pred == truth)
        tp += len(pred & truth)
        fp += len(pred - truth)
        fn += len(truth - pred)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"exact": exact, "n": len(pairs), "P": round(prec, 3),
            "R": round(rec, 3), "F1": round(f1, 3)}


def block_stats(p, bounds):
    """Статистика блоков: длины (в словах), нарушения запретов V4."""
    lens, func_end, pp_strict, ppmod, punct = [], 0, 0, 0, 0
    strict, mod = pp_spans(p)
    func_bad = p.forbidden_after_funcword()
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b <= a:
            continue
        lens.append(p.lex_count(a, b))
        if a > 0 and a in func_bad:
            func_end += 1
        if a > 0 and a in strict:
            pp_strict += 1
        if a > 0 and a in mod:
            ppmod += 1
        if a > 0 and p.upos[a] == "PUNCT" and p.tokens[a][0] in ATTACHED_PUNCT:
            punct += 1
    return {"lens": lens, "func_end": func_end, "pp_strict": pp_strict,
            "ppmod": ppmod, "punct": punct, "nblocks": len(lens)}


def now():
    return time.perf_counter()
