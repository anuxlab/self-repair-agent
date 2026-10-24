import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBLEM_DIR = ROOT / "problems"

class ProblemSpecTests(unittest.TestCase):
    def test_every_problem_spec_has_required_metadata(self):
        specs = sorted(PROBLEM_DIR.glob("*.json"))
        self.assertGreaterEqual(len(specs), 20)
        names = set()
        for path in specs:
            with self.subTest(problem=path.name):
                spec = json.loads(path.read_text(encoding="utf-8"))
                self.assertTrue(spec.get("name"))
                self.assertNotIn(spec["name"], names, f"duplicate function name: {spec['name']}")
                names.add(spec["name"])
                self.assertIn(spec.get("difficulty"), {"easy", "easy-medium", "medium", "medium-hard", "hard"})
                self.assertTrue(spec.get("statement"))
                self.assertTrue(spec.get("bug_family"))
                self.assertTrue(spec.get("difficulty_rubric"))
                self.assertGreaterEqual(len(spec.get("tests", [])), 5)
                for case in spec["tests"]:
                    self.assertIn("args", case)
                    self.assertIn("expected", case)
                    self.assertTrue(case.get("category"), f"missing category in {path.name}")

    def test_problem_corpus_covers_graphs_and_dynamic_programming(self):
        specs = [json.loads(p.read_text(encoding="utf-8")) for p in PROBLEM_DIR.glob("*.json")]
        families = {s["bug_family"] for s in specs}
        self.assertTrue(any("dynamic_programming" in family for family in families))
        self.assertTrue(any("graph" in family or "shortest_path" in family for family in families))
        self.assertTrue(any("shortest_path" in family for family in families))

if __name__ == "__main__":
    unittest.main()
