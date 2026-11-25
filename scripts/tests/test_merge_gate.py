# -*- coding: utf-8 -*-
"""Юнит-тесты гейта мержа: только чистые функции, без сети и gh.

Запуск: python -m unittest discover -s scripts/tests -p 'test_merge_gate*.py'
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
scripts = HERE.parent
sys.path.insert(0, str(scripts))
import merge_gate as G  # noqa: E402

FIXTURE = HERE / "fixtures" / "merge_gate_pr4.json"
HEAD = "a" * 40
OTHER = "b" * 40


def fixture_pr() -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return copy.deepcopy(payload["data"]["repository"]["pullRequest"])


def make_pr(**overrides) -> dict:
    pr = {
        "number": 7, "url": "https://github.com/o/r/pull/7", "state": "OPEN",
        "isDraft": False, "merged": False, "mergeable": "MERGEABLE",
        "mergeStateStatus": "UNSTABLE", "headRefOid": HEAD, "baseRefName": "master",
        "reviewDecision": None,
        "statusCheckRollup": {"contexts": {
            "pageInfo": {"hasPreviousPage": False}, "nodes": [],
        }},
    }
    pr.update(overrides)
    return pr


def check(name: str, conclusion="SUCCESS", status="COMPLETED", run_id=1,
          started="2026-01-01T00:00:00Z", completed="2026-01-01T00:01:00Z",
          workflow="smoke", app="github-actions", oid=HEAD, job_id=10) -> dict:
    return {
        "__typename": "CheckRun", "name": name, "status": status,
        "conclusion": conclusion, "startedAt": started, "completedAt": completed,
        "detailsUrl": f"https://github.com/o/r/actions/runs/{run_id}/job/{job_id}",
        "checkSuite": {
            "commit": {"oid": oid},
            "app": {"slug": app},
            "workflowRun": {"workflow": {"name": workflow}},
        },
    }


def status_check(context: str, state="SUCCESS", oid=HEAD,
                 target="https://ci.example.com/build/1") -> dict:
    return {
        "__typename": "StatusContext", "context": context, "state": state,
        "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:01:00Z",
        "targetUrl": target, "commit": {"oid": oid},
    }


def with_nodes(pr: dict, nodes: list[dict]) -> dict:
    pr = copy.deepcopy(pr)
    pr["statusCheckRollup"]["contexts"]["nodes"] = nodes
    return pr


def verdict(pr: dict) -> dict:
    rollup = pr.get("statusCheckRollup") or {}
    contexts = rollup.get("contexts") or {}
    normalized, dropped = G.normalize_contexts(contexts.get("nodes"), pr.get("headRefOid") or "")
    return G.decide(pr, normalized, dropped, contexts.get("pageInfo"))


class MergeGateFixtureTest(unittest.TestCase):
    def test_fixture_keeps_all_contexts_and_non_ascii_job(self):
        pr = fixture_pr()
        contexts, dropped = G.normalize_contexts(
            pr["statusCheckRollup"]["contexts"]["nodes"], pr["headRefOid"])
        self.assertEqual(len(contexts), 10)
        self.assertEqual(dropped, [])
        names = {c["name"] for c in contexts}
        self.assertIn("полный прогон 3.15 (installer/requirements.txt + модели от Stanford)", names)
        self.assertEqual({c["run_id"] for c in contexts},
                         {45633300682, 45633300829, 45633346827, 45633347190})
        self.assertTrue(all(c["source"] == "gha" for c in contexts))

    def test_fixture_pr4_merged_is_not_open(self):
        report = verdict(fixture_pr())
        self.assertEqual(report["label"], "BLOCK:not_open")
        self.assertEqual(report["exit_code"], 1)
        self.assertIn("state=MERGED", report["reason"])

    def test_fixture_stale_cancelled_allows_merge_when_open(self):
        pr = fixture_pr()
        pr.update(state="OPEN", merged=False, mergeable="MERGEABLE",
                  mergeStateStatus="UNSTABLE", reviewDecision=None)
        report = verdict(pr)
        self.assertEqual(report["label"], "MERGE:all_checks_success")
        self.assertEqual(report["exit_code"], 0)
        self.assertIn("3 устаревших CANCELLED проигнорированы", report["reason"])

        diag = report["diagnostics"]
        self.assertEqual(diag["merge_state_status"], "UNSTABLE")
        self.assertEqual(len(diag["current"]), 5)
        stale = [i for i in diag["ignored_history"]
                 if i.get("ignore_reason") == "superseded_by_later_success"]
        self.assertEqual(len(stale), 3)
        self.assertEqual({i["name"] for i in stale}, {
            "smoke (windows-latest)",
            "полный прогон 3.15 (installer/requirements.txt + модели от Stanford)",
            "install.ps1 / all.ps1 — текущий контракт (Windows)",
        })
        self.assertTrue(all(i["conclusion"] == "CANCELLED" for i in stale))
        self.assertTrue(all(i["superseded_by_run_id"] == 45633347190 for i in stale))
        self.assertTrue(all(i["ignore_detail"] == G.SUPERSEDED_PHRASE for i in stale))
        self.assertEqual(diag["blocking"], [])


class MergeGateRulesTest(unittest.TestCase):
    def test_latest_cancelled_blocks_even_if_older_was_green(self):
        pr = with_nodes(make_pr(), [
            check("smoke", "SUCCESS", run_id=1, started="2026-01-01T00:00:00Z"),
            check("smoke", "CANCELLED", run_id=2, started="2026-01-01T00:05:00Z"),
        ])
        report = verdict(pr)
        self.assertEqual(report["label"], "BLOCK:fresh_cancel_no_success")
        self.assertIn("перезапустите", report["diagnostics"]["blocking"][0]["detail"])
        older = report["diagnostics"]["ignored_history"][0]
        self.assertEqual(older["ignore_reason"], "older_than_current")

    def test_real_failure_blocks_above_stale_cancelled(self):
        pr = with_nodes(make_pr(), [
            check("smoke", "CANCELLED", run_id=1),
            check("smoke", "SUCCESS", run_id=2, started="2026-01-01T00:02:00Z"),
            check("contract", "FAILURE", run_id=3),
        ])
        report = verdict(pr)
        self.assertEqual(report["label"], "BLOCK:real_failure")
        self.assertEqual(len([i for i in report["diagnostics"]["ignored_history"]
                              if i["ignore_reason"] == "superseded_by_later_success"]), 1)

    def test_in_progress_waits(self):
        pr = with_nodes(make_pr(), [
            check("contract", "SUCCESS"),
            check("smoke", status="IN_PROGRESS", conclusion=None, run_id=2),
        ])
        report = verdict(pr)
        self.assertEqual(report["label"], "WAIT:pending_checks")
        self.assertEqual(report["exit_code"], 2)
        self.assertIn("smoke", report["reason"])

    def test_conflict_blocks(self):
        pr = with_nodes(make_pr(mergeable="CONFLICTING"), [check("contract")])
        self.assertEqual(verdict(pr)["label"], "BLOCK:conflict")

    def test_unknown_mergeability_waits(self):
        pr = with_nodes(make_pr(mergeable="UNKNOWN"), [check("contract")])
        report = verdict(pr)
        self.assertEqual(report["label"], "WAIT:unknown_mergeability")
        self.assertIn("повторите через несколько секунд", report["reason"])

    def test_no_checks_waits(self):
        report = verdict(make_pr())
        self.assertEqual(report["label"], "WAIT:no_checks")
        self.assertEqual(report["exit_code"], 2)

    def test_draft_blocks(self):
        pr = with_nodes(make_pr(isDraft=True), [check("contract")])
        self.assertEqual(verdict(pr)["label"], "BLOCK:draft_pr")

    def test_external_status_cancelled_blocks(self):
        pr = with_nodes(make_pr(), [status_check("ci/external", "CANCELLED")])
        report = verdict(pr)
        self.assertEqual(report["label"], "BLOCK:external_not_success")
        self.assertEqual(report["diagnostics"]["blocking"][0]["source"], "external")

    def test_external_checkrun_neutral_blocks(self):
        pr = with_nodes(make_pr(), [check("external", "NEUTRAL", app="circleci", workflow="")])
        self.assertEqual(verdict(pr)["label"], "BLOCK:external_not_success")

    def test_gha_skipped_and_neutral_are_ok(self):
        pr = with_nodes(make_pr(), [
            check("a", "SKIPPED", run_id=1),
            check("b", "NEUTRAL", run_id=2),
        ])
        report = verdict(pr)
        self.assertEqual(report["label"], "MERGE:all_checks_success")
        self.assertEqual(report["diagnostics"]["blocking"], [])

    def test_wrong_head_is_dropped(self):
        pr = with_nodes(make_pr(), [check("contract", oid=OTHER)])
        report = verdict(pr)
        self.assertEqual(report["label"], "WAIT:no_checks")
        dropped = report["diagnostics"]["dropped_wrong_head"]
        self.assertEqual(len(dropped), 1)
        self.assertEqual(dropped[0]["reason"], "wrong_head")

    def test_missing_head_oid_is_dropped(self):
        node = check("contract")
        node["checkSuite"]["commit"]["oid"] = ""
        report = verdict(with_nodes(make_pr(), [node]))
        self.assertEqual(report["diagnostics"]["dropped_wrong_head"][0]["reason"], "missing_head_oid")
        self.assertEqual(report["label"], "WAIT:no_checks")

    def test_same_name_in_different_workflows_is_not_grouped(self):
        pr = with_nodes(make_pr(), [
            check("job", "CANCELLED", run_id=1, workflow="one"),
            check("job", "SUCCESS", run_id=2, started="2026-01-01T00:02:00Z", workflow="two"),
        ])
        report = verdict(pr)
        self.assertEqual(len(report["diagnostics"]["current"]), 2)
        self.assertEqual(report["label"], "BLOCK:fresh_cancel_no_success")

    def test_behind_and_review_are_diagnostics_only(self):
        pr = with_nodes(make_pr(mergeStateStatus="BEHIND", reviewDecision="CHANGES_REQUESTED"),
                        [check("contract")])
        report = verdict(pr)
        self.assertEqual(report["label"], "MERGE:all_checks_success")
        notes = " ".join(report["diagnostics"]["notes"])
        self.assertIn("BEHIND", notes)
        self.assertIn("CHANGES_REQUESTED", notes)

    def test_run_id_order_wins_over_timestamp(self):
        pr = with_nodes(make_pr(), [
            check("contract", "SUCCESS", run_id=1, started="2026-01-02T00:00:00Z"),
            check("contract", "CANCELLED", run_id=2, started="2026-01-01T00:00:00Z"),
        ])
        self.assertEqual(verdict(pr)["label"], "BLOCK:fresh_cancel_no_success")

    def test_not_open_and_error_reports_have_full_diagnostics(self):
        for report in (verdict(fixture_pr()),
                       G.error_report("gh_error", "boom", 4, "o/r")):
            diag = report["diagnostics"]
            for key in ("mergeStateStatus", "mergeable", "reviewDecision", "isDraft",
                        "headRefOid", "ignored_history", "blocking"):
                self.assertIn(key, diag, report["label"])

    def test_report_shape_and_formatting(self):
        report = verdict(with_nodes(make_pr(), [check("contract")]))
        for key in ("schema", "verdict", "code", "label", "reason", "exit_code", "diagnostics"):
            self.assertIn(key, report)
        diag = report["diagnostics"]
        for key in ("state", "is_draft", "mergeable", "merge_state_status", "review_decision",
                    "base_ref_name", "ignored_history", "blocking", "current",
                    "mergeStateStatus", "mergeable", "reviewDecision", "isDraft",
                    "headRefOid", "baseRefName"):
            self.assertIn(key, diag)
        payload = json.loads(G.format_report(report, json_mode=True))
        self.assertEqual(payload["label"], "MERGE:all_checks_success")
        self.assertIn("MERGE:all_checks_success", G.format_report(report))
        self.assertIn("--- diagnostics", G.format_report(report, explain=True))
        self.assertEqual(G.EXIT[report["verdict"]], 0)


class MergeGateRepoTest(unittest.TestCase):
    def test_parse_repo_from_https_and_ssh(self):
        self.assertEqual(
            G.parse_repo_from_url("https://github.com/ppogrebnoj/stanza-german-ppl.git"),
            "ppogrebnoj/stanza-german-ppl")
        self.assertEqual(
            G.parse_repo_from_url("git@github.com:ppogrebnoj/stanza-german-ppl.git"),
            "ppogrebnoj/stanza-german-ppl")

    def test_bad_repo_raises_gate_error(self):
        with self.assertRaises(G.GateError) as caught:
            G.parse_repo_from_url("https://example.com/o/r.git")
        self.assertEqual(caught.exception.code, "bad_repo")


if __name__ == "__main__":
    unittest.main()
