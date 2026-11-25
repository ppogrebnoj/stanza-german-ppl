# -*- coding: utf-8 -*-
"""acceptance.py — приёмка: doctor + smoke fast/full + валидаторы + mcp_probe.

    python scripts/run_checks.py --check acceptance --json

В JSON: checks[], f1 {corpus52, heldout_51}, validators, mcp_probe, verdict PASS/FAIL.
Эталон: F1 0.777 / 0.686, валидаторы 52/52 и 45/51. Ничего не меняет (кроме логов
самых инструментов). Код 0 = приёмка зелёная.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]   # installer/lib/checks -> корень проекта
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "rule"))
import _paths as P  # noqa: E402

REF_F1 = {"corpus52": 0.777, "heldout_51": 0.686}
TOL = 0.02
MIN_F1 = {"corpus52": 0.75, "heldout_51": 0.65}


def run(cmd: list[str], timeout: int = 1800) -> tuple[int, str]:
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return r.returncode, (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")
    except subprocess.TimeoutExpired:
        return 124, f"таймаут {timeout} с: {' '.join(cmd)}"
    except Exception as exc:  # noqa: BLE001
        return 125, str(exc)


def parse_json_obj(text: str):
    dec = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch == "{":
            try:
                obj, _ = dec.raw_decode(text[i:])
                return obj
            except Exception:
                continue
    return None


def check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "status": "PASS" if ok else "FAIL", "detail": detail[:800]}


def validator_sets() -> dict:
    import importlib.util
    out = {}
    cfg_path = P.RULE_DIR / "config.json"
    try:
        import validator as V
        cfg = V.load_cfg(str(cfg_path))
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    for name, expect in (("corpus52", 52), ("heldout_51", 45)):
        path = P.SETS_DIR / f"{name}.jsonl"
        try:
            stat, _, _ = V.run_set(str(path), cfg)
            out[name] = {"compliant": stat["compliant"], "n": stat["n"], "expected": expect,
                         "ok": stat["compliant"] == expect}
        except Exception as exc:  # noqa: BLE001
            out[name] = {"error": str(exc), "ok": False}
    return out


def f1_from_smoke(data: dict) -> dict:
    out = {}
    for item in data.get("results", []):
        m = re.match(r"segment_f1_(\w+)", item.get("name", ""))
        if not m:
            continue
        fm = re.search(r"F1\s+([0-9.]+)", item.get("detail", ""))
        if fm:
            out[m.group(1)] = float(fm.group(1))
        if item.get("status") == "FAIL":
            out[m.group(1) + "_fail"] = True
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    checks = []

    py = sys.executable
    rc, out = run([py, str(ROOT / "scripts" / "run_checks.py"), "--check", "doctor", "--json"])
    doc = (parse_json_obj(out) or {}).get("data") or {}
    checks.append(check("doctor", rc == 0 and bool(doc.get("ok")),
                        str(doc.get("counts", out[:200]))))

    for mode in ("fast", "full"):
        argv = [py, str(ROOT / "rule" / "smoke_test.py"), "--json"]
        if mode == "full":
            argv.append("--full")
        rc, out = run(argv)
        sm = parse_json_obj(out) or {}
        counts = sm.get("counts", {})
        checks.append(check(f"smoke_{mode}", rc == 0 and not counts.get("FAIL"), str(counts)))
        if mode == "full":
            f1 = f1_from_smoke(sm)

    vals = validator_sets()
    for name, v in vals.items():
        checks.append(check(f"validator_{name}", bool(v.get("ok")), str(v)))

    rc, out = run([py, str(ROOT / "scripts" / "run_checks.py"), "--check", "mcp_probe", "--json"])
    probe = (parse_json_obj(out) or {}).get("data") or {}
    checks.append(check("mcp_probe", rc == 0 and bool(probe.get("ok")),
                        str(probe.get("problems", out[:300]))))

    f1_ok = True
    for name, ref in REF_F1.items():
        have = f1.get(name)
        if have is None:
            f1_ok = False
        elif have < MIN_F1[name] - TOL or abs(have - ref) > TOL:
            f1_ok = False
    checks.append(check("f1_reference", f1_ok, str(f1)))

    verdict = "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL"
    result = {
        "ok": verdict == "PASS", "verdict": verdict, "checks": checks,
        "f1": {k: v for k, v in f1.items() if not k.endswith("_fail")},
        "f1_reference": REF_F1, "tolerance": TOL,
        "validators": vals, "mcp_probe": probe,
    }
    print(json.dumps(result, ensure_ascii=False, indent=1) if a.json else
          "\n".join(f"[{c['status']}] {c['name']}: {c['detail']}" for c in checks)
          + f"\nF1: {result['f1']}\nИТОГ: {verdict}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raise SystemExit(main())
