#!/usr/bin/env bash
set -euo pipefail

# Pre-push CI/CD test suite
# Runs linting, type checking, security scanning, and tests

TIMESTAMP=$(date +%s)
REPORTS_DIR="./reports"
mkdir -p "$REPORTS_DIR"

echo "=== Pre-push Test Suite ==="
echo "Timestamp: $TIMESTAMP"
echo ""

# Track failures
FAILED=0

# Ruff - autofix safe changes only (no unsafe fixes)
echo ">>> Running ruff check + format..."
if uv run ruff check src/ --fix --no-unsafe-fixes 2>&1 | tee "$REPORTS_DIR/ruff-$TIMESTAMP.txt"; then
    uv run ruff format src/
    echo "✓ Ruff passed"
else
    echo "✗ Ruff failed"
    FAILED=1
fi
echo ""

# Mypy - strict mode
echo ">>> Running mypy (strict)..."
if uv run mypy src/ --strict 2>&1 | tee "$REPORTS_DIR/mypy-$TIMESTAMP.txt"; then
    echo "✓ Mypy passed"
else
    echo "✗ Mypy failed"
    FAILED=1
fi
echo ""

# Bandit - security linting
echo ">>> Running bandit..."
if uv run bandit -r src/ -q 2>&1 | tee "$REPORTS_DIR/bandit-$TIMESTAMP.txt"; then
    echo "✓ Bandit passed"
else
    echo "✗ Bandit failed"
    FAILED=1
fi
echo ""

# pip-audit - dependency CVE scanning
echo ">>> Running pip-audit..."
if uv run pip-audit 2>&1 | tee "$REPORTS_DIR/pip-audit-$TIMESTAMP.txt"; then
    echo "✓ pip-audit passed"
else
    echo "✗ pip-audit failed"
    FAILED=1
fi
echo ""

# Pytest - tests with coverage (80% threshold)
echo ">>> Running pytest with coverage..."
if uv run pytest -q --tb=line -rFEw --cov=gobby --cov-fail-under=80 --cov-report=term-missing 2>&1 | tee "$REPORTS_DIR/pytest-$TIMESTAMP.txt"; then
    echo "✓ Pytest passed"
else
    echo "✗ Pytest failed"
    FAILED=1
fi
echo ""

# Summary
echo "=== Summary ==="
echo "Reports saved to: $REPORTS_DIR/*-$TIMESTAMP.txt"

if [ $FAILED -eq 0 ]; then
    echo "✓ All checks passed!"
    exit 0
else
    echo "✗ Some checks failed - review reports"
    exit 1
fi
