#!/system/bin/sh
# Only fixed settings routes are accepted; no shell fragments or setting writes.
[ "$#" = 1 ] || exit 2
[ "$(getprop ro.product.device)" = xuanyuan ] && [ "$(getprop ro.build.version.sdk)" = 37 ] && [ "$(getprop ro.build.version.incremental)" = OS4.0.0.6.XOAEUXM ] || { echo '此面板仅适用于 xuanyuan EEA OS4.0.0.6'; exit 1; }
route() {
 case "$1" in
  suggestions) echo 'com.miui.personalassistant/com.miui.personalassistant.service.aireco.setting.ui.RecommendationNewActivity' ;;
  screen) echo 'com.miui.voiceassist/com.xiaomi.voiceassistant.settings.ScreenRecognitionSettingActivity' ;;
  control) echo 'com.miui.voiceassist/com.xiaomi.voiceassistant.settings.AppControlSettingsActivity' ;;
  memory) echo 'com.miui.voiceassist/com.xiaomi.voiceassistant.settings.MemorySettingActivity' ;;
  wakeup) echo 'com.miui.voiceassist/com.xiaomi.voiceassistant.settings.WakeupSettingsActivity' ;;
  translate) echo 'com.xiaomi.aiasst.vision/com.xiaomi.aiasst.vision.ui.setting.ControlWindowSettingActivity' ;;
  write) echo 'com.miui.voiceassist/com.xiaomi.voiceassistant.LaunchHomeRouterActivity' ;;
  aicall) echo 'com.xiaomi.aiasst.service/com.xiaomi.aiasst.service.aicall.settings.main.CallLogAndSettingsActivity' ;;
  callerid) echo 'com.miui.yellowpage/com.miui.yellowpage.activity.SettingActivity' ;;
  *) return 2 ;;
 esac
}
ready() {
 COMPONENT=$(route "$1") || return 2
 RESULT=$(cmd package resolve-activity --brief --user 0 -n "$COMPONENT" 2>/dev/null)
 case "$RESULT" in *"${COMPONENT%/*}/"*) return 0 ;; *) return 1 ;; esac
}
if [ "$1" = status ]; then
 for ID in suggestions screen control memory wakeup translate write aicall callerid; do
  if ready "$ID"; then echo "$ID|ready"; else echo "$ID|missing"; fi
 done
 # This is the user's network lookup switch, not a claim of server success.
 case "$(settings get system cloud_antispam)" in
  1) echo 'callerid_switch|on' ;;
  0) echo 'callerid_switch|off' ;;
  *) echo 'callerid_switch|unknown' ;;
 esac
 exit 0
fi
route "$1" >/dev/null || { echo '未知功能'; exit 2; }
ready "$1" || { echo '未找到功能入口，请检查组件是否已安装并启用'; exit 1; }
if [ "$1" = aicall ]; then
 am start --user 0 -n "$COMPONENT" --ei SELECT_INDEX 1
else
 am start --user 0 -n "$COMPONENT"
fi
