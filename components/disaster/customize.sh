#!/system/bin/sh
REMOVE="/system/product/priv-app/MIUISecurityCenterGlobal/MIUISecurityCenterGlobal.apk"
[ "$KSU" = true ] || abort 'KernelSU required'
[ "$(getprop ro.product.device)" = xuanyuan ] && [ "$(getprop ro.build.version.sdk)" = 37 ] && [ "$(getprop ro.build.version.incremental)" = OS4.0.0.6.XOAEUXM ] || abort 'Exact xuanyuan EEA OS4.0.0.6 required'
[ -x /data/adb/metamodule/meta-overlayfs ] || abort 'OverlayFS MetaModule required'
mountpoint -q /data/adb/metamodule/mnt || abort 'Reboot once after enabling OverlayFS MetaModule first'
[ -d /data/adb/modules/zygisk_lsposed ] || abort 'LSPosed required'
LIVE=$(pm path --user 0 com.miui.securitycenter | sed -n 's/^package://p')
case "$LIVE" in
 /product/priv-app/MIUISecurityCenterGlobal/MIUISecurityCenterGlobal.apk|/product/priv-app/MIUISecurityCenterWarning/MIUISecurityCenterWarning.apk) ;;
 *) abort 'Remove SecurityCenter /data/app update first';;
esac
case "$(sha256sum "$LIVE" | cut -d' ' -f1)" in
 da9c99b77d29f8052bd71ec98fa8736ba7b04ed13881ffb09575db1d592af793|f3d338484cc5fd3f3fec9e8d9d0b4c6370923fba0f5e0d81975a45e914cbc776) ;;
 *) abort 'Unsupported SecurityCenter source';;
esac
(cd "$MODPATH" && sha256sum -c checksums.sha256) || abort 'Payload hash mismatch'
STATE=/data/adb/xuanyuan-disaster-state
mkdir -p "$STATE"
chmod 700 "$STATE"
if [ ! -e "$STATE/preinstall-securitycenter.tar" ]; then
 am force-stop com.miui.securitycenter
 tar -cf "$STATE/preinstall-securitycenter.tar" -C / data/user/0/com.miui.securitycenter data/user_de/0/com.miui.securitycenter || abort 'Backup failed'
 chmod 600 "$STATE/preinstall-securitycenter.tar"
 getprop ro.build.version.incremental > "$STATE/backup-rom.txt"
fi
chown -R 0:0 "$MODPATH"
find "$MODPATH" -type d -exec chmod 0755 {} +
find "$MODPATH" -type f -exec chmod 0644 {} +
for script in "$MODPATH"/*.sh; do chmod 0755 "$script"; done
cp "$MODPATH/restore.sh" "$STATE/restore.sh"
chmod 700 "$STATE/restore.sh"
ui_print '统一设置中手动启用预警兼容；作用域仅手机管家，然后重启。'
ui_print 'Full SecurityCenter overlay. Disable module and reboot to restore stock APK; app data is retained.'
