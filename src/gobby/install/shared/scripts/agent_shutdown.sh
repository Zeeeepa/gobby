#!/bin/bash
# agent_shutdown.sh - Gracefully terminate the agent's terminal session
# Installed by: uv run gobby install --gemini
#
# This script is used by the meeseeks workflow to self-terminate
# after completing its assigned task.

# Get the current terminal's parent PID (the shell's parent is the terminal)
TERM_PID=$(ps -o ppid= -p $$ | tr -d ' ')

# Create log directory if it doesn't exist
mkdir -p ~/.gobby/logs

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
