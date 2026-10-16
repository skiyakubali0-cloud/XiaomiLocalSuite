#!/system/bin/sh
[ "$KSU" = true ] || abort "KernelSU required"
[ "$(getprop ro.product.device)" = xuanyuan ] || abort "xuanyuan only"
[ "$(getprop ro.build.version.sdk)" = 37 ] || abort "Android 17 only"
[ "$(getprop ro.build.version.incremental)" = OS4.0.0.6.XOAEUXM ] || abort "OS4.0.0.6.XOAEUXM only"
[ -x /data/adb/metamodule/meta-overlayfs ] || abort "Activate OverlayFS MetaModule first"
[ -f /data/adb/modules/zygisk_lsposed/module.prop ] || abort "LSPosed required for SMS and recording compatibility"
pm path com.xiaomi.market | grep '^package:' >/dev/null || abort "Install the Xiaomi Market module first"
pm list libraries | grep '^library:micloud-sdk$' >/dev/null || abort "micloud-sdk missing"
(cd "$MODPATH" && sha256sum -c checksums.sha256) || abort "Payload mismatch"
STATE=/data/adb/xuanyuan-os4-phone-state
mkdir -p "$STATE"
chmod 700 "$STATE"
if [ ! -e "$STATE/before-dialer" ]; then
  OLD_DIALER=$(cmd role get-role-holders --user 0 android.app.role.DIALER)
  OLD_SMS=$(cmd role get-role-holders --user 0 android.app.role.SMS)
  [ -n "$OLD_DIALER" ] && [ -n "$OLD_SMS" ] || abort "Cannot save current defaults"
  echo "$OLD_DIALER" > "$STATE/before-dialer"
  echo "$OLD_SMS" > "$STATE/before-sms"
fi
mkdir -p /data/adb/service.d
cp "$MODPATH/recording-cleanup.sh" /data/adb/service.d/xuanyuan-phone-recording-cleanup.sh
chmod 755 /data/adb/service.d/xuanyuan-phone-recording-cleanup.sh
set_perm_recursive "$MODPATH" 0 0 0755 0644
for script in "$MODPATH"/*.sh; do set_perm "$script" 0 0 0755; done
ui_print "- Reboot required; Google apps and provider data preserved"
