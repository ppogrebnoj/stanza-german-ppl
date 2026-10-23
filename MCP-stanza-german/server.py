#!/usr/bin/env python3
"""Stanza German MCP server (stdio).

Локальный MCP-сервер для синтаксического анализа немецкого языка на базе
Stanford Stanza 1.15.0 (CPU). Работает полностью офлайн: модели берутся из
локального кэша C:\\Users\\BIGTER\\AppData\\Local\\StanfordNLP\\stanza\\Cache\\1.15.0\\resources,
download_method=None — сеть не используется и повторная загрузка не требуется.

Запуск:  python server.py
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
import threading
import time
import datetime

# stdout должен оставаться чистым для MCP-протокола (stdio) и быть UTF-8
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ===================== логирование и версия сервера ==========================
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_SERVER_LOG_FILE = os.path.join(_BASE_DIR, "server.log")
_MAX_LOG_SIZE = 2 * 1024 * 1024

# version.json — текущая версия сервера (см. CHANGELOG.md: история).
def _get_server_version() -> str:
    try:
        with open(os.path.join(_BASE_DIR, "version.json"), "r", encoding="utf-8") as f:
            return str(json.load(f).get("server_version") or "dev")
    except Exception:  # noqa: BLE001
        return "dev"

def _log(msg: str) -> None:
    """Лог в файл (вращение при >2 МБ) + stderr. stdout остаётся чистым."""
    line = "%s %s\n" % (datetime.datetime.now().isoformat(timespec="seconds"), msg)
    try:
        if os.path.exists(_SERVER_LOG_FILE) and os.path.getsize(_SERVER_LOG_FILE) >= _MAX_LOG_SIZE:
            os.rename(_SERVER_LOG_FILE, _SERVER_LOG_FILE + ".1")
        with open(_SERVER_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:  # noqa: BLE001
        pass
    try:
        sys.stderr.write(line)
    except Exception:  # noqa: BLE001
        pass

def _run_tool(name: str, fn) -> dict:
    """Обёртка для инструмента: лог start/ok/error + время. Возвращает результат."""
    _log("TOOL %s start" % name)
    t0 = time.perf_counter()
    try:
        res = fn()
    except Exception as exc:  # noqa: BLE001
        _log("TOOL %s ERROR %.1f ms: %s" % (name, (time.perf_counter() - t0) * 1000, str(exc)))
        raise
    ms = (time.perf_counter() - t0) * 1000
    extra = ""
    if isinstance(res, dict):
        v = res.get("verdict")
        if v is not None:
            extra = " verdict=%s" % v
        elif res.get("gate_passed") is not None:
            extra = " gate=%s" % str(res["gate_passed"])
    _log("TOOL %s ok %.1f ms%s" % (name, ms, extra))
    return res

import stanza
from mcp.server.fastmcp import FastMCP

LANGUAGE = "de"
FULL_PROCESSORS = "tokenize,mwt,pos,lemma,depparse,constituency"
CORE_PROCESSORS = "tokenize,mwt,pos,lemma,depparse"

# Правило сегментации (rule.py + config.json + CORPUS) живёт отдельно от сервера.
# Путь — переменная окружения RULE_ROOT (поле env в mcp.json), иначе — дефолт.
RULE_ROOT_DEFAULT = r"E:\KI_WORK\MCP-stanza-german-RULE"

mcp = FastMCP(
    "stanza-german",
    instructions=(
        "Stanza de: parse_german — синтаксис (леммы/POS/зависимости + MWT-поля); "
        "constituency_german — фразовое дерево; calc_pause — паузы в сек по символам, пакетно; "
        "pipeline_info — статус. Судья правила: check_segmentation (verdict + подсказки), "
        "rule_self_test (регресс по CORPUS), rule_info (версия/критерии/полнота). Офлайн."
    ),
)

_pipeline: stanza.Pipeline | None = None
_pipeline_lock = threading.Lock()
_load_notes: list[str] = []


def _default_chars_per_sec() -> float:
    """Скорость calc_pause по умолчанию (симв./сек): переменная окружения
    STANZA_CHARS_PER_SEC, иначе 4.0. Настраивается полем 'env' записи сервера
    в mcp.json (LM Studio: Program → Install → Edit mcp.json)."""
    raw = os.environ.get("STANZA_CHARS_PER_SEC")
    if not raw:
        return 4.0
    try:
        value = float(raw)
    except ValueError:
        _load_notes.append(f"STANZA_CHARS_PER_SEC='{raw}' — не число, использовано 4.0")
        return 4.0
    if value <= 0:
        _load_notes.append(f"STANZA_CHARS_PER_SEC={value} должно быть > 0, использовано 4.0")
        return 4.0
    return value


DEFAULT_CHARS_PER_SEC = _default_chars_per_sec()


def _load_pipeline() -> stanza.Pipeline:
    """Загружает пайплайн из локального кэша (без сети). При неудаче с полным
    набором процессоров откатывается на ядро tokenize,mwt,pos,lemma,depparse."""
    for processors in (FULL_PROCESSORS, CORE_PROCESSORS):
        try:
            pipe = stanza.Pipeline(
                lang=LANGUAGE,  # в Stanza 1.15 параметр называется lang
                processors=processors,
                download_method=None,  # офлайн: только локальный кэш, без сети
                verbose=False,
            )
            if processors != FULL_PROCESSORS:
                _load_notes.append(
                    f"Загружено ядро процессоров ({processors}); "
                    "constituency недоступен"
                )
            return pipe
        except Exception as exc:  # noqa: BLE001 — фиксируем и пробуем ядро
            _load_notes.append(f"Не удалось загрузить '{processors}': {exc}")
    raise RuntimeError("Stanza pipeline не удалось загрузить: " + "; ".join(_load_notes))


def get_pipeline() -> stanza.Pipeline:
    """Ленивый singleton: пайплайн грузится один раз при первом вызове инструмента."""
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                _pipeline = _load_pipeline()
    return _pipeline


def _word_dict(d: dict) -> dict:
    """Нормализует запись word из Token.to_dict() (Stanza 1.15)."""
    return {
        "id": d.get("id"),
        "text": d.get("text"),
        "lemma": d.get("lemma"),
        "upos": d.get("upos"),
        "xpos": d.get("xpos"),
        "features": d.get("feats"),
        "head": d.get("head"),
        "dep": d.get("deprel"),
    }


def _sentence_words(doc, s) -> list[dict]:
    """Плоский список слов предложения (с учётом MWT-расширений).

    Каждой записи добавлены is_mwt / mwt_id — ИСТОЧНИК ТОЛЬКО STANZA:
    Token.is_mwt() и Token.id. Без вычисления/гадания из text/lemma/upos.
    Для MWT t.id — диапазон Word-ID (a, b); в JSON — список [a, b].
    rule.py собирает слова одного MWT по mwt_id."""
    words: list[dict] = []
    for t in s.tokens:
        is_mwt = bool(t.is_mwt())
        # МWT — диапазон Word-ID; одиночный токен — свой int id.
        mwid = list(t.id) if len(t.id) > 1 else t.id[0]
        for d in t.to_dict():
            w = _word_dict(d)
            w["is_mwt"] = is_mwt
            w["mwt_id"] = mwid
            words.append(w)
    return words


def _sentence_tokens(doc, s) -> list[dict]:
    """Параллельный список поверхностных токенов: один объект на каждый
    Sentence.token. Содержит MWT-флаг (Token.is_mwt()), явный перечень
    word_ids — Word-ID, входящие в токен, и offsets start_char/end_char.
    Нужен rule.py для восстановления поверхностного текста/пунктуации,
    диапазона MWT и вырезания текста блока по позициям символов (SPEC §4)."""
    tokens: list[dict] = []
    for t in s.tokens:
        tokens.append({
            "id": list(t.id) if len(t.id) > 1 else t.id[0],  # int; MWT: [a,b]
            "text": t.text,
            "start_char": t.start_char,  # offset в тексте предложения (SPEC §4)
            "end_char": t.end_char,
            "is_mwt": bool(t.is_mwt()),
            "word_ids": [w.id for w in t.words],
        })
    return tokens


def _texts_arg(text):
    """Нормализация входного текста инструментов анализа: str | list[str] |
    JSON-строка списка '["...","..."]' -> список предложений. Один вызов на
    весь пакет предложений."""
    if isinstance(text, (list, tuple)):
        return [str(t) for t in text]
    if isinstance(text, str):
        s = text.strip()
        if s.startswith("["):
            try:
                arr = json.loads(s)
                if isinstance(arr, list) and arr and all(isinstance(x, str) for x in arr):
                    return arr
            except Exception:  # noqa: BLE001 — обычное предложение со скобкой
                pass
        return [text]
    raise ValueError("text: str | list[str] | JSON-строка списка строк")


def _parse_german_impl(text) -> dict:
    """Синтаксический анализ немецкого текста (Stanza). Возвращает предложения: слова с леммой, UPOS/XPOS, features и зависимостями head/dep; MWT-поля is_mwt (bool) и mwt_id (диапазон Word-ID [a,b] для MWT); parallel list tokens (поверхностные токены с word_ids). Пакет: text = list[str] или JSON-строка списка — все предложения за один вызов; у предложения поле item (номер входного текста, 1-based). Пример: parse_german(["S1.", "S2."])"""
    pipe = get_pipeline()
    sentences = []
    for k, t in enumerate(_texts_arg(text)):
        doc = pipe(t)
        for s in doc.sentences:
            sentences.append({
                "id": len(sentences) + 1,
                "item": k + 1,
                "text": s.text,
                "words": _sentence_words(doc, s),
                "tokens": _sentence_tokens(doc, s),
            })
    return {"language": LANGUAGE, "count": len(sentences), "sentences": sentences}


@mcp.tool()
def parse_german(text: str | list[str]) -> dict:
    return _run_tool("parse_german", lambda: _parse_german_impl(text))

def _constituency_german_impl(text) -> dict:
    """Фразовое дерево Penn Treebank (скобочная запись) по предложениям немецкого текста. Пакет: text = list[str] или JSON-строка списка — все предложения за один вызов; поле item — номер входного текста. Пример: constituency_german(["S1.", "S2."])"""
    pipe = get_pipeline()
    out = []
    for k, t in enumerate(_texts_arg(text)):
        doc = pipe(t)
        for s in doc.sentences:
            tree = s.constituency
            out.append({
                "id": len(out) + 1,
                "item": k + 1,
                "text": s.text,
                "tree": str(tree) if tree is not None else None,
            })
    res = {"language": LANGUAGE, "count": len(out), "sentences": out}
    if any(x["tree"] is None for x in out):
        res["note"] = "constituency недоступен: загружено ядро процессоров без constituency"
    return res




@mcp.tool()
def constituency_german(text: str | list[str]) -> dict:
    return _run_tool("constituency_german", lambda: _constituency_german_impl(text))

def _analyze_german_impl(text) -> dict:
    """parse_german + constituency_german ОДНИМ вызовом для всего пакета:
    text = str | list[str] | JSON-строка списка. На каждое предложение:
    words/tokens (полный разбор) + tree (Penn Treebank). Пример:
    analyze_german(["S1.", "S2.", "S3."])"""
    pipe = get_pipeline()
    out = []
    for k, t in enumerate(_texts_arg(text)):
        doc = pipe(t)
        for s in doc.sentences:
            tree = s.constituency
            out.append({
                "id": len(out) + 1,
                "item": k + 1,
                "text": s.text,
                "words": _sentence_words(doc, s),
                "tokens": _sentence_tokens(doc, s),
                "tree": str(tree) if tree is not None else None,
            })
    res = {"language": LANGUAGE, "count": len(out), "sentences": out}
    if any(x["tree"] is None for x in out):
        res["note"] = "constituency недоступен: загружено ядро процессоров без constituency"
    return res


@mcp.tool()
def analyze_german(text: str | list[str]) -> dict:
    return _run_tool("analyze_german", lambda: _analyze_german_impl(text))

def _calc_pause_impl(texts: str | list[str], chars_per_sec: float = DEFAULT_CHARS_PER_SEC) -> dict:
    """Пауза в секундах: ceil(символы / chars_per_sec), 10/4->3c. Пакетно (list): items + total, тот же ceil. Скорость - симв./сек: по умолч. 4; переопределяется аргументом chars_per_sec или env STANZA_CHARS_PER_SEC. Пример: calc_pause(["..."], chars_per_sec=5)"""
    if chars_per_sec <= 0:
        raise ValueError("chars_per_sec должен быть положительным числом")
    items = [texts] if isinstance(texts, str) else list(texts)
    per_item = []
    total_chars = 0
    for t in items:
        n = len(t)
        total_chars += n
        per_item.append(
            {"characters": n, "pause_seconds": math.ceil(n / chars_per_sec)}
        )
    return {
        "chars_per_sec": chars_per_sec,
        "count": len(items),
        "items": per_item,
        "total": {
            "characters": total_chars,
            "pause_seconds": math.ceil(total_chars / chars_per_sec),
        },
    }



@mcp.tool()
def calc_pause(texts: str | list[str], chars_per_sec: float = DEFAULT_CHARS_PER_SEC) -> dict:
    return _run_tool("calc_pause", lambda: _calc_pause_impl(texts, chars_per_sec))

def _pipeline_info_impl() -> dict:
    """Статус сервера: загруженные процессоры, версии, путь к кэшу, offline-статус."""
    import torch

    pipe = get_pipeline()
    return {
        "server": "stanza-german",
        "server_version": _get_server_version(),
        "log_file": _SERVER_LOG_FILE,
        "language": LANGUAGE,
        "chars_per_sec_default": DEFAULT_CHARS_PER_SEC,
        "processors_loaded": sorted(pipe.processors.keys()),
        "download_method": None,
        "offline": True,
        "model_dir": str(pipe.dir),
        "versions": {
            "python": sys.version.split()[0],
            "stanza": stanza.__version__,
            "torch": torch.__version__,
        },
        "rule_root": _rule_root(),
        "rule_registered": _RULE is not None,
        "notes": list(_load_notes) + ([_RULE_NOTE] if _RULE_NOTE else []),
    }


# ======================= правило сегментации (судья) =========================
# rule.py = единственный код правила. Сервер — тонкая read-only обёртка:
# судья (check), регресс (self_test), паспорт правила (rule_info).
# config.json перечитывается на КАЖДЫЙ вызов: цикл правит конфиг и сразу
# перепроверяется; в ответе — config_hash, которым доказана версия суждения.
_RULE = None
_RULE_NOTE: str | None = None



@mcp.tool()
def pipeline_info() -> dict:
    return _run_tool("pipeline_info", lambda: _pipeline_info_impl())

def _rule_root() -> str:
    return os.environ.get("RULE_ROOT", RULE_ROOT_DEFAULT)


def _load_rule() -> None:
    """Импорт reference/rule.py из RULE_ROOT. Нет правила — сервер работает как
    раньше, инструменты судьи просто не регистрируются (не падает)."""
    global _RULE, _RULE_NOTE
    root = _rule_root()
    path = os.path.join(root, "reference", "rule.py")
    if not os.path.exists(path):
        _RULE_NOTE = f"правило не подключено: нет {path} (задайте RULE_ROOT)"
        return
    try:
        spec = importlib.util.spec_from_file_location("rule_reference", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["rule_reference"] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        _RULE = mod
    except Exception as exc:  # noqa: BLE001
        _RULE_NOTE = f"правило не подключено: {exc}"


def get_rule():
    if _RULE is None:
        raise RuntimeError(_RULE_NOTE or "rule.py не подключен")
    return _RULE


def rule_config():
    """config.json перечитывается каждый раз — свежее правило без рестарта сервера."""
    return get_rule().load_config(os.path.join(_rule_root(), "reference", "config.json"))


def _parse_payload(sentence: str) -> dict:
    """Разбор одного предложения в формате parse_german — его же судья и судит
    (SPEC §4): LLM и судья оперируют одними Word-ID."""
    pipe = get_pipeline()
    doc = pipe(sentence)
    if len(doc.sentences) != 1:
        raise ValueError(
            f"ожидается ровно одно предложение, Stanza дала {len(doc.sentences)}")
    s = doc.sentences[0]
    return {"language": "de", "sentences": [{
        "id": 1, "text": s.text,
        "words": _sentence_words(doc, s), "tokens": _sentence_tokens(doc, s),
    }]}


def _blocks_from_toks(tokens: list[dict], sentence: str, toks: list[list[int]]) -> list[str]:
    """toks=[[a,b],...] (Word-ID) -> тексты блоков. Канонический ввод: номера слов
    надёжнее текста блока (защита от опечаток)."""
    return [get_rule().block_text(sentence, tokens, int(a), int(b)) for a, b in toks]


def _check_one(item: dict, with_opinion: bool) -> dict:
    rule = get_rule()
    cfg = rule_config()
    sentence = (item.get("sentence") or "").strip()
    if not sentence:
        return {"verdict": "invalid_input", "sentence": sentence,
                "violations": [{"type": "invalid_sentence", "detail": "empty 'sentence'"}]}
    try:
        payload = _parse_payload(sentence)
    except Exception as exc:  # noqa: BLE001
        return {"verdict": "invalid_input", "sentence": sentence,
                "violations": [{"type": "invalid_sentence", "detail": str(exc)}]}
    tokens = payload["sentences"][0]["tokens"]
    blocks = item.get("blocks")
    if not blocks and item.get("toks"):
        blocks = _blocks_from_toks(tokens, sentence, item["toks"])
    if not blocks:
        return {"verdict": "invalid_input", "sentence": sentence,
                "violations": [{"type": "invalid_sentence",
                                "detail": "нужны 'blocks' (текст) или 'toks' (Word-ID)"}]}
    res = rule.check(sentence, list(blocks), cfg,
                     with_opinion=bool(with_opinion), parsed=payload)
    out = {
        "sentence": sentence,
        "verdict": res["verdict"],
        "violations": res["violations"],
        "coverage": res["diagnosis"]["coverage"],
        "cuts": res["diagnosis"]["cuts"],
        "effects": res["diagnosis"]["effects"],
        "hints": res["diagnosis"]["hints"],
        "delta_required": res["diagnosis"]["delta_required"],
        "block_not_found": res["diagnosis"].get("block_not_found", []),
        "parse_source": res["parse_source"],
        "rule_version": res["rule_version"],
        "config_hash": res["config_hash"],
    }
    op = res["machine_opinion"]
    if op.get("enabled"):
        out["machine_opinion"] = {
            "recommended": [b["text"] for b in op.get("recommended", [])],
            "admissible_top": [[b["text"] for b in a["blocks"]] for a in op.get("admissible_top", [])],
            "total_admissible": op.get("total_admissible"),
            "total_rejected": op.get("total_rejected"),
            "human_rank": op.get("human_rank"),
            "note": op.get("note"),
        }
        if op.get("error"):
            out["machine_opinion"]["error"] = op["error"]
            out["machine_opinion"]["seam_positions"] = op.get("seam_positions")
            out["machine_opinion"]["limit"] = op.get("limit")
    return out


def _check_segmentation_impl(items: dict | list[dict] | str,
                       with_opinion: bool = False) -> dict:
    """Судья правила сегментации: проверяет СООТВЕТСТВИЕ разбивки человека правилу
    и даёт подсказки. НЕ решает, как резать: recommended/admissible — справочное
    мнение, в verdict не входит.

    items — одно или список: {"sentence": "...", "blocks": ["блок1", "блок2"]}
    (текст блоков) ИЛИ {"sentence": "...", "toks": [[1,3],[4,9]]} (Word-ID, надёжнее).
    with_opinion=true включает перебор §8 (ранжирование) — он ограничен
    max_seam_positions и max_admissible из config.json.

    verdict: compliant | non_compliant | invalid_input. delta_required=true — только
    при missing/forbidden (дыра правила); min/cap/coverage — дырой НЕ считаются.
    Пример: check_segmentation({"sentence":"Ich weiß es, weil er müde ist.",
    "blocks":["Ich weiß es,","weil er müde ist."]})"""
    get_rule()
    if isinstance(items, str):
        s = items.strip()
        if s.startswith("{") or s.startswith("["):
            items = json.loads(s)  # JSON-строка пакета/объекта — принимаем как данные
    lst = [items] if isinstance(items, (dict, str)) else list(items)
    lst = [i if isinstance(i, dict) else {"sentence": i} for i in lst]
    results = [_check_one(i, with_opinion) for i in lst]
    cfg = rule_config()
    return {
        "count": len(results),
        "all_compliant": all(r["verdict"] == "compliant" for r in results),
        "rule_version": cfg["version"],
        "config_hash": get_rule()._canonical_hash(cfg),
        "results": results,
    }



def check_segmentation(items: dict | list[dict] | str,
                       with_opinion: bool = False) -> dict:    return _run_tool("check_segmentation", lambda: _check_segmentation_impl(items, with_opinion))

def _rule_self_test_impl() -> dict:
    """Регресс по CORPUS/verified.jsonl: воспроизводит ли ТЕКУЩИЙ config.json все
    ваши verified-разбивки. Гейт PROTOCOL: все compliant. strict_rank1 — справочно
    (разбивка человека = recommended[0] машины).

    Пример: rule_self_test() → {"total":3,"compliant":3,"failed_ids":[]}"""
    rule = get_rule()
    res = rule.self_test()
    total = len(res)
    compliant = sum(1 for r in res if r["pass"])
    strict = sum(1 for r in res if r["strict_rank1"])
    cfg = rule_config()
    return {
        "total": total,
        "compliant": compliant,
        "non_compliant": total - compliant,
        "strict_rank1": strict,
        "gate_passed": total > 0 and compliant == total,
        "failed_ids": [r["id"] for r in res if not r["pass"]],
        "cases": res,
        "rule_version": cfg["version"],
        "config_hash": rule._canonical_hash(cfg),
    }



def rule_self_test() -> dict:    return _run_tool("rule_self_test", lambda: _rule_self_test_impl())

def _rule_info_impl() -> dict:
    """Паспорт правила: версия, hash config.json, критерии ранжирования, статусы
    C-классов, лимиты перебора, полнота конфига, размер CORPUS.

    Пример: rule_info()"""
    rule = get_rule()
    cfg = rule_config()
    rep = rule.config_completeness()
    cpath = os.path.join(_rule_root(), "CORPUS", "verified.jsonl")
    verified = 0
    if os.path.exists(cpath):
        with open(cpath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    if json.loads(line).get("accepted") is True:
                        verified += 1
                except Exception:  # noqa: BLE001
                    continue
    return {
        "rule_root": _rule_root(),
        "registered": True,
        "rule_version": cfg["version"],
        "config_hash": rule._canonical_hash(cfg),
        "rank_criteria": [f"{c['criterion']}:{c['direction']}" for c in cfg["rank"]["criteria"]],
        "seam_classes_status": cfg["seam_classes_status"],
        "params": {"min": cfg["min"], "pref": cfg["pref"], "cap": cfg["cap"]},
        "guards": {"max_seam_positions": cfg.get("max_seam_positions"),
                   "max_admissible": cfg.get("max_admissible")},
        "config_completeness": rep,
        "corpus_verified_count": verified,
        "corpus_path": cpath,
    }



def rule_info() -> dict:    return _run_tool("rule_info", lambda: _rule_info_impl())

def main() -> None:
    rule_status = "rule not connected"
    if _RULE is not None and os.path.exists(os.path.join(_rule_root(), "reference", "config.json")):
        try:
            cfg = get_rule().load_config(os.path.join(_rule_root(), "reference", "config.json"))
            rule_status = "rule v%s, config_hash=%s" % (cfg["version"], get_rule()._canonical_hash(cfg))
        except Exception:  # noqa: BLE001
            rule_status = "rule error"
    _log(
        "START server_version=%s stanza=%s python=%s torch=n/a rule=%s log=%s" % (
            _get_server_version(),
            getattr(stanza, "__version__", "n/a"),
            sys.version.split()[0],
            rule_status,
            _SERVER_LOG_FILE,
        )
    )
    mcp.run()  # stdio transport


# Правило подключаем до регистрации инструментов: нет правила — судьи нет,
# сервер живёт как раньше.
_load_rule()
if _RULE is not None:
    mcp.tool(name="check_segmentation",
             description="Судья: verdict compliant/non_compliant/invalid_input + подсказки (см. docstring)")(check_segmentation)
    mcp.tool(name="rule_self_test",
             description="Регресс по CORPUS/verified.jsonl: compliant N/N + strict_rank1")(rule_self_test)
    mcp.tool(name="rule_info",
             description="Версия правила, config_hash, rank_criteria, лимиты, полнота конфига")(rule_info)


if __name__ == "__main__":
    main()
