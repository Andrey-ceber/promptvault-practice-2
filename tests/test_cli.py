import subprocess
import sys
import unittest


class CLITests(unittest.TestCase):
    def test_module_has_help_with_safe_defaults(self):
        result = subprocess.run([sys.executable, '-m', 'promptvault', '--help'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--db', result.stdout)
        self.assertIn('--port', result.stdout)
        self.assertIn('127.0.0.1', result.stdout)
