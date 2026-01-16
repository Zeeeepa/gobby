import json
import os
from datetime import datetime

STATUS_FILE = "htmlcov/status.json"


def analyze_coverage():
    if not os.path.exists(STATUS_FILE):
        print("No status.json found.")
        return

    with open(STATUS_FILE) as f:
        data = json.load(f)

    files = data.get("files", {})
    stats = []

    for filename, info in files.items():
        details = info.get("index", {})
        path = details.get("file", filename)
        nums = details.get("nums", {})
        n_statements = nums.get("n_statements", 0)
        n_missing = nums.get("n_missing", 0)

        if n_statements > 0:
            coverage = (n_statements - n_missing) / n_statements * 100
        else:
            coverage = 100.0

        stats.append(
            {"path": path, "statements": n_statements, "missing": n_missing, "coverage": coverage}
        )

    # Sort by missing lines (descending)
    stats.sort(key=lambda x: x["missing"], reverse=True)

    print("# Coverage Gap Analysis")
    print(f"Generated at: {datetime.now().isoformat()}")
    print("\n## Top 20 Files by Missing Lines")
    print("| File | Statements | Missing | Coverage |")
    print("|---|---|---|---|")

    total_statements = 0
    total_missing = 0

    for s in stats[:20]:
        print(f"| `{s['path']}` | {s['statements']} | {s['missing']} | {s['coverage']:.1f}% |")

    for s in stats:
        total_statements += s["statements"]
        total_missing += s["missing"]

    global_coverage = (
        (total_statements - total_missing) / total_statements * 100 if total_statements else 0
    )
    print(f"\n## Global Stats")
    print(f"- **Total Statements**: {total_statements}")
    print(f"- **Total Missing**: {total_missing}")
    print(f"- **Global Coverage**: {global_coverage:.1f}%")


if __name__ == "__main__":
    analyze_coverage()
