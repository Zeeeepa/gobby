# SWE-bench Evaluation & Leaderboard Submission Plan

## Overview

This plan outlines the steps to implement SWE-bench evaluation for Gobby + Claude Code, track scores over time, and submit results to the official leaderboard.

**Goal**: Measure how Gobby's task tracking, workflows, and MCP tools affect Claude Code's performance on real-world software engineering tasks.

**Target Benchmarks**:
- SWE-bench Lite (300 instances) - for development iteration
- SWE-bench Verified (500 instances) - for official scores
- SWE-bench Live (dynamic) - for contamination-free ongoing evaluation

---

## Phase 1: Infrastructure Setup

### 1.1 Evaluation Database Schema

Add tables to track evaluation runs and results in `src/gobby/storage/`:

```sql
-- eval_runs: Track each benchmark run
CREATE TABLE eval_runs (
    id TEXT PRIMARY KEY,                    -- e.g., "run-20260107-001"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    benchmark TEXT NOT NULL,                -- 'lite', 'verified', 'live'
    split TEXT DEFAULT 'test',              -- 'test', 'dev'
    gobby_version TEXT NOT NULL,
    model TEXT NOT NULL,                    -- 'claude-opus-4.5', 'claude-sonnet-4'
    workflow TEXT,                          -- active workflow if any
    config_hash TEXT,                       -- SHA256 of agent config

    -- Counts
    total_instances INTEGER,
    attempted INTEGER DEFAULT 0,
    patches_generated INTEGER DEFAULT 0,
    resolved INTEGER DEFAULT 0,

    -- Metrics
    pass_rate REAL,                         -- resolved / total
    cost_usd REAL,
    tokens_used INTEGER,
    avg_time_seconds REAL,

    -- Status
    status TEXT DEFAULT 'running',          -- 'running', 'completed', 'failed'
    completed_at TIMESTAMP,
    notes TEXT
);

-- eval_instances: Per-instance results
CREATE TABLE eval_instances (
    run_id TEXT REFERENCES eval_runs(id) ON DELETE CASCADE,
    instance_id TEXT NOT NULL,              -- e.g., 'django__django-11099'

    -- Results
    patch_generated BOOLEAN DEFAULT FALSE,
    resolved BOOLEAN DEFAULT FALSE,

    -- Artifacts
    patch TEXT,                             -- The generated diff
    trajectory_path TEXT,                   -- Path to trajectory file
    log_path TEXT,                          -- Path to execution log

    -- Metrics
    tokens_used INTEGER,
    cost_usd REAL,
    time_seconds REAL,
    attempts INTEGER DEFAULT 1,

    -- Debug
    error TEXT,

    PRIMARY KEY (run_id, instance_id)
);

-- eval_comparisons: Track A/B comparisons
CREATE TABLE eval_comparisons (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    run_a TEXT REFERENCES eval_runs(id),
    run_b TEXT REFERENCES eval_runs(id),
    description TEXT,
    delta_pass_rate REAL,
    delta_cost REAL,
    significant BOOLEAN                     -- Statistical significance
);
```

### 1.2 Evaluation Module Structure

Create `src/gobby/eval/`:

```
src/gobby/eval/
├── __init__.py
├── runner.py           # Main evaluation orchestrator
├── harness.py          # Docker environment management
├── agent.py            # Claude Code agent wrapper
├── scorer.py           # Evaluate patches against tests
├── storage.py          # Database operations
├── artifacts.py        # Trajectory/log management
├── export.py           # Export for leaderboard submission
└── cli.py              # CLI commands
```

### 1.3 CLI Commands

Add to `src/gobby/cli.py`:

```bash
# Run evaluations
gobby eval run                              # Run on Lite (default)
gobby eval run --benchmark verified         # Run on Verified
gobby eval run --benchmark lite --limit 10  # Quick test
gobby eval run --model claude-sonnet-4      # Specific model
gobby eval run --workflow test-driven       # With workflow

# Check status
gobby eval status                           # Current run progress
gobby eval status run-20260107-001          # Specific run

# View results
gobby eval list                             # All runs
gobby eval show run-20260107-001            # Detailed results
gobby eval compare run-001 run-002          # Compare two runs

# Export for submission
gobby eval export run-001 --format swebench # Export for leaderboard
gobby eval export run-001 --output ./submission/
```

### 1.4 Dependencies

Add to `pyproject.toml`:

```toml
[project.optional-dependencies]
eval = [
    "swebench>=2.0.0",
    "datasets>=2.14.0",
    "docker>=6.0.0",
]
```

---

## Phase 2: Agent Integration

### 2.1 Claude Code Agent Wrapper

Create `src/gobby/eval/agent.py`:

```python
class SWEBenchAgent:
    """Wrapper for running Claude Code on SWE-bench instances."""

    def __init__(
        self,
        model: str = "claude-sonnet-4",
        gobby_enabled: bool = True,
        workflow: str | None = None,
        max_tokens: int = 200_000,
    ):
        self.model = model
        self.gobby_enabled = gobby_enabled
        self.workflow = workflow
        self.max_tokens = max_tokens

    async def solve(self, instance: dict) -> AgentResult:
        """
        Solve a SWE-bench instance.

        Args:
            instance: SWE-bench instance with problem_statement, repo, etc.

        Returns:
            AgentResult with patch, trajectory, metrics
        """
        # 1. Set up environment (clone repo at base commit)
        # 2. Start Gobby daemon if enabled
        # 3. Create task from issue
        # 4. Run Claude Code in non-interactive mode
        # 5. Capture patch and trajectory
        # 6. Return result
```

### 2.2 Trajectory Capture

Capture full reasoning traces for leaderboard submission:

```python
@dataclass
class TrajectoryEntry:
    timestamp: float
    type: str               # 'thought', 'tool_call', 'tool_result', 'error'
    content: str
    tool_name: str | None
    tool_args: dict | None

class TrajectoryRecorder:
    """Records agent reasoning for SWE-bench submission."""

    def __init__(self, instance_id: str):
        self.instance_id = instance_id
        self.entries: list[TrajectoryEntry] = []

    def record_thought(self, thought: str): ...
    def record_tool_call(self, name: str, args: dict): ...
    def record_tool_result(self, result: str): ...

    def export(self, format: str = "json") -> str:
        """Export trajectory in SWE-bench format."""
```

### 2.3 Gobby Integration Points

Test these Gobby features during evaluation:

| Feature | How to Test |
|---------|-------------|
| Task tracking | Create task before solving, measure if it helps focus |
| Workflows | Run with `test-driven` or `plan-execute` workflow |
| MCP tools | Enable/disable specific tools and compare |
| Memory | Pre-seed with relevant patterns, measure improvement |
| Session context | Provide continuation context from previous attempts |

---

## Phase 3: Evaluation Pipeline

### 3.1 Local Evaluation Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     gobby eval run                          │
├─────────────────────────────────────────────────────────────┤
│  1. Load dataset from HuggingFace                           │
│  2. Create eval_run record in database                      │
│  3. For each instance:                                      │
│     a. Clone repo at base commit                            │
│     b. Start Gobby daemon (if enabled)                      │
│     c. Create task from issue                               │
│     d. Run Claude Code with problem statement               │
│     e. Extract patch from response                          │
│     f. Save trajectory to trajs/                            │
│     g. Evaluate patch in Docker container                   │
│     h. Record result in database                            │
│  4. Calculate aggregate metrics                             │
│  5. Update eval_run with final stats                        │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Parallelization

Run multiple instances in parallel for speed:

```python
async def run_evaluation(
    benchmark: str = "lite",
    max_workers: int = 4,          # Parallel instances
    limit: int | None = None,
):
    dataset = load_dataset(f"princeton-nlp/SWE-bench_{benchmark}")

    semaphore = asyncio.Semaphore(max_workers)

    async def process_instance(instance):
        async with semaphore:
            return await agent.solve(instance)

    results = await asyncio.gather(*[
        process_instance(inst) for inst in dataset[:limit]
    ])
```

### 3.3 Docker Evaluation

Use official SWE-bench harness for patch evaluation:

```python
from swebench.harness.run_evaluation import run_evaluation

def evaluate_patches(predictions_path: str, run_id: str):
    """Evaluate generated patches using Docker."""
    run_evaluation(
        dataset_name="princeton-nlp/SWE-bench_Lite",
        predictions_path=predictions_path,
        max_workers=min(8, os.cpu_count() * 0.75),
        run_id=run_id,
    )
```

### 3.4 Cloud Evaluation (Modal)

For faster evaluation without local Docker:

```python
def run_on_modal(predictions_path: str, run_id: str):
    """Run evaluation on Modal cloud."""
    subprocess.run([
        "python", "-m", "swebench.harness.run_evaluation",
        "--dataset_name", "princeton-nlp/SWE-bench_Verified",
        "--predictions_path", predictions_path,
        "--parallelism", "20",
        "--modal", "true",
        "--run_id", run_id,
    ])
```

---

## Phase 4: Score Tracking

### 4.1 Historical Tracking

Query functions for trend analysis:

```python
def get_score_history(
    benchmark: str = "lite",
    model: str | None = None,
    days: int = 30,
) -> list[dict]:
    """Get historical pass rates."""

def compare_runs(run_a: str, run_b: str) -> ComparisonResult:
    """Compare two runs with statistical significance."""

def get_regression_candidates(
    current_run: str,
    baseline_run: str,
) -> list[str]:
    """Find instances that regressed."""
```

### 4.2 Visualization (Optional)

Export data for visualization:

```bash
# Export to CSV for analysis
gobby eval export-history --format csv > scores.csv

# JSON for dashboards
gobby eval export-history --format json > scores.json
```

### 4.3 CI/CD Integration

Add to GitHub Actions for regression detection:

```yaml
# .github/workflows/swebench-eval.yml
name: SWE-bench Evaluation

on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly
  workflow_dispatch:

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run SWE-bench Lite (10 instances)
        run: |
          uv run gobby eval run --benchmark lite --limit 10

      - name: Check for regression
        run: |
          uv run gobby eval compare --latest --baseline main
```

---

## Phase 5: Leaderboard Submission

### 5.1 Submission Artifacts

Generate all required files:

```
submission/
├── 20260115_gobby_claude_sonnet/
│   ├── all_preds.jsonl          # Predictions
│   ├── metadata.yaml            # Metadata
│   ├── README.md                # System description
│   ├── trajs/                   # Reasoning traces
│   │   ├── django__django-11099.json
│   │   ├── sympy__sympy-20590.json
│   │   └── ...
│   └── logs/                    # Execution logs
│       ├── django__django-11099/
│       │   ├── patch.diff
│       │   ├── report.json
│       │   └── test_output.txt
│       └── ...
```

### 5.2 Predictions Format

`all_preds.jsonl`:
```jsonl
{"instance_id": "django__django-11099", "model_name_or_path": "gobby-claude-sonnet-4", "model_patch": "diff --git a/..."}
{"instance_id": "sympy__sympy-20590", "model_name_or_path": "gobby-claude-sonnet-4", "model_patch": "diff --git a/..."}
```

### 5.3 Metadata Format

`metadata.yaml`:
```yaml
info:
  logo: "https://github.com/josh/gobby/raw/main/assets/logo.png"
  name: "Gobby + Claude Code"
  site: "https://github.com/josh/gobby"
  report: "https://josh.github.io/gobby/swebench-report"
  authors:
    - "Josh"

tags:
  checked: false
  model:
    - "Claude Sonnet 4"
  org: "Gobby"
  os_model: false
  os_system: true

system:
  attempts: "1"
```

### 5.4 README Template

`README.md`:
```markdown
# Gobby + Claude Code SWE-bench Submission

## System Description

Gobby is a local daemon that provides task tracking, workflow management,
and MCP tool discovery for Claude Code. This submission evaluates how
these features affect Claude Code's performance on SWE-bench.

## Architecture

- **Agent**: Claude Sonnet 4 via Claude Code CLI
- **Scaffold**: Minimal (bash + edit tools only)
- **Enhancements**: Gobby task tracking, test-driven workflow

## Evaluation Details

- **Benchmark**: SWE-bench Verified
- **Instances**: 500
- **Pass@1**: Yes (single attempt per instance)
- **Date**: 2026-01-15

## How to Reproduce

\`\`\`bash
# Install
pip install gobby[eval]

# Run evaluation
gobby eval run --benchmark verified --model claude-sonnet-4
\`\`\`

## Results

| Metric | Value |
|--------|-------|
| Resolved | X / 500 |
| Pass Rate | XX.X% |
| Avg Cost | $X.XX |
| Avg Time | XX sec |
```

### 5.5 Export Command

```bash
# Generate submission artifacts
gobby eval export run-20260115-001 \
    --output ./submission/20260115_gobby_claude_sonnet/ \
    --format swebench

# Validate submission
python -m analysis.get_results evaluation/verified/20260115_gobby_claude_sonnet
```

### 5.6 Submission Process

1. **Fork** [SWE-bench/experiments](https://github.com/SWE-bench/experiments)
2. **Create folder** under `evaluation/verified/YYYYMMDD_gobby_model/`
3. **Add artifacts** (predictions, metadata, README, trajs/, logs/)
4. **Run validation**: `python -m analysis.get_results <path>`
5. **Submit PR** with results
6. **Request verification** by creating an issue with reproduction instructions

### 5.7 Getting Verified Status

To get the checkmark on the leaderboard:

1. Create issue in SWE-bench/experiments
2. Provide runnable instructions (Docker image or script)
3. SWE-bench team runs on random subset
4. If results match, you get verified

---

## Phase 6: A/B Testing Gobby Features

### 6.1 Experiment Matrix

Run controlled experiments to measure Gobby's impact:

| Experiment | Control | Treatment | Hypothesis |
|------------|---------|-----------|------------|
| Task tracking | No Gobby | With task creation | Better focus |
| Test-driven workflow | Default | `test-driven` workflow | Higher pass rate |
| Memory | No memory | Pre-seeded patterns | Faster solving |
| MCP tools | Bash + Edit only | All MCP tools | More capabilities |

### 6.2 Running Experiments

```bash
# Control: Claude Code without Gobby
gobby eval run --benchmark lite --no-gobby --run-id control

# Treatment: Claude Code with Gobby task tracking
gobby eval run --benchmark lite --run-id treatment

# Compare
gobby eval compare control treatment
```

### 6.3 Statistical Analysis

Ensure differences are statistically significant:

```python
from scipy.stats import binomtest

def is_significant(resolved_a, total_a, resolved_b, total_b, alpha=0.05):
    """Test if difference in pass rates is significant."""
    # Use McNemar's test for paired comparisons
    # or binomial test for independent samples
```

---

## Resources

### Official Documentation
- [SWE-bench Main Repo](https://github.com/SWE-bench/SWE-bench)
- [SWE-bench Experiments](https://github.com/SWE-bench/experiments)
- [sb-cli Documentation](https://www.swebench.com/sb-cli/)
- [Submission Checklist](https://github.com/swe-bench/experiments/blob/main/checklist.md)

### Reference Implementations
- [jimmc414/claudecode_swebench](https://github.com/jimmc414/claudecode_gemini_and_codex_swebench) - Claude Code toolkit
- [SWE-agent](https://github.com/princeton-nlp/SWE-agent) - Princeton's agent
- [OpenHands](https://github.com/OpenHands/OpenHands) - Multi-agent framework
- [Agentless](https://github.com/OpenAutoCoder/Agentless) - Simpler approach

### Anthropic Resources
- [SWE-bench Engineering Blog](https://www.anthropic.com/engineering/swe-bench-sonnet)
- [Claude Code Best Practices](https://www.anthropic.com/engineering/claude-code-best-practices)

---

## Success Criteria

1. **Functional**: Can run evaluations and get accurate scores
2. **Trackable**: Historical scores stored and queryable
3. **Reproducible**: Anyone can reproduce our results
4. **Published**: Scores appear on official leaderboard
5. **Verified**: Receive checkmark from SWE-bench team
6. **Insightful**: Data shows which Gobby features help most
