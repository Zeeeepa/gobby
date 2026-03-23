"""CLI command: gobby compress -- <command>

Runs a command and compresses its output for LLM consumption.
Used by PreToolUse hook rewriting to reduce token usage.
"""

import re
import subprocess
import sys

import click
import httpx

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


@click.command()
@click.option("--stats", is_flag=True, help="Show compression statistics to stderr")
@click.argument("command", nargs=-1, required=True)
def compress(command: tuple[str, ...], stats: bool) -> None:
    """Run a command and compress its output for LLM consumption.

    Usage: gobby compress -- git status
    """
    # The command arrives shlex-quoted from the hook rewrite (single string)
    # or as separate args if invoked manually.  Join into a single string
    # and run through the shell so redirections (2>&1), pipes, and flag-like
    # arguments (e.g. head -30) work correctly.
    cmd = " ".join(command)

    result = subprocess.run(  # nosec B602 # command comes from hook rewrite, not user input
        cmd,
        capture_output=True,
        text=True,
        shell=True,
    )

    raw_output = result.stdout
    if result.stderr:
        raw_output += result.stderr

    # Strip ANSI escape codes — they break compression pattern matching
    # and serve no purpose for LLM consumption
    raw_output = _ANSI_RE.sub("", raw_output)

    if not raw_output.strip():
        if result.returncode == 0:
            click.echo("No errors.")
        else:
            click.echo(f"Command failed with exit code {result.returncode} (no output).")
        sys.exit(result.returncode)

    from gobby.compression import OutputCompressor

    # Read compression config from daemon (best-effort, fall back to defaults)
    min_length = 1000
    excluded: list[str] = []
    try:
        from gobby.utils.daemon_client import DaemonClient

        resp = DaemonClient().call_http_api("/api/config/values", method="GET", timeout=1.0).json()
        cfg = resp.get("output_compression", {})
        min_length = cfg.get("min_output_length", min_length)
        excluded = cfg.get("excluded_commands", excluded)
        max_lines = cfg.get("max_compressed_lines", 100)
    except (httpx.HTTPError, ValueError, KeyError):
        max_lines = 100

    compressor = OutputCompressor(
        min_length=min_length,
        max_lines=max_lines,
        excluded_commands=excluded,
    )
    compressed = compressor.compress(cmd, raw_output)

    if stats:
        click.echo(
            f"[compress] strategy={compressed.strategy_name} "
            f"original={compressed.original_chars} "
            f"compressed={compressed.compressed_chars} "
            f"savings={compressed.savings_pct:.1f}%",
            err=True,
        )

    # Track savings via savings ledger (best-effort, non-blocking)
    if compressed.strategy_name not in ("passthrough", "excluded"):
        try:
            from gobby.utils.daemon_client import DaemonClient

            client = DaemonClient()
            client.call_http_api(
                "/api/admin/savings/record",
                method="POST",
                json_data={
                    "category": "compression",
                    "original_chars": compressed.original_chars,
                    "actual_chars": compressed.compressed_chars,
                    "metadata": {"strategy": compressed.strategy_name},
                },
                timeout=1.0,
            )
        except httpx.HTTPError:
            pass  # Non-critical — don't fail the command

    output = compressed.compressed
    if compressed.strategy_name not in ("passthrough", "excluded"):
        output = f"[Output compressed by Gobby — {compressed.strategy_name}, {compressed.savings_pct:.0f}% reduction]\n{output}"
    click.echo(output, nl=False)
    # Exit 0 when compression succeeded — the LLM reads pass/fail from the
    # content.  Propagating the subprocess exit code causes Claude Code to
    # frame the entire output as "Error: Exit code 1", hiding the results.
