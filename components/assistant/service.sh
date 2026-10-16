#!/system/bin/sh
MODDIR=${0%/*}
STATE=/data/adb/xuanyuan-os4-assistant-state
mkdir -p "$STATE"
chmod 700 "$STATE"
run() {
for i in $(seq 1 120); do
  [ "$(getprop sys.boot_completed)" = 1 ] && break
  sleep 2
done
[ "$(getprop sys.boot_completed)" = 1 ] || exit 1
PKG=com.miui.personalassistant
APP_PATH=$(pm path --user 0 "$PKG")
case "$APP_PATH" in
  package:/data/app/*) ;;
  package:/product/*)
    # A same-signed update keeps resources visible to apps with hidden mounts.
    RESULT=$(pm install -r --user 0 -i com.xiaomi.market /product/priv-app/MIUIPersonalAssistantPhoneOS4/MIUIPersonalAssistantPhoneOS4.apk 2>&1)
    echo "$RESULT"
    [ "$RESULT" = Success ] || return 1
    ;;
  *) echo 'ERROR: package not registered'; return 1 ;;
esac
echo 'REGISTERED: com.miui.personalassistant; UI validation remains separate'

if [ ! -e "$STATE/route-initialized" ]; then
  if [ -e "$MODDIR/use_china" ]; then
    sh "$MODDIR/control.sh" china || return 1
  else
    sh "$MODDIR/control.sh" google || return 1
  fi
  touch "$STATE/route-initialized"
fi

}
# Binder shell commands cannot receive log-file descriptors under /data/adb.
run 2>&1 | tee "$STATE/status.log"
