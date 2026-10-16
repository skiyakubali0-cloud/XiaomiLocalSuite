#!/system/bin/sh
MODDIR=${0%/*}
STATE=/data/adb/xuanyuan-os4-market-state
mkdir -p "$STATE"
chmod 700 "$STATE"
run() {
for i in $(seq 1 120); do
  [ "$(getprop sys.boot_completed)" = 1 ] && break
  sleep 2
done
[ "$(getprop sys.boot_completed)" = 1 ] || exit 1
PKG=com.xiaomi.market
APP_PATH=$(pm path --user 0 "$PKG")
case "$APP_PATH" in
  package:/data/app/*) ;;
  package:/product/*)
    # A same-signed update keeps resources visible to apps with hidden mounts.
    RESULT=$(pm install -r --user 0 -i com.xiaomi.market /product/app/MIUISuperMarket/MIUISuperMarket.apk 2>&1)
    echo "$RESULT"
    [ "$RESULT" = Success ] || return 1
    ;;
  *) echo 'ERROR: package not registered'; return 1 ;;
esac
echo 'REGISTERED: com.xiaomi.market; UI validation remains separate'

if [ -e "$STATE/keep-getapps" ]; then
  pm enable --user 0 com.xiaomi.mipicks
else
  pm disable-user --user 0 com.xiaomi.mipicks
fi

}
# Binder shell commands cannot receive log-file descriptors under /data/adb.
run 2>&1 | tee "$STATE/status.log"
