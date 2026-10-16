#!/system/bin/sh
STATE=/data/adb/xuanyuan-os4-market-state
mkdir -p "$STATE"
case "$1" in
  enable) touch "$STATE/keep-getapps"; pm enable --user 0 com.xiaomi.mipicks ;;
  disable) rm -f "$STATE/keep-getapps"; pm disable-user --user 0 com.xiaomi.mipicks ;;
  status) pm list packages -d --user 0 | grep -q '^package:com.xiaomi.mipicks$' && echo 旧商店已关闭 || echo 旧商店已开启 ;;
  *) exit 2 ;;
esac
