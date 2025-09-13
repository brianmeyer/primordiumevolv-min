"""
Test suite for the edit-based patcher module

This test suite uses hermetic git repositories to test the patcher functionality
in isolation without affecting the main repository.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

# Import the patcher module
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.dgm.patcher import apply_edits_package, apply_one_edit, synth_unified_diff, git_apply_check


class TestPatcher(unittest.TestCase):
    """Test cases for the edit-based patcher"""

    def setUp(self):
        """Set up a temporary git repository for each test"""
        # Create temp directory
        self.temp_dir = tempfile.mkdtemp(prefix='patcher_test_')
        self.original_cwd = os.getcwd()

        # Change to temp directory
        os.chdir(self.temp_dir)

        # Initialize git repo
        subprocess.run(['git', 'init'], check=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.com'], check=True)
        subprocess.run(['git', 'config', 'user.name', 'Test User'], check=True)

        # Create initial test file
        self.test_file = 'test_config.py'
        with open(self.test_file, 'w') as f:
            f.write('X = 1\nY = 2\nZ = 3\n')

        # Make initial commit
        subprocess.run(['git', 'add', self.test_file], check=True)
        subprocess.run(['git', 'commit', '-m', 'Initial commit'], check=True)

    def tearDown(self):
        """Clean up temporary directory"""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)

    def test_exact_string_match(self):
        """Test exact string matching edit"""
        edits_package = {
            "area": "test",
            "goal_tag": "change_x",
            "rationale": "update X value",
            "edits": [
                {
                    "path": self.test_file,
                    "match": "X = 1",
                    "replace": "X = 10"
                }
            ]
        }

        result = apply_edits_package(
            json.dumps(edits_package),
            model_name="test_model",
            goal_tag="change_x"
        )

        self.assertTrue(result["ok"])
        self.assertIn(self.test_file, result["touched"])

        # Verify file content
        with open(self.test_file, 'r') as f:
            content = f.read()
        self.assertIn("X = 10", content)
        self.assertNotIn("X = 1", content)

    def test_regex_match(self):
        """Test regex pattern matching edit"""
        edits_package = {
            "area": "test",
            "goal_tag": "regex_test",
            "rationale": "update using regex",
            "edits": [
                {
                    "path": self.test_file,
                    "match_re": r"Y = (\d+)",
                    "group_replacement": r"Y = \g<1>0"
                }
            ]
        }

        result = apply_edits_package(
            json.dumps(edits_package),
            model_name="test_model",
            goal_tag="regex_test"
        )

        self.assertTrue(result["ok"])

        # Verify file content
        with open(self.test_file, 'r') as f:
            content = f.read()
        self.assertIn("Y = 20", content)

    def test_multiline_content(self):
        """Test handling of multiline content"""
        # Create a file with multiline content
        multiline_file = 'multiline.py'
        with open(multiline_file, 'w') as f:
            f.write('def function():\n    x = 1\n    return x\n')

        subprocess.run(['git', 'add', multiline_file], check=True)
        subprocess.run(['git', 'commit', '-m', 'Add multiline file'], check=True)

        edits_package = {
            "area": "test",
            "goal_tag": "multiline_test",
            "rationale": "update multiline",
            "edits": [
                {
                    "path": multiline_file,
                    "match": "    x = 1\n    return x",
                    "replace": "    x = 2\n    return x * 2"
                }
            ]
        }

        result = apply_edits_package(
            json.dumps(edits_package),
            model_name="test_model",
            goal_tag="multiline_test"
        )

        self.assertTrue(result["ok"])

        # Verify content
        with open(multiline_file, 'r') as f:
            content = f.read()
        self.assertIn("x = 2", content)
        self.assertIn("return x * 2", content)

    def test_newline_normalization(self):
        """Test that line endings are properly normalized"""
        # Create file with CRLF endings
        crlf_file = 'crlf_test.py'
        with open(crlf_file, 'wb') as f:
            f.write(b'line1\r\nline2\r\nline3\r\n')

        subprocess.run(['git', 'add', crlf_file], check=True)
        subprocess.run(['git', 'commit', '-m', 'Add CRLF file'], check=True)

        edits_package = {
            "area": "test",
            "goal_tag": "crlf_test",
            "rationale": "test CRLF handling",
            "edits": [
                {
                    "path": crlf_file,
                    "match": "line2",
                    "replace": "modified_line2"
                }
            ]
        }

        result = apply_edits_package(
            json.dumps(edits_package),
            model_name="test_model",
            goal_tag="crlf_test"
        )

        self.assertTrue(result["ok"])

        # Verify content has LF endings
        with open(crlf_file, 'rb') as f:
            content = f.read()
        self.assertNotIn(b'\r\n', content)
        self.assertIn(b'\n', content)

    def test_match_not_found(self):
        """Test error handling when match string is not found"""
        edits_package = {
            "area": "test",
            "goal_tag": "not_found_test",
            "rationale": "test not found",
            "edits": [
                {
                    "path": self.test_file,
                    "match": "THIS_DOES_NOT_EXIST",
                    "replace": "replacement"
                }
            ]
        }

        result = apply_edits_package(
            json.dumps(edits_package),
            model_name="test_model",
            goal_tag="not_found_test"
        )

        self.assertFalse(result["ok"])
        self.assertIn("not found", result["error"].lower())

    def test_invalid_regex(self):
        """Test error handling for invalid regex patterns"""
        edits_package = {
            "area": "test",
            "goal_tag": "invalid_regex_test",
            "rationale": "test invalid regex",
            "edits": [
                {
                    "path": self.test_file,
                    "match_re": "[invalid regex pattern",
                    "group_replacement": "replacement"
                }
            ]
        }

        result = apply_edits_package(
            json.dumps(edits_package),
            model_name="test_model",
            goal_tag="invalid_regex_test"
        )

        self.assertFalse(result["ok"])

    def test_missing_file(self):
        """Test handling of edits to non-existent files"""
        edits_package = {
            "area": "test",
            "goal_tag": "missing_file_test",
            "rationale": "test missing file",
            "edits": [
                {
                    "path": "nonexistent.py",
                    "match": "anything",
                    "replace": "replacement"
                }
            ]
        }

        result = apply_edits_package(
            json.dumps(edits_package),
            model_name="test_model",
            goal_tag="missing_file_test"
        )

        # Should handle missing files gracefully by treating as empty content
        # This will likely fail on match not found, which is expected
        self.assertFalse(result["ok"])

    def test_multiple_edits(self):
        """Test applying multiple edits in one package"""
        edits_package = {
            "area": "test",
            "goal_tag": "multi_edit_test",
            "rationale": "test multiple edits",
            "edits": [
                {
                    "path": self.test_file,
                    "match": "X = 1",
                    "replace": "X = 100"
                },
                {
                    "path": self.test_file,
                    "match": "Y = 2",
                    "replace": "Y = 200"
                }
            ]
        }

        result = apply_edits_package(
            json.dumps(edits_package),
            model_name="test_model",
            goal_tag="multi_edit_test"
        )

        self.assertTrue(result["ok"])
        self.assertEqual(len(result["touched"]), 1)  # Same file touched once

        # Verify both changes applied
        with open(self.test_file, 'r') as f:
            content = f.read()
        self.assertIn("X = 100", content)
        self.assertIn("Y = 200", content)

    def test_file_shas_tracking(self):
        """Test that file SHAs are properly tracked"""
        edits_package = {
            "area": "test",
            "goal_tag": "sha_test",
            "rationale": "test SHA tracking",
            "edits": [
                {
                    "path": self.test_file,
                    "match": "Z = 3",
                    "replace": "Z = 30"
                }
            ]
        }

        result = apply_edits_package(
            json.dumps(edits_package),
            model_name="test_model",
            goal_tag="sha_test"
        )

        self.assertTrue(result["ok"])
        self.assertTrue("file_shas" in result)
        self.assertEqual(len(result["file_shas"]), 1)

        sha_entry = result["file_shas"][0]
        self.assertEqual(sha_entry["path"], self.test_file)
        self.assertTrue("before" in sha_entry)
        self.assertTrue("after" in sha_entry)
        self.assertNotEqual(sha_entry["before"], sha_entry["after"])

    def test_invalid_json(self):
        """Test error handling for invalid JSON"""
        result = apply_edits_package(
            "invalid json {",
            model_name="test_model",
            goal_tag="invalid_json_test"
        )

        self.assertFalse(result["ok"])
        self.assertIn("JSON", result["error"])

    def test_missing_required_fields(self):
        """Test error handling for missing required fields"""
        incomplete_package = {
            "area": "test",
            # Missing goal_tag, rationale, edits
        }

        result = apply_edits_package(
            json.dumps(incomplete_package),
            model_name="test_model",
            goal_tag="missing_fields_test"
        )

        self.assertFalse(result["ok"])
        self.assertIn("Missing required field", result["error"])

    def test_apply_one_edit_function(self):
        """Test the apply_one_edit helper function directly"""
        content = "hello world\nfoo bar\n"

        # Test exact match
        edit = {"match": "hello", "replace": "hi"}
        result = apply_one_edit(content, edit)
        self.assertEqual(result, "hi world\nfoo bar\n")

        # Test regex match
        edit = {"match_re": r"foo (\w+)", "group_replacement": r"baz \g<1>"}
        result = apply_one_edit(content, edit)
        self.assertEqual(result, "hello world\nbaz bar\n")

    def test_synth_unified_diff(self):
        """Test unified diff generation"""
        before = "line1\nline2\nline3\n"
        after = "line1\nmodified_line2\nline3\n"

        diff = synth_unified_diff("test.py", before, after)

        self.assertIn("--- a/test.py", diff)
        self.assertIn("+++ b/test.py", diff)
        self.assertIn("-line2", diff)
        self.assertIn("+modified_line2", diff)

    def test_git_apply_check(self):
        """Test git apply check functionality"""
        # Create a valid diff
        with open('check_test.py', 'w') as f:
            f.write('original content\n')
        subprocess.run(['git', 'add', 'check_test.py'], check=True)
        subprocess.run(['git', 'commit', '-m', 'Add check test file'], check=True)

        diff = """--- a/check_test.py
+++ b/check_test.py
@@ -1 +1 @@
-original content
+modified content
"""

        can_apply, error = git_apply_check(diff)
        self.assertTrue(can_apply, f"Git apply check failed: {error}")


if __name__ == '__main__':
    unittest.main()