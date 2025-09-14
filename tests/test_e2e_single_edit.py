"""
End-to-End Tests for Single Edit Script

This module tests the complete E2E single edit workflow including:
- Script execution with various parameters
- Analytics recording
- Integration with the patcher system
- Error handling and edge cases

These are golden tests that verify the complete pipeline works correctly.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestE2ESingleEdit(unittest.TestCase):
    """Test cases for the E2E single edit script"""

    def setUp(self):
        """Set up a temporary git repository for each test"""
        # Create temp directory
        self.temp_dir = tempfile.mkdtemp(prefix="e2e_test_")
        self.original_cwd = os.getcwd()

        # Change to temp directory
        os.chdir(self.temp_dir)

        # Initialize git repo
        subprocess.run(["git", "init"], check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], check=True)

        # Copy the app module structure
        app_dir = Path("app")
        app_dir.mkdir()
        dgm_dir = app_dir / "dgm"
        dgm_dir.mkdir()

        # Create __init__.py files
        (app_dir / "__init__.py").write_text("")
        (dgm_dir / "__init__.py").write_text("")

        # Copy necessary modules from original repo
        original_repo = Path(self.original_cwd)

        # Copy patcher module
        shutil.copy2(
            original_repo / "app" / "dgm" / "patcher.py", dgm_dir / "patcher.py"
        )

        # Create minimal analytics module for testing
        analytics_content = '''
"""Minimal analytics module for E2E testing"""

def record_edits_apply(run_id, result):
    """Record analytics for edits application"""
    print(f"Analytics: run_id={run_id}, ok={result.get('ok')}, edits={result.get('edits_count', 0)}")
    return True
'''
        (dgm_dir / "analytics.py").write_text(analytics_content)

        # Copy scripts directory
        scripts_dir = Path("scripts")
        scripts_dir.mkdir()
        shutil.copy2(
            original_repo / "scripts" / "e2e_single_edit.py",
            scripts_dir / "e2e_single_edit.py",
        )

        # Create initial test file
        self.test_file = "app/config.py"
        Path(self.test_file).parent.mkdir(exist_ok=True)
        with open(self.test_file, "w") as f:
            f.write("X = 1\nY = 2\nZ = 3\n")

        # Make initial commit
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], check=True)

    def tearDown(self):
        """Clean up temporary directory"""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)

    def test_basic_single_edit(self):
        """Test basic single edit execution"""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/e2e_single_edit.py",
                "--path",
                self.test_file,
                "--match",
                "X = 1",
                "--replace",
                "X = 10",
                "--goal",
                "test_basic",
                "--model",
                "test_model",
                "--run-id",
                "TEST001",
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, f"Script failed: {result.stderr}")

        # Verify file was modified
        with open(self.test_file, "r") as f:
            content = f.read()
        self.assertIn("X = 10", content)
        self.assertNotIn("X = 1\n", content)

        # Verify git commit was made
        git_log = subprocess.run(
            ["git", "log", "--oneline"], capture_output=True, text=True
        )
        self.assertIn("test_basic", git_log.stdout)

    def test_multiline_edit(self):
        """Test editing with newlines in match/replace"""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/e2e_single_edit.py",
                "--path",
                self.test_file,
                "--match",
                "Y = 2\\nZ = 3",
                "--replace",
                "Y = 20\\nZ = 30",
                "--goal",
                "test_multiline",
                "--model",
                "test_model",
                "--run-id",
                "TEST002",
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, f"Script failed: {result.stderr}")

        # Verify both lines were modified
        with open(self.test_file, "r") as f:
            content = f.read()
        self.assertIn("Y = 20", content)
        self.assertIn("Z = 30", content)

    def test_match_not_found(self):
        """Test error handling when match string is not found"""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/e2e_single_edit.py",
                "--path",
                self.test_file,
                "--match",
                "DOES_NOT_EXIST",
                "--replace",
                "replacement",
                "--goal",
                "test_not_found",
                "--model",
                "test_model",
                "--run-id",
                "TEST003",
            ],
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0, "Script should have failed")
        self.assertIn("FAILED", result.stdout)

    def test_missing_file(self):
        """Test error handling for non-existent file"""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/e2e_single_edit.py",
                "--path",
                "nonexistent.py",
                "--match",
                "anything",
                "--replace",
                "replacement",
                "--goal",
                "test_missing",
                "--model",
                "test_model",
                "--run-id",
                "TEST004",
            ],
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0, "Script should have failed")

    def test_custom_area_and_rationale(self):
        """Test using custom area and rationale parameters"""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/e2e_single_edit.py",
                "--path",
                self.test_file,
                "--match",
                "Z = 3",
                "--replace",
                "Z = 300",
                "--goal",
                "test_custom",
                "--model",
                "test_model",
                "--run-id",
                "TEST005",
                "--area",
                "custom_area",
                "--rationale",
                "custom test rationale",
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, f"Script failed: {result.stderr}")

        # Verify custom area is in output
        self.assertIn("custom_area", result.stdout)
        self.assertIn("custom test rationale", result.stdout)

    def test_from_scripts_directory(self):
        """Test running the script from the scripts directory"""
        os.chdir("scripts")

        result = subprocess.run(
            [
                sys.executable,
                "e2e_single_edit.py",
                "--path",
                f"../{self.test_file}",
                "--match",
                "Y = 2",
                "--replace",
                "Y = 200",
                "--goal",
                "test_from_scripts",
                "--model",
                "test_model",
                "--run-id",
                "TEST006",
            ],
            capture_output=True,
            text=True,
        )

        # Change back for proper cleanup
        os.chdir("..")

        self.assertEqual(result.returncode, 0, f"Script failed: {result.stderr}")

        # Verify file was modified
        with open(self.test_file, "r") as f:
            content = f.read()
        self.assertIn("Y = 200", content)

    def test_analytics_integration(self):
        """Test that analytics recording is called"""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/e2e_single_edit.py",
                "--path",
                self.test_file,
                "--match",
                "X = 1",
                "--replace",
                "X = 1000",
                "--goal",
                "test_analytics",
                "--model",
                "analytics_test_model",
                "--run-id",
                "ANALYTICS001",
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, f"Script failed: {result.stderr}")

        # Verify analytics output appears
        self.assertIn("Analytics:", result.stdout)
        self.assertIn("ANALYTICS001", result.stdout)

    def test_success_summary(self):
        """Test that success summary is displayed"""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/e2e_single_edit.py",
                "--path",
                self.test_file,
                "--match",
                "Z = 3",
                "--replace",
                "Z = 3000",
                "--goal",
                "test_summary",
                "--model",
                "summary_test_model",
                "--run-id",
                "SUMMARY001",
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, f"Script failed: {result.stderr}")

        # Verify success summary elements
        self.assertIn("E2E Success Summary", result.stdout)
        self.assertIn("Applied 1 edits", result.stdout)
        self.assertIn("Modified 1 files", result.stdout)
        self.assertIn("Analytics recorded", result.stdout)

    def test_json_output_structure(self):
        """Test that the patcher result has the expected JSON structure"""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/e2e_single_edit.py",
                "--path",
                self.test_file,
                "--match",
                "X = 1",
                "--replace",
                "X = 9999",
                "--goal",
                "test_json",
                "--model",
                "json_test_model",
                "--run-id",
                "JSON001",
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, f"Script failed: {result.stderr}")

        # Extract JSON from output
        lines = result.stdout.split("\n")
        json_section = False
        json_lines = []

        for line in lines:
            if "Patcher Result" in line:
                json_section = True
                continue
            elif json_section and line.strip() and not line.startswith("="):
                json_lines.append(line)
            elif json_section and line.startswith("="):
                break

        if json_lines:
            try:
                json_str = "\n".join(json_lines)
                result_data = json.loads(json_str)

                # Verify expected fields
                self.assertTrue(result_data.get("ok"))
                self.assertIn("diffs", result_data)
                self.assertIn("touched", result_data)
                self.assertIn("file_shas", result_data)
                self.assertEqual(len(result_data["touched"]), 1)

            except json.JSONDecodeError as e:
                self.fail(f"Invalid JSON in result: {e}")

    def test_help_message(self):
        """Test that help message is displayed correctly"""
        result = subprocess.run(
            [sys.executable, "scripts/e2e_single_edit.py", "--help"],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("Run a single end-to-end edit cycle", result.stdout)
        self.assertIn("--path", result.stdout)
        self.assertIn("--match", result.stdout)
        self.assertIn("--replace", result.stdout)
        self.assertIn("Examples:", result.stdout)

    def test_special_characters_in_strings(self):
        """Test handling of special characters in match/replace strings"""
        # Create a file with special characters
        special_file = "app/special.py"
        with open(special_file, "w") as f:
            f.write('pattern = r"\\d+"\nquote = "hello"\n')

        subprocess.run(["git", "add", special_file], check=True)
        subprocess.run(["git", "commit", "-m", "Add special chars file"], check=True)

        result = subprocess.run(
            [
                sys.executable,
                "scripts/e2e_single_edit.py",
                "--path",
                special_file,
                "--match",
                'pattern = r"\\\\d+"',
                "--replace",
                'pattern = r"\\\\w+"',
                "--goal",
                "test_special",
                "--model",
                "special_test_model",
                "--run-id",
                "SPECIAL001",
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, f"Script failed: {result.stderr}")

        # Verify the change
        with open(special_file, "r") as f:
            content = f.read()
        self.assertIn('r"\\w+"', content)


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)
