#!/system/bin/sh
set -eu
MODDIR=${0%/*}
STATE=/data/adb/xuanyuan-weather-state
[ "$(getprop ro.product.device)" = xuanyuan ] && [ "$(getprop ro.build.version.incremental)" = OS4.0.0.6.XOAEUXM ] || exit 1
file_sha() { sha256sum "$1" | cut -d' ' -f1; }
[ "$(file_sha "$MODDIR/payload/core-cn.apk")" = 5abe56881dafbe3540e11c4ff4a450ae7bcd19d93753a251326f09314a2bb9e9 ] || exit 1
LIVE=$(pm path --user 0 com.miui.core | sed -n 's/^package://p')
case "$(file_sha "$LIVE")" in
 5abe56881dafbe3540e11c4ff4a450ae7bcd19d93753a251326f09314a2bb9e9) ;;
 585703b25f0bce27f06f76ed568af9a9bbf58bcf7810600ad23eb4ab57be6902) cat "$MODDIR/payload/core-cn.apk" | pm install -r --user 0 -S "$(stat -c %s "$MODDIR/payload/core-cn.apk")" || exit 1 ;;
 *) echo 'Unknown XmsCore version; not overwritten'; exit 1 ;;
esac
# One-time permission setup; later user revocations remain respected.
if [ ! -e "$STATE/core-permissions-set" ]; then
 pm grant com.miui.core android.permission.ACCESS_COARSE_LOCATION
 pm grant com.miui.core android.permission.ACCESS_FINE_LOCATION
 pm grant com.miui.core android.permission.ACCESS_BACKGROUND_LOCATION
 touch "$STATE/core-permissions-set"
fi
