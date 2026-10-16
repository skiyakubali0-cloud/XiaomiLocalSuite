#!/system/bin/sh
[ "$KSU" = true ] || abort "KernelSU required"
[ "$(getprop ro.product.device)" = xuanyuan ] || abort "xuanyuan only"
[ "$(getprop ro.build.version.sdk)" = 37 ] || abort "Android 17 only"
[ "$(getprop ro.build.version.incremental)" = OS4.0.0.6.XOAEUXM ] || abort "This release requires OS4.0.0.6.XOAEUXM"
[ -x /data/adb/metamodule/meta-overlayfs ] || abort "Activate OverlayFS MetaModule first"
(cd "$MODPATH" && sha256sum -c checksums.sha256) || abort "Payload hash mismatch"
set_perm_recursive "$MODPATH" 0 0 0755 0644
for script in "$MODPATH"/*.sh; do set_perm "$script" 0 0 0755; done
ui_print "- Original xuanyuan CN Android 17 APK; reboot required"
