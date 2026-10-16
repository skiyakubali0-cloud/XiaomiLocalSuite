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

# Can also be run from the retained state directory when this module is disabled.
[ "$(file_sha "$STATE/global.apk")" = "$GLOBAL" ] || exit 1
LIVE=$(pm path --user 0 com.miui.weather2 | sed -n 's/^package://p')
case "$(file_sha "$LIVE")" in
 "$GLOBAL") echo 'Global Weather already restored';;
 "$CN"|"017d613137c0512a937dc6b8565da856099e988feab47b9eabc5c3d0a13f06e6")
  am force-stop com.miui.weather2
  TARGET=${LIVE%/*}/lib/arm64/libweather_app.so
  case "$TARGET" in /data/app/*/lib/arm64/libweather_app.so) umount "$TARGET" 2>/dev/null || true;; esac
  cat "$STATE/global.apk" | pm install -r -d --user 0 -S "$(stat -c %s "$STATE/global.apk")" || exit 1
  echo 'Global Weather restored without clearing data';;
 *) echo 'Unrecognized newer Weather; not overwritten'; exit 1;;
esac
[ ! -d /data/adb/modules/xuanyuan-os4-weather ] || touch /data/adb/modules/xuanyuan-os4-weather/disable

# Restore only the exact core installed by this module, preserving its data.
CORE=$(pm path --user 0 com.miui.core | sed -n 's/^package://p')
case "$(file_sha "$CORE")" in
 5abe56881dafbe3540e11c4ff4a450ae7bcd19d93753a251326f09314a2bb9e9)
  [ "$(file_sha "$STATE/core-global.apk")" = 585703b25f0bce27f06f76ed568af9a9bbf58bcf7810600ad23eb4ab57be6902 ] || exit 1
  cat "$STATE/core-global.apk" | pm install -r -d --user 0 -S "$(stat -c %s "$STATE/core-global.apk")" || exit 1
  rm -f "$STATE/core-permissions-set" ;;
 585703b25f0bce27f06f76ed568af9a9bbf58bcf7810600ad23eb4ab57be6902) ;;
 *) echo 'Unknown XmsCore retained; core rollback incomplete'; exit 1 ;;
esac
