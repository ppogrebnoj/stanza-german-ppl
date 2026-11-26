# -*- coding: utf-8 -*-
"""Тесты единой точки запуска Python-проверок: без сети и без реальных медленных проверок."""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import run_checks as R  # noqa: E402


class RunnerTest(unittest.TestCase):
    def test_manifest_matches_flags_registry(self):
        manifest = R.load_manifest()
        names = R.list_names(manifest)
        reg = json.loads((R.ROOT / "docs" / "flags.json").read_text(encoding="utf-8"))
        check_values = next(f["values"] for f in reg["flags"] if f["name"] == "Check")
        for name in names:
            self.assertIn(name, reg["checks"])
            self.assertIn(name, check_values)
        self.assertNotIn("ready", reg["checks"])

    def test_manifest_paths_exist(self):
        for item in R.load_manifest()["checks"]:
            self.assertTrue((R.CHECKS_DIR / item["path"]).is_file(), item["path"])

    def test_old_check_paths_are_gone(self):
        for rel in ("scripts/doctor.py", "scripts/check_models.py",
                    "scripts/acceptance.py", "scripts/mcp_probe.py",
                    "scripts/server_check.py"):
            with self.subTest(rel=rel):
                self.assertFalse((R.ROOT / rel).exists())

    def test_tool_names_are_distinct(self):
        names = R.list_names()
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("mcp_probe", names)
        self.assertIn("server_check", names)
        self.assertIn("mcp", json.loads((R.ROOT / "docs" / "flags.json").read_text(
            encoding="utf-8"))["checks"])

    def test_unknown_check_is_broken_with_code_4(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = R.main(["--check", "nope", "--json"])
        self.assertEqual(rc, 4)
        report = json.loads(out.getvalue())
        self.assertEqual(report["status"], "BROKEN")
        self.assertEqual(report["code"], 4)

    def test_missing_check_argument_is_broken(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = R.main(["--json"])
        self.assertEqual(rc, 4)
        self.assertEqual(json.loads(out.getvalue())["code"], 4)

    def test_list_is_available_without_python_guard(self):
        with mock.patch.object(R, "python_ok", return_value=False):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = R.main(["--list", "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(set(json.loads(out.getvalue())),
                         {"doctor", "models", "acceptance", "mcp_probe", "server_check"})

    def test_python_guard_blocks_run(self):
        with mock.patch.object(R, "python_ok", return_value=False):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = R.main(["--check", "doctor", "--json"])
        self.assertEqual(rc, 2)
        self.assertEqual(json.loads(out.getvalue())["status"], "BLOCK")

    def test_runner_adds_json_and_uses_manifest_path(self):
        proc = subprocess.CompletedProcess(args=[], returncode=0,
                                           stdout='{"ok": true, "counts": {"OK": 2}}', stderr="")
        with mock.patch.object(R, "python_ok", return_value=True), \
             mock.patch.object(R.subprocess, "run", return_value=proc) as run:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = R.main(["--check", "doctor", "--json"])
        self.assertEqual(rc, 0)
        cmd = run.call_args.args[0]
        self.assertIn(str(R.CHECKS_DIR / "doctor.py"), cmd)
        self.assertIn("--json", cmd)
        report = json.loads(out.getvalue())
        self.assertEqual(report["status"], "OK")
        self.assertEqual(report["data"]["counts"]["OK"], 2)

    def test_warn_does_not_change_doctor_exit(self):
        data = {"ok": True, "counts": {"OK": 8, "WARN": 2, "FAIL": 0}}
        report = R.map_result("doctor", 0, data)
        self.assertEqual(report["status"], "OK")
        self.assertEqual(report["exit_code"], 0)
        self.assertIn("WARN", report["detail"])

    def test_mcp_probe_rc2_is_block(self):
        report = R.map_result("mcp_probe", 2, {"ok": False, "problems": ["нет пакета mcp"]})
        self.assertEqual(report["status"], "BLOCK")
        self.assertEqual(report["exit_code"], 2)

    def test_timeout_is_retryable(self):
        report = R.map_result("models", 124, None, timed_out=True)
        self.assertEqual(report["exit_code"], 3)
        self.assertEqual(report["status"], "FAIL")

    def test_missing_json_on_zero_is_broken(self):
        report = R.map_result("acceptance", 0, None)
        self.assertEqual(report["exit_code"], 4)

    def test_missing_check_file_is_delivery(self):
        entry = {"name": "doctor", "path": "installer/lib/checks/nope.py", "timeout_s": 5}
        report = R.run_check(entry, [])
        self.assertEqual(report["exit_code"], 5)

    def test_server_check_sees_all_tools(self):
        sys.path.insert(0, str(R.CHECKS_DIR))
        import server_check  # noqa: E402
        self.assertEqual(set(server_check.tools_from_ast()), server_check.NEED)

    def test_workflows_compileall_include_checks(self):
        for rel in (".github/workflows/smoke.yml", ".github/workflows/contract.yml"):
            with self.subTest(rel=rel):
                text = (R.ROOT / rel).read_text(encoding="utf-8-sig")
                lines = [ln for ln in text.splitlines() if "compileall" in ln]
                self.assertTrue(lines, rel)
                self.assertTrue(any("installer/lib/checks" in ln for ln in lines), rel)

    def test_install_dispatch_has_server_check(self):
        text = (R.ROOT / "installer" / "install.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("'server_check' { Invoke-CheckRunner 'server_check' }", text)


if __name__ == "__main__":
    unittest.main()
