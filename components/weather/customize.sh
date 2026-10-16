#!/system/bin/sh
[ "$KSU" = true ] || abort 'KernelSU required'
[ "$(getprop ro.product.device)" = xuanyuan ] && [ "$(getprop ro.build.version.sdk)" = 37 ] && [ "$(getprop ro.build.version.incremental)" = OS4.0.0.6.XOAEUXM ] || abort 'Exact xuanyuan EEA OS4.0.0.6 required'
[ "$(sha256sum /product/data-app/MIUIWeatherGlobal/MIUIWeatherGlobal.apk | cut -d' ' -f1)" = 9439e87555133762d362bfba651e7ab6e2f01e78b280fdd7ec745cbb6403b025 ] || abort 'Factory Weather mismatch'
(cd "$MODPATH" && sha256sum -c checksums.sha256) || abort 'Payload mismatch'
set_perm_recursive "$MODPATH" 0 0 0755 0644
for s in "$MODPATH"/*.sh; do set_perm "$s" 0 0 0755; done
STATE=/data/adb/xuanyuan-weather-state
mkdir -p "$STATE"
chmod 700 "$STATE"
cp "$MODPATH/payload/global.apk" "$STATE/global.apk"
cp "$MODPATH/payload/core-global.apk" "$STATE/core-global.apk"
chmod 600 "$STATE/core-global.apk"
cp "$MODPATH/restore.sh" "$STATE/restore.sh"
chmod 600 "$STATE/global.apk"
chmod 700 "$STATE/restore.sh"
ui_print 'Reboot to apply. No LSPosed needed. Weather app data is retained.'
ui_print 'Disabling retains installed CN APK and patched library. Recovery: su -c "sh /data/adb/xuanyuan-weather-state/restore.sh"'
