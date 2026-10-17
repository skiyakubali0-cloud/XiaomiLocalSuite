#!/system/bin/sh
# Undo only enablement changes explicitly made by the suite's stock-app controls.
umask 077
STOCK_ROOT=/data/adb/xuanyuan-os4-suite-state
STOCK_STATE=$STOCK_ROOT/stock-apps
STOCK_BOOT=$(cat /proc/sys/kernel/random/boot_id) || exit 1
[ -n "$STOCK_BOOT" ] || exit 1
if [ -n "${XLS_STOCK_PARENT:-}" ]; then
 [ "$XLS_STOCK_PARENT" = "$PPID" ] && [ "$(cat "$STOCK_ROOT/lock/pid" 2>/dev/null)" = "$PPID" ] &&
 [ "$(cat "$STOCK_ROOT/lock/boot" 2>/dev/null)" = "$STOCK_BOOT" ] || { echo '电话恢复任务锁不匹配' >&2; exit 1; }
else
 mkdir -p "$STOCK_ROOT" || exit 1
 mkdir "$STOCK_ROOT/lock" 2>/dev/null || { echo '已有组件任务，请稍后恢复原应用' >&2; exit 1; }
 stock_unlock() { rm -f "$STOCK_ROOT/lock/boot" "$STOCK_ROOT/lock/pid" "$STOCK_ROOT/lock/created"; rmdir "$STOCK_ROOT/lock"; }
 trap stock_unlock EXIT
 trap 'exit 130' INT TERM
 printf '%s\n' "$STOCK_BOOT" > "$STOCK_ROOT/lock/boot" && printf '%s\n' "$$" > "$STOCK_ROOT/lock/pid" &&
 date +%s > "$STOCK_ROOT/lock/created" || exit 1
fi
for STOCK_ID in phone sms; do
 [ -e "$STOCK_STATE/$STOCK_ID.disabled" ] || continue
 case "$STOCK_ID" in phone) STOCK_PKG=com.google.android.dialer;; sms) STOCK_PKG=com.google.android.apps.messaging;; esac
 STOCK_LIST=$(pm list packages --user 0 "$STOCK_PKG") || exit 1
 printf '%s\n' "$STOCK_LIST" | grep -qx "package:$STOCK_PKG" || { echo "原应用不存在，请先恢复 $STOCK_PKG" >&2; exit 1; }
 pm enable --user 0 "$STOCK_PKG" || exit 1
 STOCK_LIST=$(pm list packages -e --user 0 "$STOCK_PKG") || exit 1
 printf '%s\n' "$STOCK_LIST" | grep -qx "package:$STOCK_PKG" || { echo "原应用启用未确认：$STOCK_PKG" >&2; exit 1; }
 rm -f "$STOCK_STATE/$STOCK_ID.disabled" || exit 1
done
