#!/system/bin/sh
MODDIR=${0%/*}
STATE=/data/adb/xuanyuan-weather-state
# One watcher per boot, including manual starts after an in-place module update.
mkdir "$STATE/watch.lock" 2>/dev/null || exit 0
trap 'rmdir "$STATE/watch.lock"' EXIT
while [ "$(getprop sys.boot_completed)" != 1 ]; do sleep 2; done
sh "$MODDIR/core.sh" 2>&1 | cat > "$STATE/core-status.log"
LAST=initial
while [ -d "$MODDIR" ] && [ ! -e "$MODDIR/disable" ] && [ ! -e "$MODDIR/remove" ]; do
 LIVE=$(pm path --user 0 com.miui.weather2 2>/dev/null)
 if [ -n "$LIVE" ] && [ "$LIVE" != "$LAST" ]; then
  sleep 3
  sh "$MODDIR/apply.sh" 2>&1 | cat > "$STATE/status.log"
  LAST="$LIVE"
 fi
 sleep 10
done
