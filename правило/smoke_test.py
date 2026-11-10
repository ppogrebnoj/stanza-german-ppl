#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""smoke_test.py — быстрый гейт целостности правила V4 (config + данные + код).

ЗАЧЕМ. Раньше числа правила жили в нескольких местах, и одна лишняя запятая в
config.json ломала судью на три дня. Тест ловит такое за ~0.2 с (fast) и проверяет
живой код на реальных данных (--full).

РЕЖИМЫ
  python smoke_test.py            fast: JSON, схема, согласованность config <-> код,
                                  наличие данных, целостность разметки (~0.2 с)
  python smoke_test.py --full     + валидатор на 52 (ждём 52/52) и F1 нарезчика
                                  на 52 и 51 (~60 с, нужна модель Stanza)
  python smoke_test.py --strict   WARN считать ошибкой (для CI)
  python smoke_test.py --quiet    только итог

КОДЫ ВЫХОДА: 0 — нет FAIL; 1 — есть FAIL.
  OK / WARN / FAIL / SKIP — см. вывод.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))   # E:\KI_WORK\правило
WORK = os.path.dirname(HERE)                        # E:\KI_WORK
CONFIG = os.path.join(HERE, "config.json")
SETS = os.path.join(WORK, "bench", "sets")
DATA = os.path.join(WORK, "данные")

REQUIRED_SEG = {
    "algorithm": str, "objective": str, "min_lex": int, "ideal_lex": (int, float),
    "cap_lex": int, "w_len": (int, float), "syllables": dict, "bans": dict,
    "one_word": dict, "penalties": dict,
}

results = []


def add(status, name, detail=""):
    results.append((status, name, detail))


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ fast

def check_config():
    if not os.path.exists(CONFIG):
        add("FAIL", "config_json", f"нет {CONFIG}")
        return None
    try:
        cfg = load(CONFIG)
    except Exception as exc:  # noqa: BLE001
        add("FAIL", "config_json", f"не читается: {exc}")
        return None
    add("OK", "config_json", f"version={cfg.get('version')}")
    seg = cfg.get("segment")
    if not seg:
        add("FAIL", "config_segment", "нет раздела 'segment'")
        return cfg
    bad = [k for k, t in REQUIRED_SEG.items() if not isinstance(seg.get(k), t)]
    if bad:
        add("FAIL", "config_segment", f"битые ключи: {bad}")
    else:
        add("OK", "config_segment", f"algorithm={seg['algorithm']}, min={seg['min_lex']}, "
                                   f"ideal={seg['ideal_lex']}, cap={seg['cap_lex']}")
    if not (1 <= seg["min_lex"] <= seg["cap_lex"]):
        add("FAIL", "config_values", "min_lex > cap_lex")
    if seg.get("warn_above_lex", 99) < seg["cap_lex"]:
        add("FAIL", "config_values", "warn_above_lex < cap_lex")
    for k, v in (seg.get("penalties") or {}).items():
        if not 0 <= float(v) <= 1:
            add("FAIL", "config_values", f"штраф {k}={v} вне 0..1")
    return cfg


def check_code_agrees(cfg):
    """config.json и DEFAULT_CFG в валидаторе должны описывать одно и то же."""
    sys.path.insert(0, HERE)
    try:
        import validator as V
    except Exception as exc:  # noqa: BLE001
        add("FAIL", "code_import", f"validator.py не импортируется: {exc}")
        return
    add("OK", "code_import", "validator.py импортируется")
    seg = cfg["segment"]
    missing = [k for k in V.DEFAULT_CFG if k.startswith("_") is False and k not in seg]
    if missing:
        add("WARN", "config_code_consistency", f"в config нет ключей кода: {missing}")
    else:
        add("OK", "config_code_consistency", "ключи config покрывают DEFAULT_CFG")
    loaded = V.load_cfg(CONFIG)
    for key in ("min_lex", "cap_lex", "ideal_lex", "w_len", "objective"):
        if loaded.get(key) != seg.get(key):
            add("FAIL", "config_code_consistency", f"{key}: config={seg.get(key)} код={loaded.get(key)}")
            return
    add("OK", "config_code_consistency", "числа совпадают с config.json")


def check_data():
    for fname, name in (("corpus52.jsonl", "набор 52"), ("heldout_51.jsonl", "набор 51"),
                        ("heldout_150.jsonl", "список 150")):
        path = os.path.join(SETS, fname)
        if not os.path.exists(path):
            add("FAIL", "data_files", f"нет {path}")
            continue
        rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
        add("OK", "data_files", f"{fname}: {len(rows)}")
    for fname in ("РАЗМЕТКА_52.md", "РАЗМЕТКА_51.md", "СПИСОК_150.md"):
        if not os.path.exists(os.path.join(DATA, fname)):
            add("FAIL", "data_md", f"нет данные/{fname}")
    if all(os.path.exists(os.path.join(DATA, f)) for f in
           ("РАЗМЕТКА_52.md", "РАЗМЕТКА_51.md", "СПИСОК_150.md")):
        add("OK", "data_md", "markdown-файлы разметки на месте")


def check_corpus_integrity():
    path = os.path.join(SETS, "corpus52.jsonl")
    if not os.path.exists(path):
        return
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        add("FAIL", "corpus_jsonl", "id не уникальны")
    bad = [r["id"] for r in rows
           if " ".join(r["blocks"]).replace("  ", " ").strip() != r["sentence"].strip()]
    if bad:
        add("FAIL", "corpus_jsonl", f"блоки не складываются в предложение: {bad[:3]}")
    else:
        add("OK", "corpus_jsonl", f"{len(rows)} кейсов, блоки = предложение")


# ------------------------------------------------------------------ full

def check_live():
    sys.path.insert(0, HERE)
    try:
        import validator as V
        import segment as S
    except Exception as exc:  # noqa: BLE001
        add("FAIL", "live_import", str(exc))
        return
    cfg = V.load_cfg(CONFIG)
    stat, codes, details = V.run_set(os.path.join(SETS, "corpus52.jsonl"), cfg)
    if stat["compliant"] == stat["n"] and stat["n"] > 0:
        add("OK", "validator_52", f"{stat['compliant']}/{stat['n']} compliant")
    else:
        add("FAIL", "validator_52", f"{stat['compliant']}/{stat['n']}; коды {codes}")

    for name, min_f1 in (("corpus52.jsonl", 0.75), ("heldout_51.jsonl", 0.65)):
        rows = [json.loads(l) for l in open(os.path.join(SETS, name), encoding="utf-8") if l.strip()]
        tp = fp = fn = 0
        for r in rows:
            if not r.get("blocks"):
                continue
            s, pred = S.bounds_of(r["sentence"], cfg)
            truth = V.blocks_to_bounds(s, r["blocks"])
            p, t = set(pred[1:-1]), set(truth[1:-1])
            tp += len(p & t); fp += len(p - t); fn += len(t - p)
        f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0
        status = "OK" if f1 >= min_f1 else "FAIL"
        add(status, f"segment_f1_{name.split('.')[0]}", f"F1 {f1:.3f} (порог {min_f1})")


# ------------------------------------------------------------------ вывод

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    cfg = check_config()
    if cfg:
        check_code_agrees(cfg)
    check_data()
    check_corpus_integrity()
    if a.full:
        check_live()
    else:
        add("SKIP", "validator_52", "нужен --full (Stanza)")
        add("SKIP", "segment_f1", "нужен --full (Stanza)")

    ok = sum(1 for s, _, _ in results if s == "OK")
    warn = sum(1 for s, _, _ in results if s == "WARN")
    fail = sum(1 for s, _, _ in results if s == "FAIL")
    skip = sum(1 for s, _, _ in results if s == "SKIP")
    if not a.quiet:
        for status, name, detail in results:
            if status == "SKIP" and not a.full:
                continue
            print(f"  [{status:4}] {name:24} {detail}")
    mode = "full" if a.full else "fast"
    print(f"\nsmoke_test ({mode}): OK {ok}, WARN {warn}, FAIL {fail}, SKIP {skip}")
    if fail:
        print("ИТОГ: НЕ РАБОТАЕТ — см. FAIL выше")
        return 1
    if warn and a.strict:
        print("ИТОГ: WARN при --strict = ошибка")
        return 1
    print("ИТОГ: работает")
    return 0


if __name__ == "__main__":
    sys.exit(main())
