#!/system/bin/sh
MODDIR=${0%/*}
STATE=/data/adb/xuanyuan-os4-xiaoai-state
mkdir -p "$STATE"
chmod 700 "$STATE"
run() {
for i in $(seq 1 120); do
  [ "$(getprop sys.boot_completed)" = 1 ] && break
  sleep 2
done
[ "$(getprop sys.boot_completed)" = 1 ] || exit 1
[ "$(getprop ro.product.device)" = xuanyuan ] && [ "$(getprop ro.build.version.sdk)" = 37 ] && [ "$(getprop ro.build.version.incremental)" = OS4.0.0.6.XOAEUXM ] || return 1
PKG=com.miui.voiceassist
APP_PATH=$(pm path --user 0 "$PKG")
case "$APP_PATH" in
  package:/data/app/*) ;;
  package:/product/*)
    # A same-signed update keeps resources visible to apps with hidden mounts.
    RESULT=$(pm install -r --user 0 -i com.xiaomi.market /product/priv-app/VoiceAssistAndroidT/VoiceAssistAndroidT.apk 2>&1)
    echo "$RESULT"
    [ "$RESULT" = Success ] || return 1
    ;;
  *) echo 'ERROR: package not registered'; return 1 ;;
esac
while IFS='|' read -r COMPANION SOURCE EXPECTED; do
  LIVE=$(pm path --user 0 "$COMPANION" | sed -n 's/^package://p')
  case "$LIVE" in
    /data/app/*) echo "$COMPANION: existing update retained" ;;
    /product/*)
      ACTUAL=$(sha256sum "$SOURCE" | cut -d' ' -f1)
      [ "$ACTUAL" = "$EXPECTED" ] || { echo "ERROR: $COMPANION source mismatch"; return 1; }
      RESULT=$(pm install -r --user 0 -i com.xiaomi.market "$SOURCE" 2>&1)
      echo "$COMPANION: $RESULT"
      [ "$RESULT" = Success ] || return 1
      ;;
    *) echo "ERROR: $COMPANION not registered"; return 1 ;;
  esac
done < "$MODDIR/companions.txt"
sh "$MODDIR/suggestion-permissions.sh" || echo 'Suggestions: permission setup pending; see log'
echo 'REGISTERED: XiaoAI and eight companion apps. Feature consent and hardware/cloud behavior require separate validation.'

}
# Binder shell commands cannot receive log-file descriptors under /data/adb.
run 2>&1 | tee "$STATE/status.log"
