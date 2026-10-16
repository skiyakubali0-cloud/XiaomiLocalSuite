#!/system/bin/sh
M=${0%/*}
# Binder commands must receive a pipe rather than a private /data/adb log fd.
sh "$M/control.sh" worker "$1" "$2" "$3" 2>&1 | /data/adb/ksu/bin/busybox tee "$1/log" >/dev/null
