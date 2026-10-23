#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rule.py — статичный детерминированный референс-интерпретатор RULE.md (v3) + config.

Правило = данные (config.json), алгоритмическая семантика = код интерпретатора.
Вход: текст одного предложения + config.

ДВА РЕЖИМЫ (важно для цикла PROTOCOL):
  * check()  = СУДЬЯ: verdict compliant/non_compliant/invalid_input по разбивке
               человека + подсказки (diagnosis.cuts / effects / hints).
               Ранжирование машины в verdict НЕ входит.
  * run()    = МНЕНИЕ МАШИНЫ: полный перебор §8 (recommended/admissible/rejected).
               Справочная секция machine_opinion в check(); отдельный вызов в CLI.

API:
  rule.py "sentence"                                  -> мнение машины (run)
  rule.py --check "sentence" --blocks "b1" "b2" ...    -> verdict + подсказки
  rule.py --check "sentence" --blocks ... --no-opinion -> то же без перебора (§8)
  rule.py --check ... --parse-file parse.json          -> судить по разбору parse_german
  rule.py --self-test | --determinism | --config-completeness

Только поля Stanza; детерминизм; parse-кэш по hash; model resources — локально offline.
"""

import hashlib
import json
import os
import re
import sys

MODEL_DIR = os.environ.get(
    "STANZA_MODEL_RESOURCES",
    r"C:/Users/BIGTER/AppData/Local/StanfordNLP/stanza/Cache/1.15.0/resources",
)
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
DEFAULT_STANZA_VERSION = "1.15.0"


# ============================ helpers =======================================
def _norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def _reconf_out():
    """Force UTF-8 stdout/stderr (Windows cp1251 default)."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def _hash_text(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def _wid(words):
    """Map word id -> word dict."""
    return {w["id"]: w for w in words}


# ============================ guards ==========================================
class TooManySeams(ValueError):
    """Перебор §8 = O(2^|S|). Без лимита один вызов может вешать процесс
    (|S|=16 -> ~21 c, |S|=18 -> ~91 c). Лимит — данные правила."""
    def __init__(self, k: int, limit: int):
        super().__init__(f"too many seam positions ({k} > max_seam_positions={limit})")
        self.k, self.limit = k, limit


# ============================ config =========================================
def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    validate_schema(cfg)
    return cfg


def _nested_keys(d):
    keys, stack = [], [d]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            keys.extend(x.keys())
            stack.extend(x.values())
    return keys


def validate_schema(cfg):
    """Строгая схема §9. Неизвестные ключи/операторы — ошибка."""
    required = {
        "version": str, "min": int, "pref": list, "cap": int,
        "terminal_set": list, "min_merge": dict, "seams": list,
        "nocut": list, "punct": dict, "seam_classes_status": dict,
        "rank": dict,
    }
    for k, t in required.items():
        if k not in cfg:
            raise ValueError(f"config missing {k!r}")
        if not isinstance(cfg[k], t):
            raise ValueError(f"config {k!r} type mismatch")

    mm = cfg["min_merge"]
    if set(mm.keys()) != {"prefer", "else", "tie"}:
        raise ValueError("min_merge keys fixed {prefer, else, tie}")
    if (mm["prefer"], mm["else"], mm["tie"]) != ("root_block", "fewer_lex_words", "left"):
        raise ValueError("min_merge values fixed")

    allowed_cond = {"deprel","chain","head","scope","min_left_lex","min_right_lex",
                    "after","next_token","root_xpos","xpos_or_lemma","xpos"}
    for item in cfg["seams"]:
        if "class_id" not in item or "status" not in item:
            raise ValueError("seam needs class_id,status")
        if item.get("condition") is not None:
            for k in _nested_keys(item["condition"]):
                if k not in allowed_cond:
                    raise ValueError(f"unknown seam condition {k!r}")

    allowed_nocut = {"id","deprel","to","with","nouns_xpos","atomic_chain",
                     "mwt","root_verb","pair","lemma_corr"}
    for item in cfg["nocut"]:
        if "id" not in item:
            raise ValueError("nocut needs id")
        for k in _nested_keys(item):
            if k not in allowed_nocut:
                raise ValueError(f"unknown nocut key {k!r}")

    p = cfg["punct"]
    if set(p.keys()) != {"P1","P2"}:
        raise ValueError("punct keys fixed P1,P2")
    for k in ("C1","C2","C3","C4","C5"):
        if k not in cfg["seam_classes_status"]:
            raise ValueError(f"seam_classes_status missing {k}")

    for k in ("max_seam_positions", "max_admissible"):
        if k in cfg:
            if not isinstance(cfg[k], int) or cfg[k] <= 0:
                raise ValueError(f"config {k!r} must be a positive int")
    if "max_seam_positions" in cfg and cfg["max_seam_positions"] > 20:
        raise ValueError("max_seam_positions > 20 даёт экспоненциальный перебор (>1e6 вариантов)")

    # rank: критерии ранжирования — данные правила (SPEC §3.8 + amendment)
    crit = cfg["rank"].get("criteria")
    if not isinstance(crit, list) or not crit:
        raise ValueError("rank.criteria must be a non-empty list")
    for item in crit:
        if set(item.keys()) != {"criterion", "direction"}:
            raise ValueError("rank.criteria item keys fixed {criterion,direction}")
        if item["criterion"] not in RANK_CRITERIA:
            raise ValueError(f"unknown rank criterion {item['criterion']!r}")
        if item["direction"] not in ("asc", "desc"):
            raise ValueError("rank direction must be asc|desc")
        if RANK_CRITERIA[item["criterion"]] == "d_tuple" and item["direction"] != "asc":
            raise ValueError("cut_positions supports only asc")


# ============================ parse + cache ==================================
_NLP = None

def _get_nlp():
    global _NLP
    if _NLP is None:
        import stanza  # noqa
        os.environ.setdefault("STANZA_RESOURCES_DIR", MODEL_DIR)
        os.environ.setdefault("STANZA_CACHE_DIR", CACHE_DIR)
        _NLP = stanza.Pipeline(
            lang="de", processors="tokenize,mwt,pos,lemma,depparse",
            dir=MODEL_DIR, download_method=None, verbose="ERROR",
        )
    return _NLP


def _normalize_words(raw_words):
    """Слова из любого формата -> внутренний (feats/deprel). Принимает и поля
    MCP parse_german (features/dep), и внутренние имена кэша (feats/deprel)."""
    out = []
    for w in raw_words:
        out.append({
            "id": int(w["id"]), "text": str(w["text"]),
            "lemma": str(w.get("lemma", "")),
            "upos": str(w.get("upos", "")), "xpos": str(w.get("xpos", "")),
            "feats": str(w.get("feats", w.get("features", ""))),
            "head": int(w["head"]),
            "deprel": str(w.get("deprel", w.get("dep", ""))),
        })
    return out


def _normalize_tokens(raw_tokens):
    out = []
    for i, t in enumerate(raw_tokens):
        out.append({
            "id": i + 1, "text": str(t["text"]),
            "start_char": t.get("start_char"), "end_char": t.get("end_char"),
            "is_mwt": bool(t.get("is_mwt", False)),
            "word_ids": [int(x) for x in t["word_ids"]],
        })
    return out


def _validate_parse(words, tokens):
    """Жёсткая сверка переданного разбора: номера слов, корень, покрытие токенов,
    offsets. Ошибки — явные, молча не терпим (SPEC §4)."""
    ids = sorted(w["id"] for w in words)
    if ids != list(range(1, len(ids) + 1)):
        raise ValueError("word ids must be contiguous 1..n")
    n = len(ids)
    roots = [w for w in words if w["head"] == 0]
    if len(roots) != 1:
        raise ValueError(f"expected exactly one root (head==0), got {len(roots)}")
    covered = []
    for t in tokens:
        covered.extend(t["word_ids"])
    if sorted(covered) != list(range(1, n + 1)):
        raise ValueError("tokens must cover every word id exactly once")
    if any(t["start_char"] is None or t["end_char"] is None for t in tokens):
        raise ValueError(
            "payload tokens lack start_char/end_char — MCP parse_german must provide "
            "them (SPEC §4); update server.py _sentence_tokens")


def normalize_parse(payload, expect_text=None):
    """Готовый разбор (вывод MCP parse_german, SPEC §4) -> (words, tokens, text).
    Форматы: {'sentences':[{'text','words','tokens'}]} | {'words','tokens','sentence_text'}.
    Поля слов: features/dep (MCP) или feats/deprel (внутренние)."""
    if isinstance(payload, dict) and "sentences" in payload:
        sents = payload["sentences"]
        if len(sents) != 1:
            raise ValueError(f"expected one sentence in payload, got {len(sents)}")
        s = sents[0]
        words = _normalize_words(s["words"])
        tokens = _normalize_tokens(s["tokens"])
        text = s.get("text")
    elif isinstance(payload, dict) and "words" in payload and "tokens" in payload:
        words = _normalize_words(payload["words"])
        tokens = _normalize_tokens(payload["tokens"])
        text = payload.get("sentence_text")
    else:
        raise ValueError("expected parse payload with 'sentences' or 'words'+'tokens'")
    _validate_parse(words, tokens)
    if expect_text is not None and text and _norm(text) != _norm(expect_text):
        raise ValueError(f"payload sentence text != checked sentence: {text!r} vs {expect_text!r}")
    return words, tokens, text


def parse_sentence(text, parsed=None):
    """-> (words, tokens, source). source: 'mcp-payload' | 'parse-cache' | 'stanza'.

    SPEC §4: судья должен оперировать тем же разбором, что и LLM. Если передан
    parsed (вывод parse_german) — внутренний пере-парсинг Stanza НЕ выполняется.
    Без parsed — локальный Stanza + parse-кэш по hash (как раньше)."""
    if not text or not text.strip() or len(text.split()) == 0:
        raise ValueError("expected exactly one sentence")

    if parsed is not None:
        if isinstance(parsed, (tuple, list)) and len(parsed) == 2:
            # уже нормализованный (words, tokens) — повторное использование разбора
            words, tokens = _normalize_words(parsed[0]), _normalize_tokens(parsed[1])
            _validate_parse(words, tokens)
            return words, tokens, "reused-parse"
        words, tokens, _ = normalize_parse(parsed, expect_text=text)
        return words, tokens, "mcp-payload"

    ck = _hash_text(text)
    cpath = os.path.join(CACHE_DIR, "parse_cache.jsonl")
    if os.path.exists(cpath):
        with open(cpath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if (rec.get("text_hash") == ck and
                        rec.get("stanza_version") == DEFAULT_STANZA_VERSION):
                    return rec["words"], rec["tokens"], "parse-cache"

    nlp = _get_nlp()
    doc = nlp(text)
    if len(doc.sentences) != 1:
        raise ValueError(f"expected one sentence, got {len(doc.sentences)}")
    sent = doc.sentences[0]
    words_list = []
    for w in sent.words:
        words_list.append({
            "id": int(w.id), "text": str(w.text), "lemma": str(w.lemma),
            "upos": str(w.upos), "xpos": str(w.xpos), "feats": str(w.feats),
            "head": int(w.head), "deprel": str(w.deprel),
        })
    tokens_list = []
    for t in sent.tokens:
        wids = [int(w.id) for w in t.words]
        tokens_list.append({
            "id": len(tokens_list) + 1, "text": str(t.text),
            "start_char": int(t.start_char), "end_char": int(t.end_char),
            "is_mwt": bool(t.is_mwt()), "word_ids": wids,
        })
    _validate_parse(words_list, tokens_list)
    os.makedirs(CACHE_DIR, exist_ok=True)
    rec = {"text_hash": ck, "stanza_version": DEFAULT_STANZA_VERSION,
           "words": words_list, "tokens": tokens_list, "sentence_text": text}
    with open(cpath, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return words_list, tokens_list, "stanza"


# ============================ rank criteria (данные, не код) ================
# SPEC §3.8 задаёт 4 критерия; порядок и направления — В config.json (rank.criteria),
# чтобы любое участие «больше швов = лучше» было видно как часть правила.
RANK_CRITERIA = {
    "blocks_not_in_pref": "a_cnt",
    "min_merges": "merges",
    "units_preserved": "c_cnt",
    "cuts_count": "n_cuts",
    "cut_positions": "d_tuple",
}


def rank_criteria(cfg):
    """Читает cfg['rank']['criteria'] -> [(ctx_key, direction)]. Схема жёсткая."""
    crit = cfg["rank"]["criteria"]
    out = []
    for item in crit:
        name, direction = item["criterion"], item["direction"]
        if name not in RANK_CRITERIA:
            raise ValueError(f"unknown rank criterion {name!r}")
        if direction not in ("asc", "desc"):
            raise ValueError(f"rank criterion {name!r}: direction must be asc|desc")
        if RANK_CRITERIA[name] == "d_tuple" and direction != "asc":
            raise ValueError("cut_positions supports only asc")
        out.append((RANK_CRITERIA[name], direction))
    return out


def rank_key(ctx, criteria):
    """Детерминированный ключ сортировки из ctx по объявленным критериям."""
    key = []
    for ctx_key, direction in criteria:
        v = ctx[ctx_key]
        if isinstance(v, tuple):
            key.append(v)
        else:
            key.append(v if direction == "asc" else -v)
    return tuple(key)


def rank_ctx(a_cnt, merges, c_cnt, final_cuts):
    return {"a_cnt": a_cnt, "merges": merges, "c_cnt": c_cnt,
            "n_cuts": len(final_cuts), "d_tuple": tuple(sorted(final_cuts))}


# ============================ units / seams / nocut / punct ===================
def build_units(words):
    """[min,max] subtree of each direct root dependent + root; sorted by start_id."""
    wid = _wid(words)
    n = max(w["id"] for w in words)
    root_id = next((w["id"] for w in words if w["head"] == 0), None)
    if root_id is None:
        raise ValueError("no root word")

    def span(start):
        mn = mx = start; stack = [start]
        while stack:
            cur = stack.pop()
            for x in wid.values():
                if x["head"] == cur:
                    mn = min(mn, x["id"]); mx = max(mx, x["id"]); stack.append(x["id"])
        return (mn, mx)

    units = [span(w["id"]) for w in words if w["head"] == root_id]
    units.append((root_id, root_id))
    units.sort(key=lambda u: u[0])
    return units


def compute_seams(words, tokens):
    """pos -> list classes (C1..C5). Legal cut positions only."""
    wid = _wid(words)
    n = max(w["id"] for w in words)
    seams = {}

    def add(p, cls):
        if p > 0 and p < n:
            seams.setdefault(p, []).append(cls)

    def lex_left(p):
        return sum(1 for t in tokens
                   if all(wid[x]["upos"] != "PUNCT" for x in t["word_ids"])
                   and max(t["word_ids"]) <= p)

    def lex_right(p):
        return sum(1 for t in tokens
                   if all(wid[x]["upos"] != "PUNCT" for x in t["word_ids"])
                   and min(t["word_ids"]) > p)

    root_id = next((w["id"] for w in words if w["head"] == 0), None)

    # C1 — after each unit's last word
    for (lo, hi) in build_units(words):
        add(hi, "C1")

    # C2 — before cc
    for w in words:
        if w["deprel"] == "cc":
            add(w["id"] - 1, "C2")

    # C3 — before whole PP chain (ADP + dependents) at head-NOUN nmod; >=3 lex both sides
    for w in words:
        if w["deprel"] == "nmod" and wid.get(w["head"], {}).get("upos") == "NOUN":
            mn = mx = w["id"]; st = [w["id"]]
            while st:
                cur = st.pop()
                for x in wid.values():
                    if x["head"] == cur:
                        mn = min(mn, x["id"]); mx = max(mx, x["id"]); st.append(x["id"])
            p = mn - 1   # cut before ADP (min word-id of chain)
            if lex_left(p) >= 3 and lex_right(p) >= 3:
                add(p, "C3")

    # C4 — after root VVFIN/VAFIN; next token deprel in {advmod,cc} AND xpos==KON OR lemma in {denn,dann,so}
    for w in words:
        if w["head"] == root_id and w["xpos"] in ("VVFIN", "VAFIN"):
            nxt = wid.get(w["id"] + 1)
            if nxt is None:
                continue
            if (nxt["deprel"] in ("advmod", "cc") and
                    (nxt["xpos"] == "KON" or nxt["lemma"] in ("denn", "dann", "so"))):
                add(w["id"], "C4")

    # C5 — before mark/KOUS; >=3 lex both sides
    for w in words:
        if w["deprel"] == "mark" and w["xpos"] == "KOUS":
            p = w["id"] - 1
            if lex_left(p) >= 3 and lex_right(p) >= 3:
                add(p, "C5")

    return seams


def compute_nocut(words):
    """pos -> list rule_ids. pos = cut AFTER word pos (between pos and pos+1).
    mwt added at token level by caller."""
    wid = _wid(words)
    out = {}
    def add(p, rid):
        if p > 0:
            out.setdefault(p, []).append(rid)

    def adj_pos(a, b):
        """cut position between adjacent word-ids a,b (after the smaller). None if not adjacent."""
        if a == b or abs(a - b) != 1:
            return None
        return min(a, b)

    det = {"det", "det:poss", "amod", "nummod", "compound", "flat", "appos"}
    for w in words:
        if (w["deprel"] in det and wid.get(w["head"], {}).get("upos") == "NOUN"):
            p = adj_pos(w["id"], w["head"])
            if p is not None:
                add(p, "det_to_noun")   # between d and head

    for w in words:
        if (w["deprel"] == "case" and wid.get(w["head"], {}).get("upos") == "NOUN"
                and w["head"] > 0 and wid[w["head"]]["deprel"] in ("pobj", "obl")):
            p = adj_pos(w["id"], w["head"])
            if p is not None:
                add(p, "case_obl")   # between c and head

    aux_deprels = {"aux", "aux:pass", "cop"}
    for w in words:
        if w["deprel"] in aux_deprels and w["head"] > 0:
            p = adj_pos(w["id"], w["head"])
            if p is not None:
                add(p, "aux_cop")   # between w and head

    for w in words:
        if w["upos"] == "NOUN" and w["xpos"] == "TRUNC":
            mn = mx = w["id"]; st = [w["id"]]
            while st:
                cur = st.pop()
                for x in wid.values():
                    if x["head"] == cur and x["deprel"] in ("cc", "conj") and x["upos"] == "NOUN":
                        mn = min(mn, x["id"]); mx = max(mx, x["id"]); st.append(x["id"])
            for p in range(mn, mx):
                add(p, "trunc_atomic_chain")   # between chain extremes

    root_verb_xpos = {"VAFIN", "VVFIN", "VVPP"}
    aux_deprels_root = {"aux", "aux:pass"}
    for w in words:
        if w["head"] == 0 and w["xpos"] in root_verb_xpos:
            lo = hi = w["id"]; st = [w["id"]]
            while st:
                cur = st.pop()
                for x in wid.values():
                    if x["head"] == cur and x["deprel"] in ("aux", "aux:pass"):
                        lo = min(lo, x["id"]); hi = max(hi, x["id"]); st.append(x["id"])
            for p in range(lo, hi):
                add(p, "root_aux")   # between root-verb and aux

    return out


def compute_p2(words, tokens, cfg):
    """pos -> list ['punct_p2'] (non-terminal) and ['punct_p1'] (terminal at end)."""
    terminal = set(cfg["terminal_set"])
    wid = _wid(words)
    out = {}
    def add(p, rid):
        if p > 0:
            out.setdefault(p, []).append(rid)

    for t in tokens:
        upos = wid.get(t["word_ids"][0], {}).get("upos", "")
        if upos == "PUNCT" and t["text"] not in terminal:
            add(min(t["word_ids"]) - 1, "punct_p2")

    lt = tokens[-1]
    upos = wid.get(lt["word_ids"][0], {}).get("upos", "")
    if upos == "PUNCT" and lt["text"] in terminal:
        add(min(lt["word_ids"]) - 1, "punct_p1")

    return out


# ============================ lex / block helpers ===========================
def _lex_count(words, tokens, a, b):
    """Number of lexical surface tokens with word_ids fully inside [a,b]. MWT counts as 1."""
    wid = _wid(words)
    c = 0
    for t in tokens:
        lo = min(t["word_ids"]); hi = max(t["word_ids"])
        if a <= lo and hi <= b and all(wid[x]["upos"] != "PUNCT" for x in t["word_ids"]):
            c += 1
    return c


def block_text(sentence, tokens, a, b):
    start = end = None
    for t in tokens:
        lo = min(t["word_ids"]); hi = max(t["word_ids"])
        if a <= lo and hi <= b:
            if start is None:
                start = t["start_char"]
            end = t["end_char"]
    return sentence[start:end] if start is not None else ""


def block_toks(words, a, b):
    return sorted(w["id"] for w in words if a <= w["id"] <= b)


# ============================ partition / min-merge ===========================
def _partition(n, cuts):
    """list of (a,b) word ranges from cut set."""
    if not cuts:
        return [(1, n)]
    cs = sorted(cuts)
    blocks = []
    prev = 1
    for c in cs:
        blocks.append((prev, c))
        prev = c + 1
    blocks.append((prev, n))
    return blocks


def min_merge(words, tokens, cfg, root_id, blocks):
    """§3.6 deterministic merge; returns (final_blocks, merge_count)."""
    final = list(blocks)
    merges = 0
    mn = cfg["min"]

    def lex(a, b):
        return _lex_count(words, tokens, a, b)

    def rootdep(a, b):
        return any(w["head"] == root_id and w["id"] != root_id for w in words if a <= w["id"] <= b)

    while len(final) > 1:
        changed = False
        i = 0
        while i < len(final):
            a, b = final[i]
            if lex(a, b) >= mn:
                i += 1
                continue
            lb = final[i - 1] if i > 0 else None
            rb = final[i + 1] if i + 1 < len(final) else None
            if rootdep(a, b):
                if lb and rb:
                    li, ri = lex(*lb), lex(*rb)
                    midx = (i - 1) if li <= ri else i + 1
                else:
                    midx = i - 1 if lb else i + 1
            else:
                if lb and rb:
                    li, ri = lex(*lb), lex(*rb)
                    midx = (i - 1) if li <= ri else i + 1
                else:
                    midx = i - 1 if lb else i + 1
            lo = min(a, final[midx][0])
            hi = max(b, final[midx][1])
            newfinal = []
            for idx, blk in enumerate(final):
                if idx == i or idx == midx:
                    continue
                newfinal.append(blk)
            pos = min(i, midx)
            newfinal.insert(pos, (lo, hi))
            final = newfinal
            merges += 1
            changed = True
            i = max(0, min(i, midx) - 1)
        if not changed:
            break
    return final, merges


# ============================ run (full pipeline) ===========================
def _units_preserved(cuts, units):
    return sum(1 for (lo, hi) in units if not any(lo <= p < hi for p in cuts))


def _build_output(sentence, words, tokens, n, seams, valid_variants):
    """Construct the §8 output from pipeline internals."""
    wid = _wid(words)

    def bobj(idx, x, y):
        return {"n": idx + 1,
                "text": block_text(sentence, tokens, x, y),
                "lex_words": _lex_count(words, tokens, x, y),
                "toks": block_toks(words, x, y),
                "seams": seams.get(y, []) if y < n else []}

    out = {"language": "de", "rule_version": None,
           "recommended": [], "admissible": [], "rejected": [],
           "seam_classes_status": {}}
    for rank_i, v in enumerate(valid_variants):
        bl = v["blocks"]
        objs = [bobj(i, x, y) for i, (x, y) in enumerate(bl)]
        if rank_i == 0:
            out["recommended"] = objs
        else:
            out["admissible"].append({"rank": rank_i + 1, "blocks": objs})
    return out


def run(sentence, cfg, parsed=None):
    """Full pipeline -> out dict (JSON-serializable). МНЕНИЕ МАШИНЫ (перебор §8).
    parsed — готовый разбор из MCP parse_german (SPEC §4): пере-парсинг не делается."""
    words, tokens, parse_source = parse_sentence(sentence, parsed)
    n = max(w["id"] for w in words)
    root_id = next((w["id"] for w in words if w["head"] == 0), -1)
    criteria = rank_criteria(cfg)

    seams = compute_seams(words, tokens)
    nocut = compute_nocut(words)
    for t in tokens:
        if len(t["word_ids"]) > 1:  # MWT: forbid cuts inside token's word-id range
            for p in range(min(t["word_ids"]), max(t["word_ids"])):
                nocut.setdefault(p, []).append("mwt")
    p2 = compute_p2(words, tokens, cfg)

    S = set()
    for p, _ in seams.items():
        if p not in nocut and p not in p2:
            S.add(p)

    positions = sorted(S)
    limit = int(cfg.get("max_seam_positions", 12))
    if len(positions) > limit:
        raise TooManySeams(len(positions), limit)
    units = build_units(words)
    pref_set = set(cfg["pref"])

    valid_variants = []   # {key, final_cuts, blocks}
    rejected_list = []    # {variant, violations}
    seen_valid = set()
    seen_rej = set()

    for mask in range(1 << len(positions)):
        cuts = set()
        for i, p in enumerate(positions):
            if mask & (1 << i):
                cuts.add(p)
        blocks = _partition(n, cuts)
        final, merges = min_merge(words, tokens, cfg, root_id, blocks)

        ok = True
        if len(final) > 1:
            for (x, y) in final:
                if _lex_count(words, tokens, x, y) < cfg["min"]:
                    ok = False
                    break

        cap_ok = all(_lex_count(words, tokens, x, y) <= cfg["cap"] for (x, y) in final)

        if not ok or not cap_ok:
            vkey = tuple(_norm(block_text(sentence, tokens, x, y)) for (x, y) in final)
            if vkey not in seen_rej:
                seen_rej.add(vkey)
                violations = []
                if not ok:
                    violations.append("min")
                if not cap_ok:
                    for (x, y) in final:
                        lc = _lex_count(words, tokens, x, y)
                        if lc > cfg["cap"]:
                            violations.append(f"cap>{cfg['cap']}({lc})")
                if violations:
                    rejected_list.append({
                        "variant": " | ".join(block_text(sentence, tokens, x, y) for (x, y) in final),
                        "violations": sorted(set(violations)),
                    })
        else:
            # valid; rank uses FINAL cuts (post min_merge)
            final_cuts = set()
            for (x, y) in final:
                if y < n:
                    final_cuts.add(y)
            a_cnt = sum(1 for (x, y) in final if _lex_count(words, tokens, x, y) not in pref_set)
            c_cnt = _units_preserved(final_cuts, units)
            # Ключ §3.8 собирается из cfg['rank']['criteria'] — направления и состав
            # критериев видны как ДАННЫЕ правила, а не как правка кода под прецедент.
            ctx = rank_ctx(a_cnt, merges, c_cnt, final_cuts)
            key = rank_key(ctx, criteria)
            vkey = tuple(_norm(block_text(sentence, tokens, x, y)) for (x, y) in final)
            if vkey not in seen_valid:
                seen_valid.add(vkey)
                valid_variants.append({"key": key, "final_cuts": final_cuts, "blocks": final})

    valid_variants.sort(key=lambda v: v["key"])
    out = _build_output(sentence, words, tokens, n, seams, valid_variants)
    out["rule_version"] = cfg["version"]
    out["seam_classes_status"] = dict(cfg["seam_classes_status"])
    out["parse_source"] = parse_source
    out["rank_criteria"] = [f"{c['criterion']}:{c['direction']}" for c in cfg["rank"]["criteria"]]
    return out


# ============================ check() ========================================
def _between(wid, pos):
    """'wpos | wpos+1' string for diagnosis."""
    a = wid.get(pos)
    b = wid.get(pos + 1)
    if a is not None and b is not None:
        return f"{a['text']} | {b['text']}"
    return "?"


# ============================ compliance (verdict) ===========================
# Подсказки для шага C (дельта). Формулируются ТОЛЬКО через поля Stanza и § RULE.md.
HINTS = {
    "det_to_noun": ("NO-CUT §4: det/det:poss/amod/nummod/compound/flat/appos нельзя отрывать "
                    "от своего NOUN. Легальный рез — по границе unit (C1), а не внутри группы."),
    "case_obl": ("NO-CUT §4: предлог (case) нельзя отрывать от своего NOUN в PP. Легальный рез — "
                 "ПЕРЕД ВСЕЙ PP-цепью целиком (C3), не перед её первым словом."),
    "aux_cop": ("NO-CUT §4: глагольная рамка — рез между словом и его head по aux/aux:pass/cop "
                "запрещён."),
    "root_aux": ("NO-CUT §4: рез между root-глаголом (VAFIN/VVFIN/VVPP) и его aux запрещён "
                 "(составные времена: 'gelesen haben')."),
    "trunc_atomic_chain": ("NO-CUT §4: цепочка NOUN с xpos=TRUNC, связанная cc/conj, атомарна — "
                           "рез внутри цепочки запрещён."),
    "mwt": ("NO-CUT §4: MWT неделим ('im' = 'in dem') — рез внутри диапазона Word-ID одного "
            "поверхностного токена запрещён."),
    "punct_p2": ("P2 §6: запятая/дефис/скобка приклеивается к ПРЕДШЕСТВУЮЩЕМУ блоку — рез "
                 "непосредственно перед знаком запрещён независимо от head."),
    "punct_p1": ("P1 §6: терминальные . ? ! входят в блок, содержащий последний токен предложения."),
    "missing": ("GAP: рез не покрыт ни одним C-классом C1..C5 и не запрещён. Это сигнал дельты: "
                "новый C-класс или расширение существующего по Stanza-признакам слова СПРАВА от "
                "границы (deprel/xpos/lemma/head/upos)."),
    "min": ("§7 min=3: блок короче min не проходит правило — по §7 он должен быть слит с соседним "
            "блоком. Это НЕ дыра правила: дельту по этому кейсу не готовить."),
    "cap": ("§7 cap=7: блок длиннее cap не проходит правило. Это НЕ дыра правила: дельту по "
            "этому кейсу не готовить."),
    "coverage": ("Блоки должны покрывать предложение целиком: без пропусков, пересечений и пустых "
                 "блоков. Проверь границы блоков по word-id."),
    "block_not_found": ("Текст блока НЕ найден в предложении. Это НЕ нарушение правила: перечитай "
                        "блок точно по тексту предложения (или укажи диапазоны word-id). Дельту "
                        "правила по такому кейсу готовить нельзя."),
}


def map_blocks(sentence, tokens, human_blocks):
    """Блоки человека -> диапазоны Word-ID. Детерминированный матчинг по
    поверхности предложения: текст кандидата = sentence[start_char..end_char] от
    токена i до токена j (PUNCT-токены Stanza не имеют пробела перед собой, поэтому
    склейка token.text пробелами НЕ годится). -> (ranges, not_found)."""
    ranges, not_found = [], []
    start = 0
    for hb in human_blocks:
        target = _norm(hb)
        found = None
        if target:
            for i in range(start, len(tokens)):
                si = tokens[i]["start_char"]
                for j in range(i, len(tokens)):
                    cand = _norm(sentence[si:tokens[j]["end_char"]])
                    if len(cand) >= len(target):
                        if cand == target:
                            found = (i, j)
                        break
                if found:
                    break
        if not found:
            ranges.append(None)
            not_found.append(hb)
            continue
        i, j = found
        ranges.append((min(tokens[i]["word_ids"]), max(tokens[j]["word_ids"])))
        start = j + 1
    return ranges, not_found


def evaluate_human(words, tokens, cfg, ranges, seams, nocut, p2, root_id):
    """Verdict-критерии §4-§7, применённые к разбивке человека. БЕЗ перебора и
    ранжирования. -> (cuts, violations, lex_per_block, short_sentence)."""
    n = max(w["id"] for w in words)
    cuts = [ranges[i][1] for i in range(len(ranges) - 1)]
    violations = []

    if ranges[0][0] != 1 or ranges[-1][1] != n:
        violations.append({"type": "coverage", "pos": None,
                           "detail": f"blocks must cover word 1..{n}"})
    for i in range(len(ranges) - 1):
        if ranges[i][1] + 1 != ranges[i + 1][0]:
            violations.append({"type": "coverage", "pos": ranges[i][1],
                               "detail": "gap/overlap between blocks"})

    for pos in cuts:
        if pos in nocut:
            violations.append({"type": "forbidden", "pos": pos,
                               "rule": sorted(set(nocut[pos]))[0]})
        elif pos in p2:
            violations.append({"type": "forbidden", "pos": pos, "rule": "punct_p2"})
        elif pos not in seams:
            violations.append({"type": "missing", "pos": pos})

    lex = [_lex_count(words, tokens, a, b) for a, b in ranges]
    total_lex = _lex_count(words, tokens, 1, n)
    short = total_lex < cfg["min"]
    if short and len(ranges) > 1:
        violations.append({"type": "min", "pos": None,
                           "detail": f"sentence has {total_lex} lex words < min={cfg['min']} "
                                     "-> single block (short-sentence exception)"})
    for (a, b), lc in zip(ranges, lex):
        if lc < cfg["min"] and not short:
            violations.append({"type": "min", "pos": b, "block": [a, b], "lex_words": lc})
    for (a, b), lc in zip(ranges, lex):
        if lc > cfg["cap"]:
            violations.append({"type": "cap", "pos": b, "block": [a, b], "lex_words": lc})

    return cuts, violations, lex, short


def _key_summary(words, tokens, cfg, ranges):
    """Составляющие ключа §3.8 для конкретной разбивки — чтобы объяснить ранг."""
    n = max(w["id"] for w in words)
    root_id = next((w["id"] for w in words if w["head"] == 0), -1)
    pref = set(cfg["pref"])
    cuts = {b for (a, b) in ranges if b < n}
    _, merges = min_merge(words, tokens, cfg, root_id, _partition(n, cuts))
    ctx = rank_ctx(sum(1 for (a, b) in ranges
                       if _lex_count(words, tokens, a, b) not in pref),
                   merges, _units_preserved(cuts, build_units(words)), cuts)
    return {
        "blocks": len(ranges),
        "blocks_not_in_pref": ctx["a_cnt"],
        "min_merges_required": ctx["merges"],
        "cuts": ctx["n_cuts"],
        "units_preserved": ctx["c_cnt"],
        "rank_key": list(rank_key(ctx, rank_criteria(cfg))),
        "lex_words": [_lex_count(words, tokens, a, b) for (a, b) in ranges],
    }


def check(sentence, human_blocks, cfg, with_opinion=True, parsed=None):
    """API §8.2 — СУДЬЯ. verdict = соответствие разбивки человека ПРАВИЛУ (§4-§7):
    резы покрыты C1..Cn и не на NO-CUT/P2, блоки проходят min/cap, покрытие полное.
    Ранжирование машины (§8 перебор) — справочное мнение, в verdict НЕ входит.
    parsed — разбор из MCP parse_german (SPEC §4): судья и LLM на одних Word-ID."""
    words, tokens, parse_source = parse_sentence(sentence, parsed)
    n = max(w["id"] for w in words)
    wid = _wid(words)
    root_id = next((w["id"] for w in words if w["head"] == 0), -1)

    seams = compute_seams(words, tokens)
    nocut = compute_nocut(words)
    for t in tokens:
        if len(t["word_ids"]) > 1:
            for p in range(min(t["word_ids"]), max(t["word_ids"])):
                nocut.setdefault(p, []).append("mwt")
    p2 = compute_p2(words, tokens, cfg)

    base = {"rule_version": cfg["version"], "config_hash": _canonical_hash(cfg),
            "parse_source": parse_source, "sentence": sentence}

    ranges, not_found = map_blocks(sentence, tokens, human_blocks)
    if not_found:
        return {**base, "verdict": "invalid_input", "match": False, "human_rank": None,
                "violations": [{"type": "block_not_found", "pos": None, "block": b}
                               for b in not_found],
                "diagnosis": {"cuts": [], "effects": {"min_merge": [], "cap": [], "rank": {}},
                              "coverage": {"covered": [], "missing": [], "forbidden": []},
                              "block_not_found": not_found,
                              "hints": [HINTS["block_not_found"]],
                              "delta_required": False},
                "machine_opinion": {"enabled": False}}

    cuts, violations, lex, short = evaluate_human(
        words, tokens, cfg, ranges, seams, nocut, p2, root_id)
    verdict = "compliant" if not violations else "non_compliant"

    # --- machine opinion: дорогой перебор §8, только по запросу (справочно) ---
    human_rank = None
    opinion = {"enabled": False}
    out = None
    if with_opinion:
        try:
            out = run(sentence, cfg, parsed=(words, tokens))
        except TooManySeams as exc:
            opinion = {"enabled": True, "error": "too_many_seams",
                       "seam_positions": exc.k, "limit": exc.limit,
                       "note": ("перебор §8 снят по лимиту max_seam_positions; verdict от "
                                "этого НЕ зависит — судья уже вынесен до перебора")}
            out = None
    if out is not None:
        human_norm = [_norm(b) for b in human_blocks]
        rec = [_norm(o["text"]) for o in out["recommended"]]
        if len(human_norm) == len(rec) and all(a == b for a, b in zip(human_norm, rec)):
            human_rank = 1
        else:
            for adv in out["admissible"]:
                blt = [_norm(o["text"]) for o in adv["blocks"]]
                if len(human_norm) == len(blt) and all(a == b for a, b in zip(human_norm, blt)):
                    human_rank = adv["rank"]
                    break
        opinion = {
            "enabled": True,
            "note": ("мнение машины: перебор+ранжирование §8; НЕ является истиной и НЕ "
                     "участвует в verdict"),
            "recommended": out["recommended"],
            "admissible_top": out["admissible"][:int(cfg.get("max_admissible", 5))],
            "total_admissible": len(out["admissible"]),
            "total_rejected": len(out["rejected"]),
            "human_rank": human_rank,
        }

    # --- effects (SPEC §8.2: объяснение min_merge / cap / rank) ---
    eff = {"min_merge": [], "cap": [], "rank": {}}
    final, merges = min_merge(words, tokens, cfg, root_id, _partition(n, set(cuts)))
    if [tuple(x) for x in final] != [tuple(x) for x in ranges]:
        eff["min_merge"].append({
            "merges": merges,
            "machine_blocks": [block_text(sentence, tokens, a, b) for a, b in final],
            "note": f"min_merge §3.6 сливает блоки < min={cfg['min']}; разбивка человека при этом меняется",
        })
    for (a, b), lc in zip(ranges, lex):
        if lc > cfg["cap"]:
            eff["cap"].append({"block": [a, b], "lex_words": lc, "cap": cfg["cap"],
                               "text": block_text(sentence, tokens, a, b)})
    if with_opinion:
        rec_blocks = opinion.get("recommended") or []
        rec_ranges = [[min(o["toks"]), max(o["toks"])] for o in rec_blocks]
        eff["rank"] = {
            "human_rank": human_rank,
            "human_key": _key_summary(words, tokens, cfg, ranges),
            "rank1_key": _key_summary(words, tokens, cfg, rec_ranges) if rec_ranges else {},
            "note": "ранжирование — справочное мнение машины; в verdict не входит",
        }
        if opinion.get("error"):
            eff["rank"]["opinion_error"] = opinion["error"]

    # --- diagnosis по каждой границе + hints ---
    cuts_list, hints = [], []
    for pos in cuts:
        feat = {}
        nb = wid.get(pos + 1)
        if nb is not None:
            feat = {"id": nb["id"], "text": nb["text"], "lemma": nb["lemma"],
                    "upos": nb["upos"], "xpos": nb["xpos"], "feats": nb["feats"],
                    "head": nb["head"], "deprel": nb["deprel"]}
        if pos in nocut:
            rid = sorted(set(nocut[pos]))[0]
            cuts_list.append({"pos": pos, "between": _between(wid, pos),
                              "status": "forbidden", "rule": rid,
                              "rules_all": sorted(set(nocut[pos])),
                              "features": feat, "hint": HINTS.get(rid, "")})
        elif pos in p2:
            cuts_list.append({"pos": pos, "between": _between(wid, pos),
                              "status": "forbidden", "rule": "punct_p2",
                              "features": feat, "hint": HINTS["punct_p2"]})
        elif pos not in seams:
            cuts_list.append({"pos": pos, "between": _between(wid, pos),
                              "status": "missing", "features": feat,
                              "hint": HINTS["missing"]})
        else:
            cuts_list.append({"pos": pos, "between": _between(wid, pos),
                              "status": "effect", "seams": seams[pos],
                              "features": feat, "hint": "рез легальный: покрыт C-классом"})

    for v in violations:
        h = HINTS.get(v["type"], "")
        if h and h not in hints:
            hints.append(h)

    coverage = {"covered": [c["pos"] for c in cuts_list if c["status"] == "effect"],
                "missing": [c["pos"] for c in cuts_list if c["status"] == "missing"],
                "forbidden": [c["pos"] for c in cuts_list if c["status"] == "forbidden"]}

    delta_required = any(v["type"] in ("missing", "forbidden") for v in violations)

    return {**base, "verdict": verdict, "match": verdict == "compliant",
            "human_rank": human_rank, "violations": violations,
            "diagnosis": {"cuts": cuts_list, "effects": eff, "coverage": coverage,
                          "hints": hints, "delta_required": delta_required},
            "machine_opinion": opinion}


# ============================ self-test ======================================
def _corpus_path():
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "..", "CORPUS", "verified.jsonl")


def self_test():
    """Регресс по CORPUS/verified.jsonl (accepted=true).
    pass   = разбивка человека COMPLIANT по текущему правилу (гейт PROTOCOL).
    strict = она же = recommended[0] машины (более сильный контроль, справочный)."""
    cfg = load_config(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
    path = _corpus_path()
    results = []
    if not os.path.exists(path):
        return results
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            case = json.loads(line)
            if case.get("accepted") is not True:
                continue
            res = check(case["sentence"], case["blocks"], cfg, with_opinion=True)
            results.append({
                "id": case.get("id"),
                "pass": res["verdict"] == "compliant",
                "strict_rank1": res.get("human_rank") == 1,
                "verdict": res["verdict"],
                "violations": [v["type"] for v in res["violations"]],
            })
    return results


def self_test_cli():
    res = self_test()
    total = len(res)
    passed = sum(1 for r in res if r["pass"])
    strict = sum(1 for r in res if r["strict_rank1"])
    print(f"self_test: {passed}/{total} compliant (strict rank1: {strict}/{total})")
    for r in res:
        print("  " + ("PASS" if r["pass"] else "FAIL"), r.get("id"),
              "[" + ("strict" if r["strict_rank1"] else "non-strict") + "]",
              r.get("violations") or "")
    return total, passed


# ============================ determinism =====================================
def _canonical_hash(d):
    """SHA-256 of canonical JSON (sort_keys, fixed separators, UTF-8)."""
    return hashlib.sha256(
        json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        .encode("utf-8")
    ).hexdigest()


# Провенанс (откуда взят разбор) — НЕ часть правила: он меняется при включённом
# и выключенном parse-кэше, поэтому в гейт детерминизма §6 не входит.
_VOLATILE_KEYS = ("parse_source",)


def _rule_output_only(out):
    return {k: v for k, v in out.items() if k not in _VOLATILE_KEYS}


# ============================ config completeness -----------------------------
def config_completeness():
    """§7/§10: verify RULE.md normative rules are (a) in config and (b) supported
    by rule.py handlers. Reports supported vs gaps; does NOT auto-claim complete.
    Returns True if all NORMATIVE conditions are supported."""
    cfg = load_config(os.path.join(os.path.dirname(__file__), "config.json"))
    report = {
        "version": cfg["version"]
    }

    # C-classes: each must be implemented in compute_seams.
    c_implemented = {"C1", "C2", "C3", "C4", "C5"}
    c_in_cfg = {s["class_id"] for s in cfg.get("seams", [])}
    report["seam_classes_config"] = sorted(c_in_cfg)
    report["seam_classes_implemented"] = sorted(c_implemented)
    report["seam_gaps"] = sorted(c_in_cfg - c_implemented)

    # NO-CUT: each id in config must have a rule.py handler (compute_nocut or run token-level).
    nocut_ids = {e["id"] for e in cfg.get("nocut", [])}
    # ids produced by compute_nocut + token-level mwt
    implemented_nocut = {
        "det_to_noun", "case_obl", "trunc_atomic_chain",
        "aux_cop", "root_aux", "mwt",
    }
    report["nocut_config_ids"] = sorted(nocut_ids)
    report["nocut_implemented"] = sorted(implemented_nocut & nocut_ids)
    gaps = sorted(nocut_ids - implemented_nocut)
    report["nocut_gaps"] = gaps
    # adv_part_pair: expressed in config (lemma_corr) but needs concrete lemma list
    # + a rule.py handler -> resolved per case, not generic.
    for g in gaps:
        report["gap_detail"] = {
            "adv_part_pair": (
                "RULE.md §4 last row (ADV/PART correlated pair). config has"
                " lemma_corr:true but no concrete lemma list and no rule.py"
                " handler. Per-case gap: resolve with a specific lemma set in a"
                " separate test case. Not used by current CORPUS/verified.jsonl.")
        }

    # P1/P2 + params: static, supported.
    report["punct_supported"] = {"P1": True, "P2": True}
    report["params_supported"] = {k: True for k in ("min", "pref", "cap", "terminal_set", "min_merge", "rank") if k in cfg}
    report["guards"] = {"max_seam_positions": cfg.get("max_seam_positions"),
                        "max_admissible": cfg.get("max_admissible")}
    report["rank_criteria_config"] = [f"{c['criterion']}:{c['direction']}" for c in cfg["rank"]["criteria"]]
    report["rank_criteria_implemented"] = sorted(RANK_CRITERIA)

    complete = (len(report.get("seam_gaps", [])) == 0 and len(gaps) == 0)
    report["complete"] = complete
    return report

# ============================ determinism =====================================
def determinism_cli(sentence):
    """§6: same input -> same output. Compare sha256 with parse-cache populated
    vs empty (model resources identical). Returns True if deterministic."""
    import shutil
    cfg = load_config(os.path.join(os.path.dirname(__file__), "config.json"))
    cfile = os.path.join(CACHE_DIR, "parse_cache.jsonl")
    tmpdir = CACHE_DIR + ".tmpoff"

    # 1) run WITH cache populated (populate if needed)
    out_on = run(sentence, cfg)
    h_on = _canonical_hash(_rule_output_only(out_on))

    # 2) empty the parse-cache, re-run
    moved = False
    if os.path.exists(cfile):
        os.makedirs(tmpdir, exist_ok=True)
        shutil.move(cfile, os.path.join(tmpdir, "parse_cache.jsonl"))
        moved = True
    out_off = run(sentence, cfg)
    h_off = _canonical_hash(_rule_output_only(out_off))

    # restore cache
    if moved and os.path.exists(os.path.join(tmpdir, "parse_cache.jsonl")):
        shutil.move(os.path.join(tmpdir, "parse_cache.jsonl"), cfile)
    else:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass
    # always clean the temp dir (may be empty after a successful move-back)
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass

    ok = (h_on == h_off)
    import sys as _sys
    cfg2 = load_config(os.path.join(os.path.dirname(__file__), "config.json"))
    print(f"determinism: cache_on={h_on} cache_off={h_off} identical={ok}")
    print(json.dumps({"input_hash": _hash_text(_norm(sentence)),
                      "config_hash": _canonical_hash(cfg2),
                      "python_version": _sys.version.split()[0],
                      "stanza_version": DEFAULT_STANZA_VERSION,
                      "model_dir": MODEL_DIR}, ensure_ascii=False))
    return ok


# ============================ main ===========================================
def main():
    _reconf_out()
    args = sys.argv[1:]
    base = os.path.dirname(os.path.abspath(__file__))
    cfgp = os.path.join(base, "config.json")
    if not args:
        print("usage: rule.py <sentence> | --check <sentence> --blocks ... [--no-opinion] [--parse-file <json>] | --self-test | --determinism <sentence> | --config-completeness")
        return 1
    if args[0] == "--self-test":
        total, passed = self_test_cli()
        return 0 if (total and passed == total) else 1
    if args[0] == "--check":
        # --check <sentence> --blocks b1 b2 ... [--no-opinion] [--parse-file <json>]
        sent = ""
        blocks = []
        with_opinion = True
        parse_file = None
        i = 1
        while i < len(args):
            a = args[i]
            if a == "--blocks":
                i += 1
                rest = args[i:]
                if "--no-opinion" in rest:
                    with_opinion = False
                    rest = [x for x in rest if x != "--no-opinion"]
                if "--parse-file" in rest:
                    k = rest.index("--parse-file")
                    parse_file = rest[k + 1]
                    rest = rest[:k] + rest[k + 2:]
                blocks = rest
                break
            elif a == "--no-opinion":
                with_opinion = False
                i += 1
            elif a == "--parse-file":
                parse_file = args[i + 1]
                i += 2
            else:
                sent = (sent + " "+a).strip()
                i += 1
        cfg = load_config(cfgp)
        payload = None
        if parse_file:
            with open(parse_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
        res = check(sent, blocks, cfg, with_opinion=with_opinion, parsed=payload)
        print(json.dumps(res, ensure_ascii=False))
        return 0 if res.get("verdict") == "compliant" else 1
    if args[0] == "--config-completeness":
        rep = config_completeness()
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0 if rep.get("complete") else 1
    if args[0] == "--determinism":
        sent = " ".join(args) if len(args) > 1 else "Ich weiß es."
        # determinism_cli() prints the hash comparison + §6 protocol metadata
        ok = determinism_cli(sent)
        return 0 if ok else 1
    sent = " ".join(args)
    cfg = load_config(cfgp)
    try:
        out = run(sent, cfg)
    except TooManySeams as exc:
        print(json.dumps({"error": "too_many_seams", "seam_positions": exc.k,
                          "limit": exc.limit,
                          "note": "поднять лимит можно только осознанно: перебор 2^|S|"},
                         ensure_ascii=False))
        return 2
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
