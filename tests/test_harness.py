import json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests" / "run_cases.py"
class HarnessTests(unittest.TestCase):
    def run_case(self, code, spec_name):
        with tempfile.TemporaryDirectory() as td:
            code_path = Path(td) / "solution.py"
            code_path.write_text(code)
            spec_path = ROOT / "problems" / f"{spec_name}.json"
            proc = subprocess.run([sys.executable, str(RUNNER), str(code_path), str(spec_path)], capture_output=True, text=True)
            return json.loads(proc.stdout.strip().splitlines()[-1])
    def test_empty_solution_fails(self):
        result = self.run_case("# nothing here\n", "01_easy")
        self.assertFalse(result["passed"])
    def test_correct_add_passes(self):
        result = self.run_case("def add(a, b):\n    return a + b\n", "01_easy")
        self.assertTrue(result["passed"])
    def test_wrong_palindrome_fails(self):
        result = self.run_case("def is_palindrome(s):\n    return s == s[::-1]\n", "02_easy_medium")
        self.assertFalse(result["passed"])
    def test_correct_palindrome_passes(self):
        result = self.run_case("def is_palindrome(s):\n    t = ''.join(c.lower() for c in s if c.isalnum())\n    return t == t[::-1]\n", "02_easy_medium")
        self.assertTrue(result["passed"])
    def test_correct_two_sum_passes(self):
        result = self.run_case("def two_sum(nums, target):\n    seen = {}\n    for i, x in enumerate(nums):\n        if target-x in seen: return [seen[target-x], i]\n        seen[x] = i\n", "03_medium")
        self.assertTrue(result["passed"])
    def test_all_negative_kadane(self):
        result = self.run_case("def max_subarray(nums):\n    best = cur = nums[0]\n    for x in nums[1:]:\n        cur = max(x, cur+x)\n        best = max(best, cur)\n    return best\n", "04_medium_hard")
        self.assertTrue(result["passed"])
    def test_correct_trapping_rain_water_passes(self):
        code = "def trap_rain_water(height):\n    l, r = 0, len(height)-1\n    left = right = water = 0\n    while l < r:\n        if height[l] < height[r]:\n            left = max(left, height[l]); water += left-height[l]; l += 1\n        else:\n            right = max(right, height[r]); water += right-height[r]; r -= 1\n    return water\n"
        result = self.run_case(code, "05_hard")
        self.assertTrue(result["passed"])
if __name__ == "__main__": unittest.main()
