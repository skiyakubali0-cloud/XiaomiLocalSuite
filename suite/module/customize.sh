#!/system/bin/sh
[ "$KSU" = true ] || abort '需要 KernelSU'
[ "$(getprop ro.product.device)" = xuanyuan ] && [ "$(getprop ro.build.version.sdk)" = 37 ] && [ "$(getprop ro.build.version.incremental)" = OS4.0.0.6.XOAEUXM ] || abort '仅支持小米15 Ultra EEA OS4.0.0.6 / Android17'
[ "$(am get-current-user)" = 0 ] && [ "$(pm list users | grep -c 'UserInfo{')" = 1 ] || abort '仅支持单一机主用户0'
(cd "$MODPATH" && sha256sum -c checksums.sha256) || abort '套件文件校验失败'
M=$MODPATH
. "$M/shared.sh"
shared_check || abort '统一兼容包存在未知版本或分包安装，保留原状并停止'

# Updating the shared APK must not strand an already enabled XiaoAI CLI.
X=/data/adb/modules/xuanyuan-os4-xiaoai
PAIR_XIAOAI=false
[ ! -d /data/adb/xuanyuan-os4-suite-state/lock ] && [ ! -d /data/adb/xuanyuan-unified-state/lock ] || abort '已有套件或迁移任务，请先完成'
if [ -f "$X/module.prop" ] && [ ! -e "$X/disable" ]; then
 [ ! -e "$X/remove" ] && [ ! -e "$X/update" ] && [ ! -d /data/adb/modules_update/xuanyuan-os4-xiaoai ] || abort '小爱有待处理更改，请先重启'
 [ "$(sed -n 's/^id=//p' "$X/module.prop")" = xuanyuan-os4-xiaoai ] || abort '小爱身份不匹配'
 XC=$(sed -n 's/^versionCode=//p' "$X/module.prop")
 XH=$(sha256sum "$X/privacy.sh" | cut -d' ' -f1)
 case "$XC:$XH" in
  2026101602:428c72628cfcf14f9d17b229690c3cb4b93ef48c089dd58a6a505b87ed95b7f2) PAIR_XIAOAI=true;;
  2026101603:7f508bd4fe60bb2cc1585295ea03a717846b5918cdafcbeb91333785e67e2dde) ;;
  *) abort '请先使用已验证1.6.1升级小爱，再安装1.7；原插件保留';;
 esac
fi
for XD in /data/adb/modules_update/* /data/adb/modules/*/update /data/adb/modules/*/remove; do
 [ -e "$XD" ] || continue
 [ "$XD" = "$MODPATH" ] || abort '其他模块有待处理更改，请先重启'
done
if [ "$PAIR_XIAOAI" = true ]; then
 ui_print '同步已启用小爱的权限CLI校验；不新增其他未选组件。'
 /data/adb/ksud module install "$MODPATH/payload/xiaoai.zip" || abort '小爱配套更新失败，未更新统一APK，请保留日志'
fi

shared_install || abort '统一兼容 APK 安装或校验失败，保留数据并停止'
set_perm_recursive "$MODPATH" 0 0 0755 0644
for script in "$MODPATH"/*.sh; do set_perm "$script" 0 0 0755; done
ui_print '统一兼容与推送设置已安装；重启后打开新版统一插件的组件配置，按需勾选并应用。'
ui_print '先启用唯一统一 LSP 插件；一键配置按勾选检查组件、兼容功能并请求作用域，按页面提示重启后继续。'
ui_print '此安装器不执行迁移，不修改兼容偏好或 LSP 作用域。'
ui_print 'Root、Zygisk、LSPosed/API102 和 OverlayFS MetaModule 须另行准备；不重置钱包或接受协议。'
