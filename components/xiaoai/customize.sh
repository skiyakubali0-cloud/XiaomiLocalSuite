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

pm list libraries | grep '^library:vendor.xiaomi.hardware.misys.V3_0$' >/dev/null || abort "VoiceTrigger requires misys V3_0"

[ -d /data/adb/modules/zygisk_lsposed ] || abort 'AI权限管理需要 LSPosed'
[ "$(sha256sum /system_ext/framework/miui-services.jar | cut -d' ' -f1)" = cef17afe99cfa6396922e2fe1dce6642ec86ddcf141589b8ef4d007d6920ecdb ] || abort 'miui-services 版本不匹配'
AI_ENGINE=$(pm path --user 0 com.xiaomi.aicr | sed -n 's/^package://p')
[ -f "$AI_ENGINE" ] || abort '小米澎湃AI引擎缺失或不是单APK安装'
[ "$(sha256sum "$AI_ENGINE" | cut -d' ' -f1)" = f081299f3e638d188a2d3d2ace6aeef4ab9d0226f775fc7474495812f67b8520 ] || abort 'AI引擎版本不匹配：小爱建议需要原版4.12.19'
ui_print '统一设置中手动启用 AI识屏智控、小爱建议并核对作用域；协议由用户确认。'
