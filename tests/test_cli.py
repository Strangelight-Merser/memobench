import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from collections import Counter

from memobench.schema import Case


ROOT = Path(__file__).resolve().parents[1]
SYSTEMS = ("full_context", "sliding_window", "bm25_rag", "profile_store")
CATEGORIES = {"recall", "update", "multi", "temporal", "forget", "abstain"}


class CLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def cli(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(ROOT), env.get("PYTHONPATH"))))
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run([sys.executable, "-m", "memobench.cli", *args],
                                cwd=self.directory, env=env, capture_output=True,
                                text=True, encoding="utf-8", timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def check_report(self, directory, n):
        summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(set(summary), set(SYSTEMS))
        for system, metrics in summary.items():
            with self.subTest(system=system):
                self.assertTrue(CATEGORIES.issubset(metrics))
                for key in CATEGORIES | {"overall", "leak_rate"}:
                    self.assertGreaterEqual(metrics[key], 0)
                    self.assertLessEqual(metrics[key], 1)
                self.assertGreaterEqual(metrics["avg_ctx"], 0)
                self.assertGreaterEqual(metrics["avg_ms"], 0)
        report = (directory / "report.html").read_text(encoding="utf-8")
        self.assertIn("MemoBench", report)
        self.assertIn("<html", report.lower())
        for system in SYSTEMS:
            self.assertIn(system, report)
        results = [json.loads(line) for line in
                   (directory / "results.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(results), n * 6 * len(SYSTEMS))
        self.assertEqual(Counter((r["system"], r["category"]) for r in results),
                         {(s, c): n for s in SYSTEMS for c in CATEGORIES})

    def test_generate_then_run_saved_dataset(self):
        dataset = self.directory / "data" / "cases.jsonl"
        self.cli("generate", "-n", "2", "--seed", "17", "-o", str(dataset))
        cases = [Case.from_dict(json.loads(line)) for line in
                 dataset.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(cases), 12)
        self.assertEqual(Counter(c.category for c in cases), {c: 2 for c in CATEGORIES})
        output = self.directory / "saved-report"
        self.cli("run", "--data", str(dataset), "--systems", ",".join(SYSTEMS),
                 "--out", str(output))
        self.check_report(output, 2)

    def test_run_generates_dataset_in_memory(self):
        output = self.directory / "generated-report"
        self.cli("run", "-n", "1", "--seed", "17", "--systems", ",".join(SYSTEMS),
                 "--out", str(output))
        self.check_report(output, 1)
