# -*- coding: utf-8 -*-
"""merge_gate.py — однозначный вердикт по PR: MERGE / BLOCK / WAIT / ERROR.

Только вердикт: скрипт ничего не мержит и не пишет в GitHub. Единственный источник
данных — `gh api graphql` (gh уже используется в release.yml). Детали и правила —
docs/merge-gate.md.

Вывод: stdout — только вердикт (текст или --json), stderr — логи.
Коды выхода локальны для гейта: 0 MERGE · 1 BLOCK · 2 WAIT · 3 ERROR.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXIT = {"MERGE": 0, "BLOCK": 1, "WAIT": 2, "ERROR": 3}
GHA_APP_SLUGS = {"github-actions"}
BLOCK_CONCLUSIONS = {"FAILURE", "ERROR", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"}
GHA_OK_CONCLUSIONS = {"SUCCESS", "SKIPPED", "NEUTRAL"}
SUPERSEDED_PHRASE = (
    "устаревший CANCELLED, вытесненный более поздним SUCCESS той же проверки при том же HEAD SHA"
)

QUERY = """
query($owner:String!,$repo:String!,$number:Int!) {
  repository(owner:$owner,name:$repo) {
    pullRequest(number:$number) {
      number url state isDraft merged mergeable mergeStateStatus headRefOid baseRefName reviewDecision
      statusCheckRollup {
        contexts(last: 100) {
          pageInfo { hasPreviousPage }
          nodes {
            __typename
            ... on CheckRun {
              name status conclusion startedAt completedAt detailsUrl
              checkSuite { commit { oid } app { slug } workflowRun { workflow { name } } }
            }
            ... on StatusContext {
              context state createdAt updatedAt targetUrl
              commit { oid }
            }
          }
        }
      }
    }
  }
}
"""


class GateError(Exception):
    """Ошибка получения/разбора данных: вердикт ERROR, код выхода 3."""

    def __init__(self, message: str, code: str = "gh_error") -> None:
        super().__init__(message)
        self.code = code


def _log(message: str) -> None:
    print(f"merge_gate: {message}", file=sys.stderr)


def _get(data, *path, default=None):
    cur = data
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def _ts(value) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _run(cmd: list[str], timeout: float) -> str:
    try:
        proc = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GateError(f"{cmd[0]}: таймаут {timeout:g} с", "timeout") from exc
    except OSError as exc:
        raise GateError(f"не запустить {cmd[0]}: {exc}", "gh_error") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().replace("\n", " ")[:300]
        raise GateError(f"{cmd[0]} rc={proc.returncode}: {detail}", "gh_error")
    if proc.stderr and proc.stderr.strip():
        _log(proc.stderr.strip().replace("\n", " ")[:300])
    return proc.stdout or ""


def parse_repo_from_url(url: str) -> str:
    """owner/repo из HTTPS/SSH remote; бросает GateError при неизвестном формате."""
    match = re.search(r"github\.com[:/]([^/]+)/([^/#?]+?)(?:\.git)?/?$", (url or "").strip())
    if not match:
        raise GateError(f"не разобрать GitHub remote: {url!r}; укажите --repo owner/repo", "bad_repo")
    return f"{match.group(1)}/{match.group(2)}"


def resolve_repo(explicit: str | None, timeout: float = 30.0) -> str:
    if explicit:
        if not re.fullmatch(r"[^/\s]+/[^/\s]+", explicit.strip()):
            raise GateError(f"--repo должен быть owner/repo: {explicit!r}", "bad_repo")
        return explicit.strip()
    return parse_repo_from_url(_run(["git", "-C", str(ROOT), "remote", "get-url", "origin"], timeout))


def fetch_pr(pr_number: int, repo: str, timeout: float = 30.0) -> dict:
    owner, name = repo.split("/", 1)
    raw = _run([
        "gh", "api", "graphql",
        "-f", f"owner={owner}", "-f", f"repo={name}", "-F", f"number={pr_number}",
        "-f", f"query={QUERY}",
    ], timeout)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GateError(f"gh вернул не-JSON: {raw[:200]!r}", "bad_data") from exc
    if payload.get("errors"):
        messages = "; ".join(str(e.get("message", e)) for e in payload["errors"][:3])
        raise GateError(f"GraphQL: {messages}", "gh_error")
    pr = _get(payload, "data", "repository", "pullRequest")
    if not pr:
        raise GateError(f"PR #{pr_number} не найден в {repo}", "not_found")
    return pr


def normalize_contexts(nodes, head_oid: str) -> tuple[list[dict], list[dict]]:
    """Привести контексты GraphQL к единому виду и отбросить чужие head SHA."""
    contexts: list[dict] = []
    dropped: list[dict] = []
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        kind = node.get("__typename")
        suite = node.get("checkSuite") or {}
        if kind == "CheckRun":
            oid = _get(suite, "commit", "oid") or ""
            app = (_get(suite, "app", "slug") or "").lower()
            workflow = _get(suite, "workflowRun", "workflow", "name") or ""
            source = "gha" if app in GHA_APP_SLUGS or workflow else "external"
            name = node.get("name") or "(без имени)"
            status = (node.get("status") or "").upper()
            conclusion = (node.get("conclusion") or "").upper() if status == "COMPLETED" else ""
            started, completed = node.get("startedAt"), node.get("completedAt") if status == "COMPLETED" else None
            url = node.get("detailsUrl") or ""
        elif kind == "StatusContext":
            oid = _get(node, "commit", "oid") or ""
            app, workflow, source = "", "status", "external"
            name = node.get("context") or "(без имени)"
            state = (node.get("state") or "").upper()
            status = "PENDING" if state in {"PENDING", "EXPECTED"} else "COMPLETED"
            conclusion = state if status == "COMPLETED" else ""
            started, completed = node.get("createdAt"), node.get("updatedAt") if status == "COMPLETED" else None
            url = node.get("targetUrl") or ""
        else:
            oid = _get(node, "commit", "oid") or _get(suite, "commit", "oid") or ""
            app, workflow, source = "", "", "external"
            name = node.get("name") or node.get("context") or "(без имени)"
            status = (node.get("status") or "").upper() or "UNKNOWN"
            conclusion = (node.get("conclusion") or node.get("state") or "").upper()
            started, completed = node.get("startedAt") or node.get("createdAt"), node.get("completedAt") or node.get("updatedAt")
            url = node.get("detailsUrl") or node.get("targetUrl") or ""

        run_match = re.search(r"/actions/runs/(\d+)", url)
        run_id = int(run_match.group(1)) if run_match else None
        start_ts, done_ts = _ts(started), _ts(completed)
        item = {
            "name": name, "workflow": workflow, "source": source, "app": app,
            "status": status, "conclusion": conclusion, "run_id": run_id,
            "started_at": started or "", "completed_at": completed or "",
            "details_url": url, "head_oid": oid,
            "key": (source, workflow, name),
            "sort_key": (run_id or 0, max(start_ts, done_ts), done_ts, start_ts),
        }
        if not head_oid or (oid and oid != head_oid) or not oid:
            rec = public_context(item)
            rec["reason"] = "wrong_head" if oid and head_oid and oid != head_oid else "missing_head_oid"
            dropped.append(rec)
            continue
        contexts.append(item)
    return contexts, dropped


def public_context(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in {"key", "sort_key"}}


def split_history(contexts: list[dict]) -> tuple[list[dict], list[dict]]:
    """Самое новое по ключу — актуальная проверка; остальные уходят в историю."""
    groups: dict[tuple, list[dict]] = {}
    for item in contexts:
        groups.setdefault(item["key"], []).append(item)
    current: list[dict] = []
    ignored: list[dict] = []
    for items in groups.values():
        ordered = sorted(items, key=lambda c: c["sort_key"])
        newest = ordered[-1]
        current.append(newest)
        for old in ordered[:-1]:
            rec = public_context(old)
            if old["conclusion"] == "CANCELLED" and newest["conclusion"] == "SUCCESS":
                rec["ignore_reason"] = "superseded_by_later_success"
                rec["ignore_detail"] = SUPERSEDED_PHRASE
                rec["superseded_by_run_id"] = newest["run_id"]
                rec["superseded_by_name"] = newest["name"]
            else:
                rec["ignore_reason"] = "older_than_current"
                rec["ignore_detail"] = "более старый результат той же проверки"
            ignored.append(rec)
    current.sort(key=lambda c: (c["source"], c["workflow"], c["name"]))
    ignored.sort(key=lambda r: (r["name"], r.get("run_id") or 0))
    return current, ignored


def _result(verdict: str, code: str, reason: str, diag: dict) -> dict:
    # Публичные имена полей из GraphQL + snake-агрегаты: есть в ЛЮБОМ вердикте,
    # включая not_open и ERROR (где данных может не быть).
    diag.setdefault("mergeStateStatus", diag.get("merge_state_status", ""))
    diag.setdefault("mergeable", diag.get("mergeable", ""))
    diag.setdefault("reviewDecision", diag.get("review_decision", ""))
    diag.setdefault("isDraft", diag.get("is_draft", False))
    diag.setdefault("headRefOid", diag.get("head_ref_oid", ""))
    diag.setdefault("baseRefName", diag.get("base_ref_name", ""))
    diag.setdefault("ignored_history", diag.get("ignored_history", []))
    diag.setdefault("blocking", diag.get("blocking", []))
    return {
        "schema": 1,
        "verdict": verdict,
        "code": code,
        "label": f"{verdict}:{code}",
        "reason": reason,
        "exit_code": EXIT[verdict],
        "diagnostics": diag,
    }


def decide(pr: dict, contexts: list[dict], dropped: list[dict] | None = None, page_info: dict | None = None) -> dict:
    """Чистое правило вердикта: без сети и без побочных эффектов."""
    dropped = dropped or []
    page_info = page_info or {}
    number = pr.get("number")
    state = (pr.get("state") or "").upper()
    mergeable = (pr.get("mergeable") or "").upper()
    merge_state = (pr.get("mergeStateStatus") or "").upper()
    review = pr.get("reviewDecision") or ""
    is_draft = bool(pr.get("isDraft"))
    head = pr.get("headRefOid") or ""

    current, ignored = split_history(contexts)
    pending = [public_context(c) for c in current
               if c["status"] != "COMPLETED" or not c["conclusion"]]
    diag = {
        "state": state,
        "merged": bool(pr.get("merged")),
        "is_draft": is_draft,
        "mergeable": mergeable,
        "merge_state_status": merge_state,
        "review_decision": review,
        "base_ref_name": pr.get("baseRefName") or "",
        "head_ref_oid": head,
        "pr_url": pr.get("url") or "",
        "current": [public_context(c) for c in current],
        "ignored_history": ignored,
        "dropped_wrong_head": list(dropped),
        "blocking": [],
        "pending": pending,
        "notes": [],
    }
    if merge_state == "BEHIND":
        diag["notes"].append("mergeStateStatus=BEHIND — диагностика, не блокер (merge commit)")
    if review and review != "APPROVED":
        diag["notes"].append(f"reviewDecision={review} — диагностика, не блокер v1")
    if page_info.get("hasPreviousPage"):
        diag["notes"].append("contexts(last: 100): есть более старые проверки, не загружены")
    if dropped:
        diag["notes"].append(f"отброшено {len(dropped)} контекстов с чужим/неизвестным head SHA")

    if state != "OPEN" or pr.get("merged"):
        return _result("BLOCK", "not_open",
                       f"PR #{number} не открыт (state={state or '?'}, merged={bool(pr.get('merged'))})", diag)
    if is_draft:
        return _result("BLOCK", "draft_pr", "PR — draft: снимите draft перед мержем", diag)
    if mergeable == "CONFLICTING":
        return _result("BLOCK", "conflict", "есть конфликт с базовой веткой", diag)
    if mergeable == "UNKNOWN":
        return _result("WAIT", "unknown_mergeability",
                       "GitHub ещё считает mergeability, повторите через несколько секунд", diag)
    if not current:
        return _result("WAIT", "no_checks",
                       "актуальных проверок HEAD нет (или все отброшены по head SHA) — повторите позже", diag)
    if pending:
        names = ", ".join(sorted(c["name"] for c in pending))
        return _result("WAIT", "pending_checks", f"проверки ещё идут: {names}", diag)

    priorities = {"real_failure": 0, "fresh_cancel_no_success": 1,
                  "external_not_success": 2, "unknown_conclusion": 3}
    blocking: list[dict] = []
    for item in current:
        conclusion, source = item["conclusion"], item["source"]
        reason = detail = ""
        if source != "gha":
            if conclusion != "SUCCESS":
                reason = "external_not_success"
                detail = "внешняя проверка не SUCCESS — консервативно блокируем"
        elif conclusion in BLOCK_CONCLUSIONS:
            reason, detail = "real_failure", "реальный провал проверки GitHub Actions"
        elif conclusion == "CANCELLED":
            reason, detail = "fresh_cancel_no_success", "актуальная проверка отменена: перезапустите проверку"
        elif conclusion not in GHA_OK_CONCLUSIONS:
            reason, detail = "unknown_conclusion", "неизвестный conclusion проверки GitHub Actions"
        if reason:
            rec = public_context(item)
            rec["reason"] = reason
            rec["detail"] = detail
            blocking.append(rec)
    if blocking:
        blocking.sort(key=lambda r: priorities.get(r["reason"], 9))
        diag["blocking"] = blocking
        code = blocking[0]["reason"]
        names = ", ".join(r["name"] for r in blocking)
        return _result("BLOCK", code, f"блокирующие проверки: {names}", diag)

    stale = [i for i in ignored
             if i.get("ignore_reason") == "superseded_by_later_success" and i.get("conclusion") == "CANCELLED"]
    if stale:
        reason = (f"все {len(current)} актуальных проверок HEAD зелёные; "
                  f"{len(stale)} устаревших CANCELLED проигнорированы")
    else:
        reason = f"все {len(current)} актуальных проверок HEAD зелёные; устаревших CANCELLED нет"
    return _result("MERGE", "all_checks_success", reason, diag)


def error_report(code: str, message: str, pr_number: int | None, repo: str | None) -> dict:
    diag = {
        "pr": pr_number, "repo": repo, "state": "", "merged": False, "is_draft": False,
        "mergeable": "", "merge_state_status": "", "review_decision": "",
        "base_ref_name": "", "head_ref_oid": "", "pr_url": "",
        "current": [], "ignored_history": [], "dropped_wrong_head": [],
        "blocking": [], "pending": [], "notes": [message],
    }
    return _result("ERROR", code, message, diag)


def explain_text(report: dict) -> str:
    diag = report.get("diagnostics") or {}
    lines = ["--- diagnostics"]
    for key in ("state", "merged", "mergeStateStatus", "mergeable", "reviewDecision",
                "isDraft", "baseRefName", "headRefOid", "pr_url"):
        if key in diag:
            lines.append(f"{key}: {diag[key]!r}")
    for key, label in (("current", "current"), ("ignored_history", "ignored_history"),
                       ("blocking", "blocking"), ("pending", "pending"),
                       ("dropped_wrong_head", "dropped_wrong_head")):
        items = diag.get(key) or []
        lines.append(f"{label} ({len(items)}):")
        for item in items:
            reason = item.get("ignore_reason") or item.get("reason") or ""
            suffix = f" [{reason}]" if reason else ""
            lines.append(f"  - {item.get('name', '?')} {item.get('conclusion', '')} "
                         f"run={item.get('run_id')}{suffix}")
    for note in diag.get("notes") or []:
        lines.append(f"note: {note}")
    return "\n".join(lines)


def format_report(report: dict, json_mode: bool = False, explain: bool = False) -> str:
    if json_mode:
        return json.dumps(report, ensure_ascii=False, indent=1)
    text = f"{report['label']} — {report['reason']}"
    if explain:
        text += "\n" + explain_text(report)
    return text


def main(argv: list[str] | None = None) -> int:
    # Вывод должен быть UTF-8 и на Windows без PYTHONUTF8: --json пайпится как есть.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(
        description="Вердикт по PR: MERGE / BLOCK / WAIT. Мерж не выполняется.")
    parser.add_argument("--pr", type=int, required=True, help="номер PR")
    parser.add_argument("--repo", help="owner/repo (по умолчанию из git remote origin)")
    parser.add_argument("--json", action="store_true", help="машиночитаемый вывод в stdout")
    parser.add_argument("--explain", action="store_true", help="диагностика в текстовом выводе")
    parser.add_argument("--timeout", type=float, default=30.0, help="таймаут gh, секунд")
    args = parser.parse_args(argv)

    repo = None
    try:
        repo = resolve_repo(args.repo, args.timeout)
        _log(f"PR #{args.pr} в {repo}: читаю GitHub через gh")
        pr = fetch_pr(args.pr, repo, args.timeout)
        rollup = pr.get("statusCheckRollup") or {}
        contexts = rollup.get("contexts") or {}
        normalized, dropped = normalize_contexts(contexts.get("nodes"), pr.get("headRefOid") or "")
        report = decide(pr, normalized, dropped, contexts.get("pageInfo"))
        report["repo"] = repo
        _log(f"вердикт {report['label']}")
    except GateError as exc:
        _log(str(exc))
        report = error_report(exc.code, str(exc), args.pr, repo)
    print(format_report(report, args.json, args.explain))
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
