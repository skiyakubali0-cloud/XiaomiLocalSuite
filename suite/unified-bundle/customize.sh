#!/system/bin/sh
[ "$KSU" = true ] || abort '需要 KernelSU'
[ "$(getprop ro.product.device)" = xuanyuan ] && [ "$(getprop ro.build.version.sdk)" = 37 ] && [ "$(getprop ro.build.version.incremental)" = OS4.0.0.6.XOAEUXM ] || abort '仅支持小米15 Ultra EEA OS4.0.0.6 / Android17'
[ "$(am get-current-user)" = 0 ] && [ "$(pm list users | grep -c 'UserInfo{')" = 1 ] || abort '仅支持单一机主用户0'
(cd "$MODPATH" && sha256sum -c checksums.sha256) || abort '套件文件校验失败'
M=$MODPATH
. "$M/shared.sh"
shared_check || abort '统一兼容包存在未知版本或分包安装，保留原状并停止'
shared_install || abort '统一兼容 APK 安装或校验失败，保留数据并停止'
set_perm_recursive "$MODPATH" 0 0 0755 0644
for script in "$MODPATH"/*.sh; do set_perm "$script" 0 0 0755; done
ui_print '统一兼容与推送设置已安装；重启后打开1.4 WebUI的一键配置当前方案。'
ui_print '先启用唯一统一 LSP 插件；一键配置按勾选检查组件、兼容功能并请求作用域，按页面提示重启后继续。'
ui_print '此安装器不执行迁移，不修改兼容偏好或 LSP 作用域。'
ui_print 'Root、Zygisk、LSPosed/API102 和 OverlayFS MetaModule 须另行准备；不重置钱包或接受协议。'
