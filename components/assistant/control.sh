#!/system/bin/sh
MODDIR=${0%/*}
MARKER=/data/user_de/0/com.miui.home/files/.os4-assistant-route
set_route() {
  if [ -e "$MODDIR/use_china" ]; then
    [ -d "${MARKER%/*}" ] || return 1
    touch "$MARKER" || return 1
    chown "$(stat -c %u:%g "${MARKER%/*}")" "$MARKER" || return 1
    chmod 600 "$MARKER"
    restorecon "$MARKER" >/dev/null 2>&1
    /data/adb/ksu/bin/resetprop -n ro.appcompat_override.ro.product.mod_device xuanyuan
    /data/adb/ksu/bin/resetprop -n ro.appcompat_override.ro.miui.build.region cn
    /data/adb/ksu/bin/resetprop -n ro.appcompat_override.ro.miui.region CN
    /data/adb/ksu/bin/resetprop -n ro.appcompat_override.ro.com.miui.rsa.search tier2
  else
    rm -f "$MARKER"

  fi
}
case "$1" in
  china) touch "$MODDIR/use_china" ;;
  google) rm -f "$MODDIR/use_china" ;;
  boot) set_route; exit $? ;;
  status)
    if [ -e "$MARKER" ]; then echo '配置：国行智能助理'; else echo '配置：系统原始负一屏'; fi
    echo '请在桌面右滑确认页面。'
    exit 0 ;;
  *) exit 2 ;;
esac
set_route || { echo '配置失败，未重启桌面'; exit 1; }
settings put system open_personal_assistant 1
if [ "$1" = china ]; then
  settings put system switch_personal_assistant personal_assistant_app_vault
else
  settings put system switch_personal_assistant personal_assistant_google
fi
am force-stop com.miui.home
am start -a android.intent.action.MAIN -c android.intent.category.HOME
