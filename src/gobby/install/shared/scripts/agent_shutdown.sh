#!/bin/bash
# agent_shutdown.sh - Gracefully terminate the agent's terminal session
# VERSION: 2.0.0
# Installed by: uv run gobby install --gemini
#
# This script is used by the meeseeks workflow to self-terminate
# after completing its assigned task.

# Get the current terminal's parent PID (the shell's parent is the terminal)
TERM_PID=$(ps -o ppid= -p $$ | tr -d ' ')

# Create log directory if it doesn't exist
mkdir -p ~/.gobby/logs

# Validate TERM_PID is non-empty, numeric, and process exists
if [ -z "$TERM_PID" ]; then
    echo "[$(date -Iseconds)] Agent shutdown failed: TERM_PID is empty" >> ~/.gobby/logs/agent_shutdown.log
    exit 1
fi

if ! echo "$TERM_PID" | grep -qE '^[0-9]+$'; then
    echo "[$(date -Iseconds)] Agent shutdown failed: TERM_PID '$TERM_PID' is not numeric" >> ~/.gobby/logs/agent_shutdown.log
    exit 1
fi

if ! ps -p "$TERM_PID" >/dev/null 2>&1; then
    echo "[$(date -Iseconds)] Agent shutdown failed: Process $TERM_PID does not exist" >> ~/.gobby/logs/agent_shutdown.log
    exit 1
fi

# Log the shutdown
echo "[$(date -Iseconds)] Agent shutdown initiated for terminal PID: $TERM_PID" >> ~/.gobby/logs/agent_shutdown.log

# Give a moment for any pending output to flush
sleep 1

# Kill the terminal process (this will close the window)
# Use SIGTERM for graceful shutdown
kill -TERM "$TERM_PID" 2>/dev/null || true

# If still alive after 2 seconds, force kill
sleep 2
kill -9 "$TERM_PID" 2>/dev/null || true

