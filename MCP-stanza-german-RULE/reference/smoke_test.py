#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""smoke_test.py — быстрый гейт целостности правила (config + CORPUS + код).

ЗАЧЕМ. 27.10.2026 в `reference/config.json` ушла лишняя запятая, и судья перестал
запускаться на три дня — при этом в коммите было написано «reg 52/52». Тест ловит
такое за ~0.2 с (fast) и проверяет самого судью на живых кейсах (--full).

РЕЖИМЫ
  python smoke_test.py            fast: без Stanza — JSON, схема, корпус, отчётность,
                                  расхождения «конфиг ↔ код» (~0.2 с)
  python smoke_test.py --full     + судья на 3 кейсах, регресс по CORPUS (52 кейса),
                                  путь MCP-сервера (~20 с, нужна модель Stanza)
  python smoke_test.py --strict   WARN считать ошибкой (для CI)
  python smoke_test.py --quiet    только итог

КОДЫ ВЫХОДА
  0 — нет FAIL (при --strict: нет FAIL и нет WARN)
  1 — есть FAIL (при --strict: есть FAIL или WARN)

Смысл статусов:
  OK   — проверка пройдена;
  WARN — известное расхождение/открытый вопрос, работа не блокируется;
  FAIL — состояние нерабочее: судья или корпус сломаны;
  SKIP — проверка неприменима (нет Stanza / нет MCP-сервера).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONFIG = os.path.join(HERE, "config.json")
CORPUS = os.path.join(ROOT, "CORPUS", "verified.jsonl")
SERVER = os.path.join(os.path.dirname(ROOT), "MCP-stanza-german", "server.py")

sys.path.insert(0, HERE)

RESULTS = []  # [{"id", "status", "detail"}]


# --------------------------------------------------------------------------- #
# инфраструктура отчёта
# --------------------------------------------------------------------------- #
def _reconf_out():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def add(cid, status, detail):
    RESULTS.append({"id": cid, "status": status, "detail": detail})


def _json_error_detail(path, exc):
    """Строка с курсором на месте ошибки — чтобы правка была очевидной."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().split("\n")
        line = lines[exc.lineno - 1] if 0 < exc.lineno <= len(lines) else ""
    except Exception:
        line = ""
    out = f"{path}:{exc.lineno}:{exc.colno}: {exc.msg}"
    if line:
        out += f"\n         {exc.lineno:>4} | {line.strip()[:120]}"
        out += f"\n              | {' ' * max(0, exc.colno - 1)}^"
        if exc.msg.lower().startswith("expecting value") and line.strip()[:1] in "]}":
            out += "\n         подсказка: похоже на лишнюю запятую перед закрывающей скобкой"
    return out


# --------------------------------------------------------------------------- #
# проверки: fast
# --------------------------------------------------------------------------- #
def check_config_json():
    """config.json должен быть валидным JSON. Это ровно тот баг, что был 27.10."""
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except json.JSONDecodeError as exc:
        add("config_json", "FAIL", _json_error_detail(CONFIG, exc))
        return None
    except OSError as exc:
        add("config_json", "FAIL", f"{CONFIG}: {exc}")
        return None
    seams = [s.get("class_id") for s in cfg.get("seams", [])]
    add("config_json", "OK",
        f"{os.path.basename(CONFIG)} читается: version={cfg.get('version')}, "
        f"seams={len(seams)}, nocut={len(cfg.get('nocut', []))}")
    return cfg


def check_config_schema(cfg):
    """Схема §9: неизвестные ключи/операторы — ошибка."""
    import rule as R
    try:
        R.validate_schema(cfg)
    except Exception as exc:  # noqa: BLE001
        add("config_schema", "FAIL", f"validate_schema: {exc}")
        return
    add("config_schema", "OK", "validate_schema пройдена (строгая схема §9)")


def check_config_version(cfg):
    """Версия правила — единственный источник истины: config.version."""
    ver = cfg.get("version")
    if not isinstance(ver, str) or not re.fullmatch(r"v\d+(\.\d+)?", ver or ""):
        add("config_version", "FAIL", f"config.version={ver!r} — ожидается вид 'vN'")
        return
    add("config_version", "OK", f"config.version={ver}")


def check_config_hash(cfg):
    import rule as R
    add("config_hash", "OK", R._canonical_hash(cfg)[:16] + "… (sha256 канонического JSON)")


def check_seam_status(cfg):
    """Каждый класс C* из seams должен иметь статус, и наоборот."""
    seams = {s.get("class_id") for s in cfg.get("seams", [])}
    status = cfg.get("seam_classes_status", {})
    missing = sorted(seams - set(status))
    extra = sorted(set(status) - seams)
    bad = sorted(k for k, v in status.items() if v not in ("verified", "untested"))
    problems = []
    if missing:
        problems.append(f"нет статуса у {missing}")
    if extra:
        problems.append(f"статус без класса {extra}")
    if bad:
        problems.append(f"недопустимый статус у {bad}")
    if problems:
        add("seam_status", "FAIL", "; ".join(problems))
    else:
        add("seam_status", "OK", f"{len(seams)} классов, статусы согласованы")


def check_config_code_consistency(cfg):
    """Пороги C3/C5 зашиты в коде и НЕ читаются из config — ловим расхождение.

    Правило v7 (решение человека №42/d) требует 2/2; в коде исторически 3/3.
    Это не «сломанный файл», а расхождение правила и реализации: правка меняет
    поведение судьи, поэтому статус WARN — нужно решение человека, а не тихий фикс.
    """
    import rule as R
    by_id = {s.get("class_id"): s.get("condition") or {} for s in cfg.get("seams", [])}
    problems = []
    for cid, hard in (("C3", R._C3_MIN_LEX), ("C5", R._C5_MIN_LEX)):
        cond = by_id.get(cid, {})
        want_l = cond.get("min_left_lex")
        want_r = cond.get("min_right_lex")
        if want_l is None and want_r is None:
            continue
        if hard != want_l or hard != want_r:
            problems.append(
                f"{cid}: код требует {hard}/{hard} лексических слов, "
                f"config.json — {want_l}/{want_r}")
    if problems:
        add("config_code_consistency", "WARN",
            "условия C3/C5 в config не исполняются кодом: " + "; ".join(problems)
            + " — нужно решение (правка кода меняет правило)")
    else:
        add("config_code_consistency", "OK", "пороги C3/C5 в коде совпадают с config")


def check_corpus():
    """Корпус: каждая строка — валидный JSON нужной формы, id уникальны."""
    if not os.path.exists(CORPUS):
        add("corpus_jsonl", "FAIL", f"нет файла {CORPUS}")
        return
    ids, problems, n = set(), [], 0
    with open(CORPUS, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            n += 1
            try:
                case = json.loads(line)
            except json.JSONDecodeError as exc:
                problems.append(f"строка {lineno}: не JSON ({exc.msg})")
                continue
            for key in ("id", "sentence", "blocks", "accepted"):
                if key not in case:
                    problems.append(f"строка {lineno}: нет поля {key!r}")
            blocks = case.get("blocks")
            if not isinstance(blocks, list) or not blocks or not all(
                    isinstance(b, str) and b.strip() for b in blocks or []):
                problems.append(f"строка {lineno} ({case.get('id')}): blocks пустые/не строки")
            if case.get("id") in ids:
                problems.append(f"строка {lineno}: дубль id {case.get('id')!r}")
            ids.add(case.get("id"))
            if not str(case.get("sentence", "")).strip():
                problems.append(f"строка {lineno}: пустое sentence")
    if problems:
        add("corpus_jsonl", "FAIL", f"{len(problems)} проблем(ы): " + " | ".join(problems[:5]))
    else:
        add("corpus_jsonl", "OK", f"{n} кейсов, id уникальны, поля на месте")


def check_completeness(cfg):
    """Полнота конфига: неподдержанные условия должны быть видны, а не молчать."""
    import rule as R
    try:
        rep = R.config_completeness()
    except Exception as exc:  # noqa: BLE001
        add("config_completeness", "FAIL", f"config_completeness() упал: {exc}")
        return
    seam_gaps = rep.get("seam_gaps") or []
    nocut_gaps = rep.get("nocut_gaps") or []
    if seam_gaps:
        add("config_completeness", "FAIL", f"seam-классы без реализации: {seam_gaps}")
    elif nocut_gaps:
        add("config_completeness", "WARN",
            f"open NO-CUT без обработчика: {nocut_gaps} (complete=false — ожидаемо)")
    else:
        add("config_completeness", "OK", "complete=true")


def check_version_drift(cfg):
    """Документы не должны объявлять другую версию правила, чем config.version."""
    ver = cfg.get("version")
    notes = []
    proto = os.path.join(ROOT, "PROTOCOL.md")
    try:
        with open(proto, "r", encoding="utf-8") as f:
            m = re.search(r"текущая базовая\s*[—-]\s*(v[\d.]+)", f.read())
        if m and m.group(1) != ver:
            notes.append(f"PROTOCOL.md: базовая {m.group(1)}")
    except OSError:
        pass
    try:
        tag = subprocess.run(["git", "-C", ROOT, "describe", "--tags", "--exact-match", "HEAD"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        if tag and tag != ver:
            notes.append(f"git tag на HEAD: {tag}")
    except Exception:  # noqa: BLE001 — git может отсутствовать
        pass
    if notes:
        add("version_drift", "WARN", f"config.version={ver}, но " + "; ".join(notes))
    else:
        add("version_drift", "OK", f"версия согласована ({ver})")


# --------------------------------------------------------------------------- #
# проверки: --full (нужна Stanza)
# --------------------------------------------------------------------------- #
JUDGE_CASES = [
    # (id, sentence, blocks, ожидаемый verdict)
    ("compliant", "Er arbeitet bei der Firma.",
     ["Er arbeitet bei", "der Firma."], "compliant"),
    ("forbidden_det", "Ich habe bei der Firma gearbeitet.",
     ["Ich habe bei der", "Firma gearbeitet."], "non_compliant"),
    ("block_not_found", "Ich habe bei der Firma gearbeitet.",
     ["Ich habe bei der Firma gearbeitet.", "Firma gearbeitet."], "invalid_input"),
]


def check_judge_roundtrip(cfg):
    """Судья реально отвечает и различает три вердикта."""
    import rule as R
    try:
        bad = []
        for cid, sent, blocks, want in JUDGE_CASES:
            res = R.check(sent, blocks, cfg, with_opinion=False)
            if res.get("verdict") != want:
                bad.append(f"{cid}: {res.get('verdict')} вместо {want} "
                           f"({[v.get('type') for v in res.get('violations', [])]})")
    except Exception as exc:  # noqa: BLE001
        add("judge_roundtrip", "FAIL", f"check() упал: {type(exc).__name__}: {exc}")
        return
    if bad:
        add("judge_roundtrip", "FAIL", "; ".join(bad))
    else:
        add("judge_roundtrip", "OK", f"{len(JUDGE_CASES)} кейса: compliant/non_compliant/invalid_input")


def check_self_test():
    """Регресс по корпусу: все verified-кейсы должны быть compliant."""
    import rule as R
    try:
        res = R.self_test()
    except Exception as exc:  # noqa: BLE001
        add("self_test", "FAIL", f"self_test() упал: {type(exc).__name__}: {exc}")
        return
    total = len(res)
    passed = sum(1 for r in res if r["pass"])
    strict = sum(1 for r in res if r["strict_rank1"])
    failed = [r["id"] for r in res if not r["pass"]]
    if total == 0:
        add("self_test", "FAIL", "корпус пуст — регресс нечего проверять")
    elif failed:
        add("self_test", "FAIL",
            f"{passed}/{total} compliant; провалили: {', '.join(map(str, failed[:5]))}")
    else:
        add("self_test", "OK",
            f"{passed}/{total} compliant; strict rank1 {strict}/{total} "
            f"(справочно, гейтом не является)")


def check_mcp_path(cfg):
    """Боевой путь: MCP-инструмент check_segmentation на том же config.json."""
    if not os.path.exists(SERVER):
        add("mcp_path", "SKIP", f"нет {SERVER}")
        return
    import importlib.util
    os.environ.setdefault("RULE_ROOT", ROOT)
    try:
        spec = importlib.util.spec_from_file_location("stanza_server_smoke", SERVER)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["stanza_server_smoke"] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        out = mod._check_segmentation_impl(
            [{"sentence": "Er arbeitet bei der Firma.",
              "blocks": ["Er arbeitet bei", "der Firma."]}], False)
    except ImportError as exc:
        add("mcp_path", "SKIP", f"MCP-сервер не импортируется ({exc})")
        return
    except Exception as exc:  # noqa: BLE001
        add("mcp_path", "FAIL", f"check_segmentation упал: {type(exc).__name__}: {exc}")
        return
    import rule as R
    problems = []
    if not out.get("all_compliant"):
        problems.append(f"verdict={[r.get('verdict') for r in out.get('results', [])]}")
    if out.get("config_hash") != R._canonical_hash(cfg):
        problems.append("config_hash сервера не совпал с конфигом репозитория")
    if problems:
        add("mcp_path", "FAIL", "; ".join(problems))
    else:
        add("mcp_path", "OK",
            f"check_segmentation вернул compliant (rule {out.get('rule_version')})")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    _reconf_out()
    ap = argparse.ArgumentParser(description="smoke-тест правила сегментации")
    ap.add_argument("--full", action="store_true", help="включая Stanza-проверки (~20 с)")
    ap.add_argument("--strict", action="store_true", help="WARN считать ошибкой")
    ap.add_argument("--quiet", action="store_true", help="только итог")
    args = ap.parse_args()

    t0 = time.time()
    cfg = check_config_json()
    if cfg is None:
        for cid in ("config_schema", "config_version", "config_hash", "seam_status",
                    "config_code_consistency", "completeness", "version_drift",
                    "judge_roundtrip", "self_test", "mcp_path"):
            add(cid, "SKIP", "config.json не читается")
    else:
        check_config_schema(cfg)
        check_config_version(cfg)
        check_config_hash(cfg)
        check_seam_status(cfg)
        check_config_code_consistency(cfg)
        check_completeness(cfg)
        check_version_drift(cfg)
        if args.full:
            check_judge_roundtrip(cfg)
            check_self_test()
            check_mcp_path(cfg)
        else:
            for cid in ("judge_roundtrip", "self_test", "mcp_path"):
                add(cid, "SKIP", "нужен --full")
    check_corpus()

    order = {"FAIL": 0, "WARN": 1, "SKIP": 2, "OK": 3}
    RESULTS.sort(key=lambda r: order.get(r["status"], 9))

    counts = {s: sum(1 for r in RESULTS if r["status"] == s)
              for s in ("FAIL", "WARN", "SKIP", "OK")}
    if not args.quiet:
        for r in RESULTS:
            print(f"  [{r['status']:<4}] {r['id']:<24} {r['detail']}")
        print()
    mode = "full" if args.full else "fast"
    print(f"smoke_test ({mode}): OK {counts['OK']}, WARN {counts['WARN']}, "
          f"FAIL {counts['FAIL']}, SKIP {counts['SKIP']} — {time.time() - t0:.2f} с")
    if counts["FAIL"]:
        print("ИТОГ: НЕ РАБОТАЕТ — см. FAIL выше")
        return 1
    if args.strict and counts["WARN"]:
        print("ИТОГ: --strict — WARN считается ошибкой")
        return 1
    if counts["WARN"]:
        print("ИТОГ: работает; есть известные расхождения (WARN) — нужны решения человека")
    else:
        print("ИТОГ: всё в порядке")
    return 0


if __name__ == "__main__":
    sys.exit(main())
