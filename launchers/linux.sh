#!/bin/sh
# XLS_PYTHON is an executable path, not a command with arguments.
cd -P "$(dirname "$0")/.." || exit 1
export PYTHONDONTWRITEBYTECODE=1
if [ -n "${XLS_PYTHON:-}" ]; then
    exec "$XLS_PYTHON" ./launch.py "$@"
fi
for xls_python in python3.13 python3.12 python3.11 python3; do
    if command -v "$xls_python" >/dev/null 2>&1 && "$xls_python" ./launch.py --check >/dev/null 2>&1; then
        exec "$xls_python" ./launch.py "$@"
    fi
done
printf '%s\n' 'Python 3.11+ with Tk 8.6+ is required. Set XLS_PYTHON to its executable path.' >&2
exit 1
