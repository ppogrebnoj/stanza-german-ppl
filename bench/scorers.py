# -*- coding: utf-8 -*-
"""Оценки границ: по одной функции на алгоритм.

Каждая функция: parsed -> список score длины n+1 (score[i] = сила границы перед токеном i),
score[0] и score[n] не используются. Диапазон не важен (DP сравнивает суммы),
но для гибридов всё нормируется в 0..1.
"""
import math
import re

import numpy as np


# ------------------------------------------------------------ общие утилиты

def _token_heads(p):
    """head на уровне ПОВЕРХНОСТНЫХ токенов (уже посчитано в Parsed)."""
    return p.heads_tok


def _norm(v):
    v = [float(x) for x in v]
    lo, hi = min(v), max(v)
    if hi - lo < 1e-9:
        return [0.0] * len(v)
    return [(x - lo) / (hi - lo) for x in v]


def _candidate_positions(p):
    """позиции, где есть хотя бы 1 слово слева и справа (по лексическим словам)."""
    out = []
    for i in range(1, p.n):
        if p.lex_count(0, i) >= 1 and p.lex_count(i, p.n) >= 1:
            out.append(i)
    return out


# ------------------------------------------------------------ S1: LCA по зависимостям

def _lca_dist(heads, a, b):
    anc, cur, d = {}, a, 0
    while cur >= 0:
        anc.setdefault(cur, d)
        cur = heads[cur]
        d += 1
    cur, d = b, 0
    while cur >= 0:
        if cur in anc:
            return anc[cur] + d
        cur = heads[cur]
        d += 1
    return 99


def s1_lca_dep(p):
    heads = _token_heads(p)
    sc = [0.0] * (p.n + 1)
    for i in _candidate_positions(p):
        d = _lca_dist(heads, i - 1, i)
        sc[i] = d / (1.0 + d)
    return _norm_keep_zero(sc)


def _norm_keep_zero(sc):
    """нормируем только ненулевые позиции, сохраняя 0 в неиспользуемых."""
    idx = [i for i, v in enumerate(sc) if v > 0]
    if not idx:
        return sc
    vals = _norm([sc[i] for i in idx])
    out = [0.0] * len(sc)
    for j, i in enumerate(idx):
        out[i] = vals[j]
    return out


# ------------------------------------------------------------ дерево составляющих

def _leaves_and_parents(tree):
    leaves, parent, order = [], {}, []
    stack = [(tree, None)]
    while stack:
        node, par = stack.pop()
        order.append(node)
        parent[id(node)] = par
        for ch in reversed(getattr(node, "children", []) or []):
            stack.append((ch, node))
    for node in order:
        if not getattr(node, "children", None):
            leaves.append(node)
    return leaves, parent


def _lca_dist_nodes(a, b, parent):
    anc, cur, d = {}, a, 0
    while cur is not None:
        anc[id(cur)] = d
        cur = parent.get(id(cur))
        d += 1
    cur, d = b, 0
    while cur is not None:
        if id(cur) in anc:
            return anc[id(cur)] + d
        cur = parent.get(id(cur))
        d += 1
    return 99


def _const_aligned(p):
    if p.const is None:
        return None
    leaves, parent = _leaves_and_parents(p.const)
    if len(leaves) != p.n:
        return None
    return leaves, parent


def s2_constituency(p):
    al = _const_aligned(p)
    if al is None:
        return None
    leaves, parent = al
    sc = [0.0] * (p.n + 1)
    for i in _candidate_positions(p):
        d = _lca_dist_nodes(leaves[i - 1], leaves[i], parent)
        sc[i] = d / (1.0 + d)
    return _norm_keep_zero(sc)


# ------------------------------------------------------------ S3: тип составляющей

LABEL_W = {"S": 1.0, "SBAR": 1.0, "CS": 1.0, "VP": 0.9, "CO": 0.9, "PP": 0.8,
           "ADVP": 0.6, "NP": 0.45, "AP": 0.4, "ADJP": 0.4}


def _label_weight(label):
    lab = re.sub(r"[-_].*$", "", str(label)).upper()
    if lab in LABEL_W:
        return LABEL_W[lab]
    for k, v in LABEL_W.items():
        if str(label).upper().startswith(k):
            return v
    return 0.3


def s3_const_type(p):
    al = _const_aligned(p)
    if al is None:
        return None
    leaves, parent = al
    # span каждого нетерминального узла в индексах листьев
    spans = {}

    def collect(node):
        ch = getattr(node, "children", []) or []
        if not ch:
            return (leaves.index(node), leaves.index(node))
        lo, hi = None, None
        for c in ch:
            a, b = collect(c)
            lo = a if lo is None else min(lo, a)
            hi = b if hi is None else max(hi, b)
        spans[id(node)] = (lo, hi, getattr(node, "label", ""))
        return lo, hi

    collect(p.const)
    sc = [0.0] * (p.n + 1)
    for i in _candidate_positions(p):
        launch = max([_label_weight(lab) for (a, b, lab) in spans.values() if a == i and b > a] or [0.0])
        close = max([_label_weight(lab) for (a, b, lab) in spans.values() if b == i - 1 and b > a] or [0.0])
        sc[i] = 0.5 * (launch + close)
    return _norm_keep_zero(sc)


# ------------------------------------------------------------ S4: гибрид S1+S2

def s4_hybrid(p):
    a = s1_lca_dep(p)
    b = s2_constituency(p)
    if b is None:
        return a
    return [(x + y) / 2.0 for x, y in zip(a, b)]


# ------------------------------------------------------------ S6: TextTiling (эмбеддинги)

_EMB = {}


def _embedder():
    if "m" not in _EMB:
        from sentence_transformers import SentenceTransformer
        _EMB["m"] = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _EMB["m"]


def s6_texttiling(p, window=5):
    model = _embedder()
    text = [t[0] for t in p.tokens]
    pos = _candidate_positions(p)
    lefts = [" ".join(text[max(0, i - window):i]) for i in pos]
    rights = [" ".join(text[i:min(p.n, i + window)]) for i in pos]
    if not pos:
        return [0.0] * (p.n + 1)
    embs = model.encode(lefts + rights, normalize_embeddings=True, show_progress_bar=False)
    k = len(pos)
    sc = [0.0] * (p.n + 1)
    for j, i in enumerate(pos):
        sim = float(np.dot(embs[j], embs[k + j]))
        sc[i] = max(0.0, 1.0 - sim)
    return _norm_keep_zero(sc)


# ------------------------------------------------------------ S7: MLM-пунктуация

_MLM = {}
PUNCT_TOKENS = [",", ".", ";", ":", "!", "?", "\u2013", "\u2014"]


def _mlm(name="bert-base-multilingual-cased"):
    if name not in _MLM:
        from transformers import AutoModelForMaskedLM, AutoTokenizer
        try:
            tok = AutoTokenizer.from_pretrained(name, use_fast=False)
        except Exception:
            tok = AutoTokenizer.from_pretrained(name)
        mdl = AutoModelForMaskedLM.from_pretrained(name)
        mdl.eval()
        _MLM[name] = (tok, mdl)
    return _MLM[name]


def _mlm_scores(p, name, marks):
    import torch
    tok, mdl = _mlm(name)
    text = [t[0] for t in p.tokens]
    pos = _candidate_positions(p)
    sc = [0.0] * (p.n + 1)
    if not pos:
        return sc
    ids = [i for i in (tok.convert_tokens_to_ids(m) for m in marks)
           if isinstance(i, int) and i >= 0]
    batch = [" ".join(text[:i]) + " [MASK] " + " ".join(text[i:]) for i in pos]
    enc = tok(batch, return_tensors="pt", padding=True, truncation=True, max_length=256)
    with torch.no_grad():
        logits = mdl(**enc).logits
    probs = torch.softmax(logits, dim=-1)
    mask_id = tok.mask_token_id
    for row, i in enumerate(pos):
        nz = (enc["input_ids"][row] == mask_id).nonzero()
        if len(nz) == 0:
            continue
        sc[i] = float(probs[row, int(nz[0]), ids].sum())
    return _norm_keep_zero(sc)


def s7_mlm(p):
    return _mlm_scores(p, "bert-base-multilingual-cased", PUNCT_TOKENS)


def s8_mlm_de(p):
    return _mlm_scores(p, "dbmdz/bert-base-german-cased", PUNCT_TOKENS)


def s9_mlm_de_comma(p):
    return _mlm_scores(p, "dbmdz/bert-base-german-cased", [","])


def s10_mlm_de_mid(p):
    return _mlm_scores(p, "dbmdz/bert-base-german-cased", [",", ";", ":", "–"])


def s11_mlm_mbert_comma(p):
    return _mlm_scores(p, "bert-base-multilingual-cased", [","])


DIRECT = {}   # прямых алгоритмов нет: старый rule.py (C1-C14) выведен из проекта

def _mix(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return [(x + y) / 2.0 for x, y in zip(a, b)]


def s12_const_plus_mlm(p):
    return _mix(s2_constituency(p), s11_mlm_mbert_comma(p))


def s13_const_plus_mlm_all(p):
    return _mix(s2_constituency(p), s7_mlm(p))


SCORERS = {
    "S1": ("LCA по дереву зависимостей (subtitle2go)", s1_lca_dep),
    "S2": ("расстояние по дереву составляющих (EMNLP-2024)", s2_constituency),
    "S3": ("тип составляющей на границе", s3_const_type),
    "S4": ("гибрид S1+S2", s4_hybrid),
    "S6": ("TextTiling: семантический провал (эмбеддинги)", s6_texttiling),
    "S7": ("MLM: «где была бы запятая» (mBERT, все знаки)", s7_mlm),
    "S8": ("MLM: «где была бы запятая» (нем. BERT, все знаки)", s8_mlm_de),
    "S9": ("MLM: только запятая (нем. BERT)", s9_mlm_de_comma),
    "S10": ("MLM: серединные знаки , ; : – (нем. BERT)", s10_mlm_de_mid),
    "S11": ("MLM: только запятая (mBERT)", s11_mlm_mbert_comma),
    "S12": ("гибрид: составляющие + MLM-запятая (mBERT)", s12_const_plus_mlm),
    "S13": ("гибрид: составляющие + MLM все знаки (mBERT)", s13_const_plus_mlm_all),
}
