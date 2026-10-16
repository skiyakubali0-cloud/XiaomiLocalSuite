#!/system/bin/sh
MODDIR=${0%/*}
STATE=/data/adb/xuanyuan-os4-phone-state
mkdir -p "$STATE"
chmod 700 "$STATE"
run() {
for i in $(seq 1 120); do
  [ "$(getprop sys.boot_completed)" = 1 ] && break
  sleep 2
done
[ "$(getprop sys.boot_completed)" = 1 ] || return 1
cmd overlay disable --user 0 com.android.shell:XuanyuanCallRecording 2>/dev/null
[ "$(getprop ro.product.device)" = xuanyuan ] && [ "$(getprop ro.build.version.sdk)" = 37 ] && [ "$(getprop ro.build.version.incremental)" = OS4.0.0.6.XOAEUXM ] || return 1
echo 'Compatibility is supplied by unified API102; choose phone in unified settings.'
YELLOW_PATH=$(pm path com.miui.yellowpage | sed -n 's/^package://p')
YELLOW_HASH=$(sha256sum "$YELLOW_PATH" | cut -d' ' -f1)
case "$YELLOW_HASH" in
  e07e59b9d9a99b0cce4bf06b9734002016b1c3bebe701c6ee368cdc8161cb733) ;;
  0c5c655fe93ffc0eade6a77dc56c05754d4a3afab8a6c122acd3a2f8a160c0ba)
    APK="$MODDIR/payload/MIUIYellowPage-cn.apk"
    cat "$APK" | pm install -r --user 0 -i com.xiaomi.market -S "$(stat -c %s "$APK")" || return 1
    ;;
  *) echo 'ERROR: unsupported YellowPage update; no downgrade attempted'; return 1 ;;
esac
for pair in com.android.contacts:MIUIContactsT com.android.incallui:InCallUI com.android.mms:MiuiMms; do
  PKG=${pair%:*}
  DIR=${pair#*:}
  APP_PATH=$(pm path --user 0 "$PKG")
  case "$APP_PATH" in
    package:/data/app/*) ;;
    package:/product/*)
      RESULT=$(pm install -r --user 0 -i com.xiaomi.market /product/priv-app/$DIR/$DIR.apk 2>&1)
      echo "$PKG: $RESULT"
      [ "$RESULT" = Success ] || return 1
      ;;
    *) echo "ERROR: $PKG not registered"; return 1 ;;
  esac
done
if [ ! -e "$STATE/incall-permissions-v1" ]; then
  for PERM in POST_NOTIFICATIONS READ_PHONE_STATE READ_CONTACTS READ_CALL_LOG BLUETOOTH_CONNECT; do
    pm grant --user 0 com.android.incallui "android.permission.$PERM" || return 1
  done
  touch "$STATE/incall-permissions-v1"
fi
MONITOR_PATH=$(pm path com.miui.audiomonitor | sed -n 's/^package://p')
MONITOR_HASH=$(sha256sum "$MONITOR_PATH" | cut -d' ' -f1)
case "$MONITOR_HASH" in
  83133a62f37cefe873075064d39c5e176e768af251d678438a242116be8178b1|f84954e6ef361a8204c565bfe365e66344e2984036febe784c1485e113d1ba71) ;;
  *) echo 'ERROR: unsupported AudioMonitor update; recording adaptation stopped'; return 1 ;;
esac
case "$MONITOR_PATH:$MONITOR_HASH" in
  /data/app/*:83133a62f37cefe873075064d39c5e176e768af251d678438a242116be8178b1) ;;
  *)
    APK="$MODDIR/system/system_ext/app/MiuiAudioMonitor/MiuiAudioMonitor.apk"
    SIZE=$(stat -c %s "$APK")
    cat "$APK" | pm install -r --user 0 -i com.xiaomi.market -S "$SIZE" || return 1
    ;;
esac
if [ ! -e "$STATE/record-permission-v1" ]; then
  pm grant --user 0 com.android.incallui android.permission.RECORD_AUDIO || return 1
  touch "$STATE/record-permission-v1"
fi
cmd overlay fabricate --target com.android.phone --name XuanyuanCallRecording com.android.phone:bool/config_call_recording 0x12 0x1 || return 1
cmd overlay enable --user 0 com.android.shell:XuanyuanCallRecording || return 1
VALUE=$(cmd overlay lookup com.android.phone com.android.phone:bool/config_call_recording)
[ "$VALUE" = true ] || { echo 'ERROR: call recording overlay inactive'; return 1; }
echo 'REGISTERED: phone, SMS, call recording capability and CN AudioMonitor; consent and real recordings require user testing'
}
run 2>&1 | tee "$STATE/status.log"
