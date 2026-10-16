#!/system/bin/sh
set -eu
MODDIR=${0%/*}
STATE=/data/adb/xuanyuan-weather-state
CN=2a8faed30ce5ffe4ae0229dce0d520d882dff990f6ef158e5fbb555153b7e887
GLOBAL=9439e87555133762d362bfba651e7ab6e2f01e78b280fdd7ec745cbb6403b025
PATCHED=1aff04e6b7706980cf311b7cc128887aae54c43f6b69df13affc1779ae0d3e16
ORIGINAL=d631a3cdbce74d192d3304d23f8f7b369a18e4718c2905523466aee6eb11d85c
file_sha() { sha256sum "$1" | cut -d' ' -f1; }
[ "$(getprop ro.product.device)" = xuanyuan ] && [ "$(getprop ro.build.version.sdk)" = 37 ] && [ "$(getprop ro.build.version.incremental)" = OS4.0.0.6.XOAEUXM ] || exit 1

[ "$(file_sha "$MODDIR/payload/cn.apk")" = "$CN" ] && [ "$(file_sha "$MODDIR/payload/libweather_app.so")" = "$PATCHED" ] || exit 1
mkdir "$STATE/apply.lock" 2>/dev/null || exit 0
trap 'rmdir "$STATE/apply.lock"' EXIT
LIVE=$(pm path --user 0 com.miui.weather2 | sed -n 's/^package://p')
[ -f "$LIVE" ] || exit 1
case "$(file_sha "$LIVE")" in
 "$CN"|"017d613137c0512a937dc6b8565da856099e988feab47b9eabc5c3d0a13f06e6") ;;
 "$GLOBAL") cat "$MODDIR/payload/cn.apk" | pm install -r -d --user 0 -i com.xiaomi.market -S "$(stat -c %s "$MODDIR/payload/cn.apk")" || exit 1 ;;
 *) echo 'Unsupported weather update; no changes'; exit 1 ;;
esac
LIVE=$(pm path --user 0 com.miui.weather2 | sed -n 's/^package://p')
APK_SHA=$(file_sha "$LIVE")
OFFSET=6513632
SOURCE="$MODDIR/payload/libweather_app.so"
case "$APK_SHA" in
 "$CN") ;;
 "017d613137c0512a937dc6b8565da856099e988feab47b9eabc5c3d0a13f06e6")
 ORIGINAL=0b142053c411c132cd5dbbd0ac2d56f7b52271af78e7962ee4ef52ebdb357cf6
 PATCHED=96f7cabbe8710418b2286dc50bd5dc519a5fad5f794f6827b332b660e4a47c72
 OFFSET=6531104
 SOURCE="$MODDIR/payload/libweather27.so" ;;
 *) exit 1 ;;
esac
[ "$(file_sha "$SOURCE")" = "$PATCHED" ] || exit 1
TARGET=${LIVE%/*}/lib/arm64/libweather_app.so
case "$TARGET" in /data/app/*/lib/arm64/libweather_app.so) ;; *) echo 'Unexpected native path'; exit 1;; esac
case "$(file_sha "$TARGET")" in
 "$PATCHED") echo 'Weather native compatibility already applied'; exit 0 ;;
 "$ORIGINAL") ;;
 *) echo 'Native library changed; no changes'; exit 1 ;;
esac
am force-stop com.miui.weather2
# Change only the verified PLT entry in Weather's extracted library. No shared runtime edits.
if ! dd if="$SOURCE" of="$TARGET" bs=1 skip="$OFFSET" seek="$OFFSET" count=16 conv=notrunc; then
 sh "$STATE/restore.sh"
 exit 1
fi
if [ "$(file_sha "$TARGET")" != "$PATCHED" ]; then
 sh "$STATE/restore.sh"
 exit 1
fi
echo 'READY: original CN APK with weather-only native compatibility'
