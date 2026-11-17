# -*- coding: utf-8 -*-
"""Кэш разборов Stanza: набор -> bench/cache/parses_<имя>.json

Stanza (depparse + constituency) — самая дорогая часть. Считаем один раз на набор
и дальше грузим готовые разборы: эксперименты идут секунды, а не минуты.
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bench.core import Parsed, build_parse

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

_nlp = None


def nlp():
    global _nlp
    if _nlp is None:
        import stanza
        _nlp = stanza.Pipeline("de", processors="tokenize,pos,lemma,depparse,constituency",
                               verbose=False, download_method=None)
    return _nlp


def load_rows(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def get_parses(path, force=False):
    """[(id, sentence, Parsed)] + rows. Кэш инвалидируется по содержимому файла."""
    rows = load_rows(path)
    h = hashlib.sha1(open(path, "rb").read()).hexdigest()[:10]
    name = os.path.splitext(os.path.basename(path))[0]
    cp = os.path.join(CACHE, f"parses_{name}_{h}.json")
    if os.path.exists(cp) and not force:
        d = json.load(open(cp, encoding="utf-8"))
        if d["ids"] == [r["id"] for r in rows]:
            parses = [(rid, s, Parsed.from_dict(pd)) for rid, s, pd in d["parses"]]
            return rows, parses
    pipeline = nlp()
    parses, out = [], []
    for r in rows:
        s = r["sentence"]
        p = build_parse(s, pipeline)
        if p is None:
            continue
        parses.append((r["id"], s, p))
        out.append([r["id"], s, p.to_dict()])
    os.makedirs(CACHE, exist_ok=True)
    json.dump({"ids": [r["id"] for r in rows], "parses": out},
              open(cp, "w", encoding="utf-8", newline="\n"), ensure_ascii=False)
    return rows, parses


if __name__ == "__main__":
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    sets = sys.argv[1:] or [os.path.join(here, "sets", x) for x in
                            ("corpus52.jsonl", "heldout_51.jsonl")]
    for p in sets:
        rows, parses = get_parses(p)
        print(f"{os.path.basename(p)}: {len(parses)} разборов в кэше")
