#!/system/bin/sh
[ "$KSU" = true ] || abort '需要 KernelSU'
[ "$(getprop ro.product.device)" = xuanyuan ] && [ "$(getprop ro.build.version.sdk)" = 37 ] && [ "$(getprop ro.build.version.incremental)" = OS4.0.0.6.XOAEUXM ] || abort '仅支持小米15 Ultra EEA OS4.0.0.6 / Android17'
(cd "$MODPATH" && sha256sum -c checksums.sha256) || abort '套件文件校验失败'
set_perm_recursive "$MODPATH" 0 0 0755 0644
for script in "$MODPATH"/*.sh; do set_perm "$script" 0 0 0755; done
ui_print '套件安装完成。重启后打开 WebUI 勾选所需功能。'
ui_print '本次只安装管理入口，不改动现有功能，不重置钱包，不接受协议。'
