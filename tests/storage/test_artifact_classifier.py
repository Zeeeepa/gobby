"""Tests for artifact type classification.

TDD RED PHASE: These tests verify the artifact classifier that automatically
detects artifact types from content. Tests should fail initially as the
classifier module does not exist yet.

The classifier is used to automatically categorize session artifacts into
types like code, file_path, error, command, structured_data, or text.
"""

import pytest


# =============================================================================
# Import Tests (RED PHASE)
# =============================================================================


class TestArtifactClassifierImport:
    """Tests for importing the artifact classifier."""

    def test_import_classify_artifact(self):
        """Test that classify_artifact can be imported from storage.artifact_classifier."""
        from gobby.storage.artifact_classifier import classify_artifact

        assert classify_artifact is not None

    def test_import_classification_result(self):
        """Test that ClassificationResult can be imported."""
        from gobby.storage.artifact_classifier import ClassificationResult

        assert ClassificationResult is not None


# =============================================================================
# Code Block Classification Tests
# =============================================================================


class TestCodeBlockClassification:
    """Tests for classify_artifact identifying code blocks by language markers."""

    def test_python_code_with_def(self):
        """Test that Python code with 'def' is classified as code."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """def calculate_total(items):
    return sum(item.price for item in items)
"""
        result = classify_artifact(content)

        assert result.artifact_type == "code"
        assert result.metadata.get("language") == "python"

    def test_python_code_with_class(self):
        """Test that Python code with 'class' is classified as code."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """class UserManager:
    def __init__(self):
        self.users = []
"""
        result = classify_artifact(content)

        assert result.artifact_type == "code"
        assert result.metadata.get("language") == "python"

    def test_python_code_with_import(self):
        """Test that Python code with imports is classified as code."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """import os
from pathlib import Path
import json
"""
        result = classify_artifact(content)

        assert result.artifact_type == "code"
        assert result.metadata.get("language") == "python"

    def test_javascript_code_with_function(self):
        """Test that JavaScript code with 'function' is classified as code."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """function calculateTotal(items) {
    return items.reduce((sum, item) => sum + item.price, 0);
}
"""
        result = classify_artifact(content)

        assert result.artifact_type == "code"
        assert result.metadata.get("language") == "javascript"

    def test_javascript_code_with_const_arrow(self):
        """Test that JavaScript code with const and arrow functions is classified as code."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """const calculateTotal = (items) => {
    return items.reduce((sum, item) => sum + item.price, 0);
};
"""
        result = classify_artifact(content)

        assert result.artifact_type == "code"
        assert result.metadata.get("language") == "javascript"

    def test_typescript_code_with_interface(self):
        """Test that TypeScript code with interface is classified as code."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """interface User {
    id: string;
    name: string;
    email?: string;
}
"""
        result = classify_artifact(content)

        assert result.artifact_type == "code"
        assert result.metadata.get("language") == "typescript"

    def test_rust_code_with_fn(self):
        """Test that Rust code with 'fn' is classified as code."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """fn calculate_total(items: Vec<Item>) -> f64 {
    items.iter().map(|item| item.price).sum()
}
"""
        result = classify_artifact(content)

        assert result.artifact_type == "code"
        assert result.metadata.get("language") == "rust"

    def test_go_code_with_func(self):
        """Test that Go code with 'func' is classified as code."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """func calculateTotal(items []Item) float64 {
    var total float64
    for _, item := range items {
        total += item.Price
    }
    return total
}
"""
        result = classify_artifact(content)

        assert result.artifact_type == "code"
        assert result.metadata.get("language") == "go"

    def test_sql_query(self):
        """Test that SQL queries are classified as code."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """SELECT u.name, COUNT(o.id) as order_count
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
WHERE u.active = true
GROUP BY u.id
ORDER BY order_count DESC;
"""
        result = classify_artifact(content)

        assert result.artifact_type == "code"
        assert result.metadata.get("language") == "sql"

    def test_shell_script(self):
        """Test that shell scripts are classified as code."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """#!/bin/bash
for file in *.txt; do
    echo "Processing $file"
    cat "$file" | wc -l
done
"""
        result = classify_artifact(content)

        assert result.artifact_type == "code"
        assert result.metadata.get("language") in ("bash", "shell")


# =============================================================================
# File Path Classification Tests
# =============================================================================


class TestFilePathClassification:
    """Tests for classify_artifact identifying file paths."""

    def test_unix_absolute_path(self):
        """Test that Unix absolute paths are classified as file_path."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = "/Users/josh/Projects/gobby/src/main.py"
        result = classify_artifact(content)

        assert result.artifact_type == "file_path"
        assert result.metadata.get("extension") == "py"

    def test_windows_absolute_path(self):
        """Test that Windows absolute paths are classified as file_path."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = "C:\\Users\\Josh\\Projects\\gobby\\src\\main.py"
        result = classify_artifact(content)

        assert result.artifact_type == "file_path"
        assert result.metadata.get("extension") == "py"

    def test_relative_path_with_extension(self):
        """Test that relative paths with extensions are classified as file_path."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = "src/storage/artifacts.py"
        result = classify_artifact(content)

        assert result.artifact_type == "file_path"
        assert result.metadata.get("extension") == "py"

    def test_path_with_dots_directory(self):
        """Test that paths with dot directories are classified as file_path."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = "../parent/file.txt"
        result = classify_artifact(content)

        assert result.artifact_type == "file_path"

    def test_path_without_extension(self):
        """Test that paths without extensions can still be classified as file_path."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = "/usr/local/bin/python3"
        result = classify_artifact(content)

        assert result.artifact_type == "file_path"
        assert result.metadata.get("extension") is None


# =============================================================================
# Error Message Classification Tests
# =============================================================================


class TestErrorMessageClassification:
    """Tests for classify_artifact identifying error messages and stack traces."""

    def test_python_traceback(self):
        """Test that Python tracebacks are classified as error."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """Traceback (most recent call last):
  File "/src/main.py", line 42, in process
    result = calculate(data)
  File "/src/utils.py", line 15, in calculate
    return data / 0
ZeroDivisionError: division by zero
"""
        result = classify_artifact(content)

        assert result.artifact_type == "error"
        assert "traceback" in result.metadata.get("error_type", "").lower() or \
               result.metadata.get("language") == "python"

    def test_javascript_error(self):
        """Test that JavaScript errors are classified as error."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """TypeError: Cannot read property 'length' of undefined
    at Array.forEach (<anonymous>)
    at processItems (/src/index.js:42:10)
    at main (/src/index.js:15:5)
"""
        result = classify_artifact(content)

        assert result.artifact_type == "error"

    def test_rust_panic(self):
        """Test that Rust panics are classified as error."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """thread 'main' panicked at 'index out of bounds: the len is 3 but the index is 5', src/main.rs:10:5
note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace
"""
        result = classify_artifact(content)

        assert result.artifact_type == "error"

    def test_generic_error_message(self):
        """Test that generic error messages are classified as error."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """Error: Connection refused
Failed to connect to database at localhost:5432
"""
        result = classify_artifact(content)

        assert result.artifact_type == "error"

    def test_exception_message(self):
        """Test that exception messages are classified as error."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """Exception in thread "main" java.lang.NullPointerException
    at com.example.Main.process(Main.java:42)
    at com.example.Main.main(Main.java:10)
"""
        result = classify_artifact(content)

        assert result.artifact_type == "error"


# =============================================================================
# Command Output Classification Tests
# =============================================================================


class TestCommandOutputClassification:
    """Tests for classify_artifact identifying command outputs."""

    def test_git_status_output(self):
        """Test that git status output is classified as command_output."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
        modified:   src/main.py

no changes added to commit (use "git add" and/or "git commit -a")
"""
        result = classify_artifact(content)

        assert result.artifact_type == "command_output"

    def test_npm_install_output(self):
        """Test that npm install output is classified as command_output."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """npm WARN deprecated request@2.88.2: request has been deprecated
added 423 packages, and audited 424 packages in 15s

73 packages are looking for funding
  run `npm fund` for details

found 0 vulnerabilities
"""
        result = classify_artifact(content)

        assert result.artifact_type == "command_output"

    def test_pytest_output(self):
        """Test that pytest output is classified as command_output."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """============================= test session starts ==============================
platform darwin -- Python 3.11.0, pytest-7.2.0, pluggy-1.0.0
collected 42 items

tests/test_main.py ............................                            [ 66%]
tests/test_utils.py ..............                                         [100%]

============================== 42 passed in 2.15s ==============================
"""
        result = classify_artifact(content)

        assert result.artifact_type == "command_output"

    def test_ls_output(self):
        """Test that ls output is classified as command_output."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """total 32
drwxr-xr-x  10 user  staff   320 Jan  8 10:00 .
drwxr-xr-x   5 user  staff   160 Jan  8 09:00 ..
-rw-r--r--   1 user  staff  1234 Jan  8 10:00 main.py
-rw-r--r--   1 user  staff   567 Jan  8 10:00 utils.py
"""
        result = classify_artifact(content)

        assert result.artifact_type == "command_output"

    def test_shell_prompt_output(self):
        """Test that shell command with prompt is classified as command_output."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """$ git log --oneline -3
abc1234 fix: resolve connection issue
def5678 feat: add new feature
ghi9012 docs: update readme
"""
        result = classify_artifact(content)

        assert result.artifact_type == "command_output"


# =============================================================================
# Structured Data Classification Tests
# =============================================================================


class TestStructuredDataClassification:
    """Tests for classify_artifact identifying structured data (JSON/YAML)."""

    def test_json_object(self):
        """Test that JSON objects are classified as structured_data."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """{
    "name": "gobby",
    "version": "1.0.0",
    "dependencies": {
        "click": "^8.0.0",
        "pydantic": "^2.0.0"
    }
}
"""
        result = classify_artifact(content)

        assert result.artifact_type == "structured_data"
        assert result.metadata.get("format") == "json"

    def test_json_array(self):
        """Test that JSON arrays are classified as structured_data."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """[
    {"id": 1, "name": "Alice"},
    {"id": 2, "name": "Bob"},
    {"id": 3, "name": "Charlie"}
]
"""
        result = classify_artifact(content)

        assert result.artifact_type == "structured_data"
        assert result.metadata.get("format") == "json"

    def test_yaml_config(self):
        """Test that YAML config is classified as structured_data."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """name: gobby
version: 1.0.0
dependencies:
  - click>=8.0.0
  - pydantic>=2.0.0
settings:
  debug: true
  log_level: INFO
"""
        result = classify_artifact(content)

        assert result.artifact_type == "structured_data"
        assert result.metadata.get("format") == "yaml"

    def test_toml_config(self):
        """Test that TOML config is classified as structured_data."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """[project]
name = "gobby"
version = "1.0.0"

[project.dependencies]
click = "^8.0.0"
pydantic = "^2.0.0"
"""
        result = classify_artifact(content)

        assert result.artifact_type == "structured_data"
        assert result.metadata.get("format") == "toml"

    def test_xml_data(self):
        """Test that XML data is classified as structured_data."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """<?xml version="1.0" encoding="UTF-8"?>
<project>
    <name>gobby</name>
    <version>1.0.0</version>
</project>
"""
        result = classify_artifact(content)

        assert result.artifact_type == "structured_data"
        assert result.metadata.get("format") == "xml"


# =============================================================================
# Default Type Classification Tests
# =============================================================================


class TestDefaultTypeClassification:
    """Tests for classify_artifact returning 'text' as default type."""

    def test_plain_text_returns_text(self):
        """Test that plain text is classified as text."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """This is just some plain text that doesn't match any specific pattern.
It's a description of something, maybe some notes or documentation.
"""
        result = classify_artifact(content)

        assert result.artifact_type == "text"

    def test_short_string_returns_text(self):
        """Test that short strings are classified as text."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = "Hello, world!"
        result = classify_artifact(content)

        assert result.artifact_type == "text"

    def test_empty_string_returns_text(self):
        """Test that empty strings are classified as text."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = ""
        result = classify_artifact(content)

        assert result.artifact_type == "text"

    def test_whitespace_only_returns_text(self):
        """Test that whitespace-only content is classified as text."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = "   \n\n\t  \n   "
        result = classify_artifact(content)

        assert result.artifact_type == "text"

    def test_mixed_content_defaults_to_text(self):
        """Test that ambiguous mixed content defaults to text."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """Here are some notes:
- Item one
- Item two
- Item three

These are just bullet points.
"""
        result = classify_artifact(content)

        assert result.artifact_type == "text"


# =============================================================================
# Metadata Extraction Tests
# =============================================================================


class TestMetadataExtraction:
    """Tests for metadata extraction based on artifact type."""

    def test_code_extracts_language(self):
        """Test that code classification extracts language."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = "def hello(): pass"
        result = classify_artifact(content)

        assert result.artifact_type == "code"
        assert "language" in result.metadata

    def test_file_path_extracts_extension(self):
        """Test that file_path classification extracts extension."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = "/path/to/file.py"
        result = classify_artifact(content)

        assert result.artifact_type == "file_path"
        assert result.metadata.get("extension") == "py"

    def test_file_path_extracts_filename(self):
        """Test that file_path classification extracts filename."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = "/path/to/my_script.py"
        result = classify_artifact(content)

        assert result.artifact_type == "file_path"
        assert result.metadata.get("filename") == "my_script.py"

    def test_structured_data_extracts_format(self):
        """Test that structured_data classification extracts format."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = '{"key": "value"}'
        result = classify_artifact(content)

        assert result.artifact_type == "structured_data"
        assert result.metadata.get("format") == "json"

    def test_error_extracts_error_type(self):
        """Test that error classification extracts error type when possible."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """ZeroDivisionError: division by zero"""
        result = classify_artifact(content)

        assert result.artifact_type == "error"
        # May extract error type like "ZeroDivisionError"
        assert "error" in result.metadata or result.metadata == {}


# =============================================================================
# Classification Result Tests
# =============================================================================


class TestClassificationResult:
    """Tests for ClassificationResult dataclass."""

    def test_classification_result_has_artifact_type(self):
        """Test that ClassificationResult has artifact_type field."""
        from gobby.storage.artifact_classifier import ClassificationResult

        result = ClassificationResult(artifact_type="code", metadata={})
        assert result.artifact_type == "code"

    def test_classification_result_has_metadata(self):
        """Test that ClassificationResult has metadata field."""
        from gobby.storage.artifact_classifier import ClassificationResult

        result = ClassificationResult(artifact_type="code", metadata={"language": "python"})
        assert result.metadata == {"language": "python"}

    def test_classification_result_metadata_defaults_empty(self):
        """Test that ClassificationResult metadata can be empty."""
        from gobby.storage.artifact_classifier import ClassificationResult

        result = ClassificationResult(artifact_type="text", metadata={})
        assert result.metadata == {}

    def test_classification_result_to_dict(self):
        """Test that ClassificationResult has to_dict method."""
        from gobby.storage.artifact_classifier import ClassificationResult

        result = ClassificationResult(artifact_type="code", metadata={"language": "python"})
        d = result.to_dict()

        assert d["artifact_type"] == "code"
        assert d["metadata"]["language"] == "python"


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases in classification."""

    def test_code_block_with_markdown_fence(self):
        """Test that markdown fenced code blocks are classified as code."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """```python
def hello():
    print("Hello, world!")
```"""
        result = classify_artifact(content)

        assert result.artifact_type == "code"
        assert result.metadata.get("language") == "python"

    def test_code_block_with_triple_backticks_no_lang(self):
        """Test that markdown code blocks without language hint."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """```
some code here
```"""
        result = classify_artifact(content)

        # Should still be classified as code, language may be unknown
        assert result.artifact_type == "code"

    def test_very_long_content(self):
        """Test that very long content is handled."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = "x" * 100000  # 100KB of text
        result = classify_artifact(content)

        assert result.artifact_type == "text"

    def test_binary_looking_content(self):
        """Test that binary-looking content is handled gracefully."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = "\x00\x01\x02\x03binary data"
        result = classify_artifact(content)

        # Should not raise, may be text or other type
        assert result.artifact_type is not None

    def test_unicode_content(self):
        """Test that unicode content is handled."""
        from gobby.storage.artifact_classifier import classify_artifact

        content = """def greet():
    print("Hola, mundo!")
"""
        result = classify_artifact(content)

        assert result.artifact_type == "code"
