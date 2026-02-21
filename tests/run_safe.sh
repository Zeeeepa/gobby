#!/bin/bash
# Run tests and auto-restore hook_dispatcher.py if deleted
HOOK="/Users/josh/.gobby/hooks/hook_dispatcher.py"
SRC="/Users/josh/Projects/gobby/src/gobby/install/shared/hooks/hook_dispatcher.py"

# Restore before
[ ! -f "$HOOK" ] && cp "$SRC" "$HOOK"

# Run whatever tests are passed as arguments
uv run pytest "$@"
EXIT=$?

# Check and restore after
if [ ! -f "$HOOK" ]; then
    echo ""
    echo ">>> HOOK FILE WAS DELETED BY TEST RUN <<<"
    cp "$SRC" "$HOOK"
    echo ">>> Restored."
fi

exit $EXIT
