#!/bin/sh
# XLS_PYTHON is an executable path, not a command with arguments.
cd -P "$(dirname "$0")/.." || exit 1
export PYTHONDONTWRITEBYTECODE=1
export TK_SILENCE_DEPRECATION=1
if [ -n "${XLS_PYTHON:-}" ]; then
    "$XLS_PYTHON" ./launch.py "$@"
    xls_status=$?
else
    xls_status=1
    for xls_python in python3.13 python3.12 python3.11 python3 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 /usr/local/bin/python3; do
        if command -v "$xls_python" >/dev/null 2>&1 && "$xls_python" ./launch.py --check >/dev/null 2>&1; then
            "$xls_python" ./launch.py "$@"
            xls_status=$?
            break
        fi
    done
fi
if [ "$xls_status" -ne 0 ]; then
    printf '%s\n' 'Python 3.11+ with Tk 8.6+ is required. Set XLS_PYTHON to its executable path.' >&2
    if [ "$#" -eq 0 ] && [ -t 0 ]; then
        printf '%s\n' 'Press Enter to close.'
        read -r xls_answer
    fi
fi
exit "$xls_status"
