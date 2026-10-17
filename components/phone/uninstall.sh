#!/system/bin/sh
STATE=/data/adb/xuanyuan-os4-phone-state
if [ -n "${XLS_STOCK_PARENT:-}" ]; then
 [ "$XLS_STOCK_PARENT" = "$PPID" ] && [ "$(cat /data/adb/xuanyuan-os4-suite-state/lock/pid 2>/dev/null)" = "$PPID" ] &&
 [ "$(cat /data/adb/xuanyuan-os4-suite-state/lock/boot 2>/dev/null)" = "$(cat /proc/sys/kernel/random/boot_id)" ] || exit 1
else
 # Sourcing keeps the recovery lock until the entire uninstall has finished.
 . "${0%/*}/restore-stock.sh" || exit 1
fi
if [ "$(cmd role get-role-holders --user 0 android.app.role.DIALER)" = com.android.contacts ]; then
  OLD=$(cat "$STATE/before-dialer")
  [ -n "$OLD" ] && cmd role add-role-holder --user 0 android.app.role.DIALER "$OLD" 0
fi
if [ "$(cmd role get-role-holders --user 0 android.app.role.SMS)" = com.android.mms ]; then
  OLD=$(cat "$STATE/before-sms")
  [ -n "$OLD" ] && cmd role add-role-holder --user 0 android.app.role.SMS "$OLD" 0
fi
cmd overlay disable --user 0 com.android.shell:XuanyuanCallRecording
MODDIR=${0%/*}
APK="$MODDIR/payload/MiuiAudioMonitor-eea.apk"
LIVE=$(pm path com.miui.audiomonitor | sed -n 's/^package://p')
HASH=$(sha256sum "$LIVE" 2>/dev/null | cut -d' ' -f1)
if [ "$HASH" = 83133a62f37cefe873075064d39c5e176e768af251d678438a242116be8178b1 ] && [ -f "$APK" ]; then
  cat "$APK" | pm install -r --user 0 -i com.xiaomi.market -S "$(stat -c %s "$APK")"
fi
APK="$MODDIR/payload/MIUIYellowPage-eea.apk"
LIVE=$(pm path com.miui.yellowpage | sed -n 's/^package://p')
HASH=$(sha256sum "$LIVE" 2>/dev/null | cut -d' ' -f1)
if [ "$HASH" = e07e59b9d9a99b0cce4bf06b9734002016b1c3bebe701c6ee368cdc8161cb733 ] && [ -f "$APK" ]; then
  cat "$APK" | pm install -r --user 0 -i com.xiaomi.market -S "$(stat -c %s "$APK")"
fi
echo 'Phone mount disabled after reboot; turn off phone in unified settings. Shared APK retained.'
