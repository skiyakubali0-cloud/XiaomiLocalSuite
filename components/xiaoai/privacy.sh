#!/system/bin/sh
MODDIR=${0%/*}
[ "$#" = 1 ] || exit 2
[ -f /product/etc/xuanyuan-ai-privacy.enabled ] && [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || {
 echo '请启用小爱模块并重启后再使用 AI 权限管理' >&2; exit 1;
}
case "$1" in *[!a-zA-Z0-9._:]*|'') echo '无效操作' >&2; exit 2 ;; esac
CLASSPATH=$(pm path --user 0 local.xuanyuan.mipushcompat | sed -n 's/^package://p')
[ -f "$CLASSPATH" ] || { echo '统一兼容包缺失或为分包安装' >&2; exit 1; }
case "$(sha256sum "$CLASSPATH" | cut -d' ' -f1)" in
 660cb1245fa9dac261d64570fba557ba44c166382960799b27bc130b59e14d25|9846373803f3e440372f014cb7bfa499636d99968bed278911ee75116c4d537b|f51432bb665ba68c1e5232170baea2d8e9d320e83804000e54b13ebdba4c5858|02b4d7bc35ccfa6ec9d3e7ce82171b1a96bf81ba1abb3f1dcff70170c960679f) ;;
 *) exit 1;;
esac
export CLASSPATH
exec /system/bin/app_process /system/bin local.xuanyuan.aiprivacy.Manager "$1"
