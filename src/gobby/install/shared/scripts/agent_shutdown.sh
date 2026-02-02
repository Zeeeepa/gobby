#!/bin/bash
# agent_shutdown.sh - Gracefully terminate the agent's terminal session
# VERSION: 3.0.0
# Installed by: uv run gobby install --gemini
#
# This script is used by the meeseeks workflow to self-terminate
# after completing its assigned task.
#
# Usage:
#   agent_shutdown.sh [PID] [SIGNAL] [DELAY]
#   - PID: Target terminal PID (preferred). If empty or non-numeric, falls back to PPID discovery.
#   - SIGNAL: Signal to send (TERM, KILL, INT). Default: TERM
#   - DELAY: Delay in seconds before shutdown. Default: 0

# Accept PID as first argument (preferred), fall back to PPID discovery
if [ -n "$1" ] && echo "$1" | grep -qE '^[0-9]+$'; then
    TERM_PID="$1"
    SIGNAL="${2:-TERM}"
    DELAY="${3:-0}"
else
    # Legacy fallback: discover via PPID (unreliable when run from daemon)
    TERM_PID=$(ps -o ppid= -p $$ | tr -d ' ')
    SIGNAL="${1:-TERM}"
    DELAY="${2:-0}"
fi

# Create log directory if it doesn't exist
mkdir -p ~/.gobby/logs

# Determine PID source for logging
if [ -n "$1" ] && echo "$1" | grep -qE '^[0-9]+$'; then
    PID_SOURCE="argument"
else
    PID_SOURCE="ppid_discovery"
fi

# Validate TERM_PID is non-empty, numeric, and process exists
if [ -z "$TERM_PID" ]; then
    echo "[$(date -Iseconds)] Agent shutdown failed: TERM_PID is empty (source: $PID_SOURCE)" >> ~/.gobby/logs/agent_shutdown.log
    exit 1
fi

if ! echo "$TERM_PID" | grep -qE '^[0-9]+$'; then
    echo "[$(date -Iseconds)] Agent shutdown failed: TERM_PID '$TERM_PID' is not numeric (source: $PID_SOURCE)" >> ~/.gobby/logs/agent_shutdown.log
    exit 1
fi

if ! ps -p "$TERM_PID" >/dev/null 2>&1; then
    echo "[$(date -Iseconds)] Agent shutdown failed: Process $TERM_PID does not exist (source: $PID_SOURCE)" >> ~/.gobby/logs/agent_shutdown.log
    exit 1
fi

# Log the shutdown
echo "[$(date -Iseconds)] Agent shutdown initiated for terminal PID: $TERM_PID (source: $PID_SOURCE, signal: $SIGNAL)" >> ~/.gobby/logs/agent_shutdown.log

# Give a moment for any pending output to flush
sleep 1

# Kill the terminal process (this will close the window)
kill -"$SIGNAL" "$TERM_PID" 2>/dev/null || true

# If still alive after 2 seconds, force kill
sleep 2
kill -9 "$TERM_PID" 2>/dev/null || true

