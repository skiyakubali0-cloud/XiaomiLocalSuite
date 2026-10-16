#!/system/bin/sh
M=${0%/*}
S=/data/adb/xuanyuan-os4-suite-state
K=/data/adb/ksud
BB=/data/adb/ksu/bin/busybox
MODULES=/data/adb/modules
ORDER='market assistant xiaoai phone gallery weather disaster wallet clock calendar'
. "$M/catalog.sh"
umask 077

fail() { echo "错误：$*" >&2; exit 1; }
sha() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1; }
path_of() { pm path --user 0 "$1" 2>/dev/null | sed -n 's/^package://p'; }
pkg_sha() { sha "$(path_of "$1")"; }
enabled() { [ -f "$MODULES/$1/module.prop" ] && [ ! -e "$MODULES/$1/disable" ] && [ ! -e "$MODULES/$1/remove" ]; }
present() { pm list packages --user 0 "$1" | grep -qx "package:$1"; }
boot() { cat /proc/sys/kernel/random/boot_id; }
json() { "$BB" awk 'BEGIN{printf "\"";for(i=1;i<32;i++)esc[sprintf("%c",i)]=sprintf("\\u%04x",i)}{if(NR>1)printf "\\n";for(j=1;j<=length($0);j++){c=substr($0,j,1);if(c=="\\")printf "\\\\";else if(c=="\"")printf "\\\"";else if(c in esc)printf "%s",esc[c];else printf "%s",c}}END{printf "\""}'; }
prop() { sed -n "s/^$2=//p" "$1/module.prop" 2>/dev/null | head -1; }
platform() {
 [ "$(id -u)" = 0 ] || fail '需要从 KernelSU WebUI 运行'
 [ "$(getprop ro.product.device)" = xuanyuan ] && [ "$(getprop ro.build.version.sdk)" = 37 ] && [ "$(getprop ro.build.version.incremental)" = OS4.0.0.6.XOAEUXM ] || fail '机型或系统不受支持'
 [ "$(am get-current-user)" = 0 ] || fail '请切回机主用户'
 [ "$(pm list users | grep -c 'UserInfo{')" = 1 ] || fail '首版只支持单用户0，未执行更改'
 [ -x "$K" ] || fail 'KernelSU CLI 不可用'
 [ -x /data/adb/metamodule/meta-overlayfs ] && enabled meta-overlayfs || fail '先安装并重启启用 OverlayFS 元模块'
 [ "$(getprop sys.boot_completed)" = 1 ] || fail '等待系统启动完成'
}
integrity() { (cd "$M" && sha256sum -c control.sha256 >/dev/null) || fail '管理程序校验失败，请重新安装套件'; }
validate_ids() {
 [ -n "$1" ] || fail '没有选择组件'
 case "$1" in *[!a-z,]*|,*|*,|*,,*) fail '组件参数不合法';; esac
 for ID in $(echo "$1" | tr ',' ' '); do lookup "$ID" || fail "未知组件 $ID"; done
}
selected() { case ",$IDS," in *",$1,"*) return 0;; *) return 1;; esac; }
payload_ok() { lookup "$1" || fail '未知组件'; [ "$(sha "$M/payload/$FILE")" = "$SHA" ] || fail "$TITLE 安装文件校验失败"; }
reconcile() {
 [ -d "$S/lock" ] || return 0
 # mkdir is atomic, the following metadata writes are not. Do not steal a new lock.
 if [ ! -s "$S/lock/boot" ]; then
  AGE=$(( $(date +%s) - $(stat -c %Y "$S/lock") ))
  [ "$AGE" -gt 60 ] || return 0
 fi
 STALE=no
 [ "$(cat "$S/lock/boot" 2>/dev/null)" = "$(boot)" ] || STALE=yes
 PID=$(cat "$S/lock/pid" 2>/dev/null)
 if [ -n "$PID" ]; then
  kill -0 "$PID" 2>/dev/null || STALE=yes
 elif [ -f "$S/lock/created" ]; then
  [ "$(( $(date +%s) - $(cat "$S/lock/created") ))" -le 60 ] || STALE=yes
 fi
 if [ "$STALE" = yes ]; then
  if [ -f "$S/latest" ]; then
   J=$(cat "$S/latest")
   case "$J" in "$S"/jobs/*) echo interrupted > "$J/state"; echo '上次任务被重启或进程退出中断，请查看日志后重新检查。' > "$J/message";; esac
  fi
  rm -rf "$S/lock"
 fi
}
job() {
 reconcile
 J=$(cat "$S/latest" 2>/dev/null)
 case "$J" in "$S"/jobs/*) ;; *) printf '{"state":"idle","message":"尚无任务","log":""}\n'; return;; esac
 printf '{"state":'; cat "$J/state" 2>/dev/null | json
 printf ',"message":'; cat "$J/message" 2>/dev/null | json
 printf ',"log":'; tail -100 "$J/log" 2>/dev/null | json; printf '}\n'
}
status() {
 supported=false; ready=false
 if [ "$(getprop ro.product.device)" = xuanyuan ] && [ "$(getprop ro.build.version.incremental)" = OS4.0.0.6.XOAEUXM ] && [ "$(getprop ro.build.version.sdk)" = 37 ]; then supported=true; fi
 if (platform) >/dev/null 2>&1; then ready=true; fi
 printf '{"device":'; getprop ro.product.device | json
 printf ',"rom":'; getprop ro.build.version.incremental | json
 printf ',"api":'; getprop ro.build.version.sdk | json
 printf ',"supported":%s,"ready":%s,"components":[' "$supported" "$ready"
 sep=''
 for ID in $ORDER; do
  lookup "$ID"; ST=absent; VER=''
  if [ "$KIND" = module ]; then
   if [ -f "$MODULES/$MID/module.prop" ]; then
    ST=enabled; VER=$(prop "$MODULES/$MID" version)
    enabled "$MID" || ST=disabled
    module_version_ok || ST=unknown
   fi
   [ ! -e "$MODULES/$MID/update" ] && [ ! -e "$MODULES/$MID/remove" ] && [ ! -d "/data/adb/modules_update/$MID" ] || ST=pending
  elif present "$PKG"; then
   ST=installed
   [ "$(pkg_sha "$PKG")" = "$SHA" ] || ST=unknown
   pm list packages -d --user 0 | grep -qx "package:$PKG" && ST=disabled
  fi
  printf '%s{"id":"%s","state":"%s","version":' "$sep" "$ID" "$ST"; printf '%s' "$VER" | json; printf '}'
  sep=,
 done
 printf '],"job":'; job; printf '}\n'
}
preflight() {
 OP=$1; IDS=$2
 platform; integrity; validate_ids "$IDS"
 case "$OP" in install|restore) ;; *) fail '未知操作';; esac
 [ "$OP" != restore ] || { case "$IDS" in *,*) fail '恢复一次只处理一个组件';; esac; }
 NEED=262144
 for CHOSEN in $(echo "$IDS" | tr ',' ' '); do lookup "$CHOSEN"; NEED=$(( NEED + $(stat -c %s "$M/payload/$FILE") / 256 )); done
 FREE=$(df -Pk /data | tail -1 | "$BB" awk '{print $4}')
 [ "$FREE" -gt "$NEED" ] || fail '存储空间不足，请先腾出安装及恢复所需空间'
 for ID in $ORDER; do
  selected "$ID" || continue
  payload_ok "$ID"
  [ ! -e "$MODULES/$MID/remove" ] || fail "$TITLE 已安排卸载，先重启处理"
  [ "$KIND" != module ] || [ ! -d "/data/adb/modules_update/$MID" ] || fail "$TITLE 有待生效更新，请先重启"
  if [ -f "$MODULES/$MID/module.prop" ]; then
   module_version_ok || fail "$TITLE 当前版本与套件不同，禁止覆盖或用旧脚本恢复"
  fi
  if [ "$OP" = install ]; then
   case "$ID" in phone|xiaoai|clock|disaster)
    enabled zygisk_lsposed && enabled zygisksu || fail "$TITLE 需要先启用 LSPosed 和 Zygisk 并重启";; esac
   case "$ID" in
    phone) present com.xiaomi.market && enabled xuanyuan-os4-market || fail '首次安装请先安装商店并重启，再安装电话组件';;
    xiaoai) enabled xuanyuan-os4-assistant || selected assistant || fail '超级小爱需要勾选智能助理';;
    wallet) [ "$(sha /product/app/MITSMClientGlobal/MITSMClientGlobal.apk)" = 567e8f05e4b2cbc7c203ce5f10672756ea8af0542c3fc5aafaa3e677ebcaa671 ] || fail '钱包首次凭据迁移须单独处理，本套件不生成重置标记';;
    clock) [ "$(pkg_sha com.android.deskclock)" = 41defcfd640a3ba5d359c20004d9dced5f6c0810204c41c94530af2a2bc1e9f6 ] || fail '时钟版本不匹配';;
    calendar) calendar_check;;
    gallery) gallery_check;;
   esac
   echo "安装：$TITLE；沿用组件原始校验和安装逻辑。"
  else
   owned_check "$ID"
   case "$ID" in
    market) ! enabled xuanyuan-os4-phone || fail '请先恢复电话组件，再恢复其商店依赖'; present com.xiaomi.mipicks || fail '原 GetApps 不存在，未执行恢复';;
    wallet) fail '钱包恢复涉及卡片/eSE凭据，须单独评估；没有执行修改';;
    clock) fail '先把法定重复规则改回普通规则，再从 LSPosed 停用时钟补丁';;
    assistant) ! enabled xuanyuan-os4-xiaoai || fail '超级小爱建议依赖智能助理，请先停用小爱组件';;
    xiaoai)
     case "$(settings get secure assistant) $(settings get secure voice_interaction_service)" in *com.miui.voiceassist*) fail '请先在系统默认应用中将数字助理切换到 Gemini 或其他应用';; esac;;
    phone) phone_restore_check;;
    weather) weather_check;;
    calendar) calendar_check;;
    gallery) gallery_check;;
   esac
   [ "$KIND" != module ] || [ -f "$MODULES/$MID/module.prop" ] || fail "$TITLE 未安装"
   echo "单独恢复/停用：$TITLE；保留数据，挂载更改重启后生效。"
  fi
 done
 echo '任务不会自动接受协议、启用录音/报警或重置钱包。LSPosed作用域需在管理器中核对。'
}


# These official-signed updates were checked against the original signing certificate.
# Restore only disables them; it never uninstalls or downgrades these APKs.
retained_update() {
 case "$1|$2|$3" in
 market\|com.xiaomi.market\|14dd58663e83d83dc6ab0f95af88be3d2b96ca28c651e3e8f7b0144807e4c05a|xiaoai\|com.miui.voiceassist\|caafb6930e7a9b86c46ea9fc3ab00fbd76c826026fa0f23260f39737b42c8ffa) return 0;;
 *) return 1;;
 esac
}

owned_check() {
 while IFS='|' read -r OWNER PACKAGE EXPECTED; do
  [ "$OWNER" = "$1" ] || continue
  if present "$PACKAGE"; then
   ACTUAL=$(pkg_sha "$PACKAGE")
   [ "$ACTUAL" = "$EXPECTED" ] || retained_update "$OWNER" "$PACKAGE" "$ACTUAL" || fail "$PACKAGE 存在其他版本，停止自动停用"
  fi
 done < "$M/owned-packages.txt"
}


module_version_ok() {
 LIVE_CODE=$(prop "$MODULES/$MID" versionCode)
 [ "$LIVE_CODE" = "$CODE" ] && return 0
 # Reviewed in-place upgrade; 1.1 keeps data/app updates and the same overlay payloads.
 [ "$MID" = xuanyuan-os4-gallery ] && [ "$LIVE_CODE" = 2026101302 ] && [ "$CODE" = 2026101401 ]
}
gallery_check() {
 for P in com.miui.gallery com.hyper.gallery.plugin com.miui.mediaeditor com.miui.extraphoto; do
  H=$(pkg_sha "$P")
  case "$P:$H" in
   com.miui.gallery:c25c993cc1462a955b145035ee071d98781ba51370bad232a78eb567eb84cfbc|com.miui.gallery:be6bb05752cf667430c9359cd46fa8f4ed3552ecbe2e90a7b6279eaeb471f4a2|com.miui.gallery:6a9c9677a6a6ef398c3d60dad58c71942adab010b8e4e7727b2c028063c3fd9d) ;;
   com.hyper.gallery.plugin:d0a6af98b4910113fb4ecf62fff349881ec1adde8291682fe500bde59eadf8d1|com.hyper.gallery.plugin:f763216706094ca04cf2c4e67600595bbfa55f0533b8468a7c36ca2463bf9497) ;;
   com.miui.mediaeditor:52343b5d46f227100fc0b75ee6eed633a431db51f95eb3c2f1ba44ad40aacefc|com.miui.mediaeditor:365954e0e94263b7372fa5e6f4d244690b5edd9607b5642a1488a622732f7756|com.miui.mediaeditor:e7c37c8ee2e10e8e45b60ad3ff293ad8a0b1c702f9e79aaa8df97ecfbcf4f699) ;;
   com.miui.extraphoto:ca7794bb50c7ab612aab9494d0fc8fe887bfbd5a28ba3ffd8fecaba7a218c7c4|com.miui.extraphoto:b6149345f1aa4f3b84d84152b186f5c60bc6bc4c95957ac3cc232fb047722756) ;;
   *) fail "$P 有未经验证的相册更新，保留数据并停止操作";;
  esac
 done
 echo '相册恢复只撤销模块挂载；应用商店更新和照片数据库均保留，不强制降级。'
}

calendar_check() {
 for pair in 'com.android.calendar ed8f4356bb7c44038abbe5f215f215277c114e75de4bd21ac0a65f77d75f75f0' 'com.xiaomi.calendar e2f2e6f2cc5d5ab32480447c23b91c90b2c5db863a38907c6dff61fec80566e7'; do
  set -- $pair
  if present "$1"; then [ "$(pkg_sha "$1")" = "$2" ] || fail '日历存在未知更新，未执行替换'; fi
 done
 [ "$(sha "$M/payload/calendar-global.apk")" = e2f2e6f2cc5d5ab32480447c23b91c90b2c5db863a38907c6dff61fec80566e7 ] || fail '国际日历恢复文件校验失败'
}
weather_check() {
 case "$(pkg_sha com.miui.weather2)" in 2a8faed30ce5ffe4ae0229dce0d520d882dff990f6ef158e5fbb555153b7e887|017d613137c0512a937dc6b8565da856099e988feab47b9eabc5c3d0a13f06e6|9439e87555133762d362bfba651e7ab6e2f01e78b280fdd7ec745cbb6403b025) ;; *) fail '天气存在未知更新，未执行恢复';; esac
 case "$(pkg_sha com.miui.core)" in 5abe56881dafbe3540e11c4ff4a450ae7bcd19d93753a251326f09314a2bb9e9|585703b25f0bce27f06f76ed568af9a9bbf58bcf7810600ad23eb4ab57be6902) ;; *) fail '天气核心存在未知更新，未执行恢复';; esac
 [ -f /data/adb/xuanyuan-weather-state/restore.sh ] || fail '缺少天气恢复文件'
}
phone_restore_check() {
 for R in DIALER SMS; do
  case "$R" in DIALER) F=before-dialer;; SMS) F=before-sms;; esac
  OLD=$(cat "/data/adb/xuanyuan-os4-phone-state/$F" 2>/dev/null)
  case "$OLD" in com.google.android.dialer|com.google.android.apps.messaging) present "$OLD" || fail '原默认应用不可用';; *) fail '原默认应用记录未知，请先手动切换并核对';; esac
 done
 case "$(pkg_sha com.miui.yellowpage)" in e07e59b9d9a99b0cce4bf06b9734002016b1c3bebe701c6ee368cdc8161cb733|0c5c655fe93ffc0eade6a77dc56c05754d4a3afab8a6c122acd3a2f8a160c0ba) ;; *) fail '黄页有未知更新';; esac
 case "$(pkg_sha com.miui.audiomonitor)" in 83133a62f37cefe873075064d39c5e176e768af251d678438a242116be8178b1|f84954e6ef361a8204c565bfe365e66344e2984036febe784c1485e113d1ba71) ;; *) fail '录音监控有未知更新';; esac
}

install_apk() { cat "$1" | pm install -r --user 0 -i com.xiaomi.market -S "$(stat -c %s "$1")"; }
disable_pkg() { if present "$1"; then pm disable-user --user 0 "$1"; fi; }
enable_pkg() { if present "$1"; then pm enable --user 0 "$1"; fi; }
remove_hook() { if present "$1"; then pm uninstall -k --user 0 "$1"; fi; }
extract() {
 lookup "$1"
 E="$J/extracted-$1"; mkdir -p "$E"
 "$BB" unzip -oq "$M/payload/$FILE" -d "$E"
}
calendar_swap() {
 if [ "$1" = cn ]; then FROM=com.xiaomi.calendar; TO=com.android.calendar; APK="$M/payload/calendar.apk"; BACK="$M/payload/calendar-global.apk"
 else FROM=com.android.calendar; TO=com.xiaomi.calendar; APK="$M/payload/calendar-global.apk"; BACK="$M/payload/calendar.apk"; fi
 HAD=no
 if present "$FROM"; then HAD=yes; pm uninstall -k "$FROM" || fail '日历应用移除失败'; fi
 if ! install_apk "$APK"; then
  [ "$HAD" != yes ] || install_apk "$BACK" || echo '原日历恢复失败，请保留日志处理'
  fail '日历安装失败，已尝试恢复原应用；日历内容服务未改动'
 fi
 for P in READ_CALENDAR WRITE_CALENDAR POST_NOTIFICATIONS; do pm grant --user 0 "$TO" "android.permission.$P"; done
}
install_one() {
 ID=$1; lookup "$ID"
 if [ "$KIND" = module ]; then
  "$K" module install "$M/payload/$FILE" || fail "$TITLE 安装失败"
  case "$ID" in
   market) pm unhide --user 0 com.xiaomi.market; enable_pkg com.xiaomi.market;;
   assistant) enable_pkg com.miui.personalassistant;;
   phone) for P in com.android.contacts com.android.incallui com.android.mms local.xuanyuan.smscompat; do enable_pkg "$P"; done;;
   disaster) enable_pkg local.xuanyuan.disastercompat;;
   xiaoai) for P in com.miui.voiceassist com.miui.contentcatcher com.xiaomi.aiasst.service com.miui.voicetrigger com.xiaomi.aireco com.xiaomi.macro com.miui.contentextension com.xiaomi.mibrain.speech com.miui.voiceassistProxy local.xuanyuan.aiprivacy local.xuanyuan.suggestioncompat; do enable_pkg "$P"; done;;
  esac
  if [ -e "$S/restored/$ID" ]; then
   case "$ID" in
    market) extract market; sh "$E/control.sh" disable;;
    assistant) extract assistant; sh "$E/control.sh" china;;
   esac
  fi
 else
  case "$ID" in clock) install_apk "$M/payload/$FILE"; enable_pkg "$PKG";; calendar) calendar_swap cn;; esac
 fi
 rm -f "$S/restored/$ID"
 echo "完成安装阶段：$TITLE。重启和功能验证另行显示。"
}
restore_one() {
 ID=$1; lookup "$ID"
 case "$ID" in
 market)
  extract market
  sh "$E/control.sh" enable
  "$K" module disable "$MID"
  pm hide --user 0 com.xiaomi.market
  dumpsys package com.xiaomi.market | grep "^    User 0:.*installed=" | sed -n '1p' | grep -q "hidden=true" || fail "商店隐藏状态未通过验证";;
 assistant)
  extract assistant
  sh "$E/control.sh" google
  "$K" module disable "$MID"
  disable_pkg com.miui.personalassistant;;
 xiaoai)
  "$K" module disable "$MID"
  for P in com.miui.voiceassist com.miui.contentcatcher com.xiaomi.aiasst.service com.miui.voicetrigger com.xiaomi.aireco com.xiaomi.macro com.miui.contentextension com.xiaomi.mibrain.speech com.miui.voiceassistProxy; do disable_pkg "$P"; done
  remove_hook local.xuanyuan.aiprivacy
  remove_hook local.xuanyuan.suggestioncompat;;
 phone)
  extract phone
  "$K" module disable "$MID"
  sh "$E/uninstall.sh"
  remove_hook local.xuanyuan.smscompat
  [ "$(pkg_sha com.miui.yellowpage)" = 0c5c655fe93ffc0eade6a77dc56c05754d4a3afab8a6c122acd3a2f8a160c0ba ] || fail '黄页恢复未通过验证'
  [ "$(pkg_sha com.miui.audiomonitor)" = f84954e6ef361a8204c565bfe365e66344e2984036febe784c1485e113d1ba71 ] || fail '录音监控恢复未通过验证'
  for R in DIALER SMS; do
   case "$R" in DIALER) F=before-dialer;; SMS) F=before-sms;; esac
   [ "$(cmd role get-role-holders --user 0 android.app.role.$R)" = "$(cat /data/adb/xuanyuan-os4-phone-state/$F)" ] || fail '默认应用恢复未通过验证'
  done
  for P in com.android.contacts com.android.incallui com.android.mms; do disable_pkg "$P"; done;;
 weather)
  extract weather
  "$K" module disable "$MID"
  sh "$E/restore.sh"
  [ "$(pkg_sha com.miui.weather2)" = 9439e87555133762d362bfba651e7ab6e2f01e78b280fdd7ec745cbb6403b025 ] || fail '国际天气恢复校验失败'
  [ "$(pkg_sha com.miui.core)" = 585703b25f0bce27f06f76ed568af9a9bbf58bcf7810600ad23eb4ab57be6902 ] || fail '国际核心恢复校验失败';;
 gallery) extract gallery; "$K" module disable "$MID"; sh "$E/profiles.sh" restore;;
 disaster) "$K" module disable "$MID"; remove_hook local.xuanyuan.disastercompat;;
 calendar) calendar_swap global;;
 *) fail '此组件需要单独处理';;
 esac
 mkdir -p "$S/restored"
 boot > "$S/restored/$ID"
 echo "已完成 $TITLE 的恢复准备；涉及挂载或补丁须重启确认，保留原数据。"
}

finish() {
 RC=$1
 if [ "$RC" != 0 ]; then echo failed > "$J/state"; echo '任务失败，已停止后续步骤；部分步骤可能已完成，请查看日志。' > "$J/message"; fi
 rm -rf "$S/lock"
}
worker() {
 J=$1; OP=$2; IDS=$3
 case "$J" in "$S"/jobs/*) ;; *) fail '任务路径无效';; esac
 [ "$(cat "$S/latest")" = "$J" ] && [ -d "$S/lock" ] || fail '任务锁无效'
 trap 'finish $?' EXIT
 trap 'exit 130' INT TERM
 set -e
 echo $$ > "$S/lock/pid"
 echo running > "$J/state"; echo '正在检查和执行，请勿重启。' > "$J/message"
 preflight "$OP" "$IDS"
 "$K" module list > "$J/modules-before.json"
 for R in DIALER SMS ASSISTANT WALLET; do
  HOLDER=$(cmd role get-role-holders --user 0 "android.app.role.$R")
  printf '%s\n' "$HOLDER" > "$J/role-$R.before"
 done
 for ID in $ORDER; do
  selected "$ID" || continue
  echo "--- $OP $ID ---"
  echo "$ID" >> "$J/started"
  if [ "$OP" = install ]; then install_one "$ID"; else restore_one "$ID"; fi
  echo "$ID" >> "$J/completed"
 done
 echo succeeded > "$J/state"
 echo '任务步骤完成。请按组件说明重启、核对 LSPosed 与实际功能；这不代表全部功能已经验证。' > "$J/message"
}
start() {
 OP=$1; IDS=$2
 platform; integrity; validate_ids "$IDS"; reconcile
 mkdir -p "$S/jobs"
 mkdir "$S/lock" 2>/dev/null || fail '已有任务在运行'
 boot > "$S/lock/boot"
 date +%s > "$S/lock/created"
 J="$S/jobs/$(date +%s)-$$"; mkdir "$J"
 echo "$J" > "$S/latest"; echo queued > "$J/state"; echo '任务已排队' > "$J/message"
 "$BB" nohup sh "$M/runner.sh" "$J" "$OP" "$IDS" </dev/null >/dev/null 2>&1 &
 echo '任务已启动，请查看进度。'
}
open_component() {
 case "$1" in
 market) am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p com.xiaomi.market;;
 assistant) am start -n com.miui.home/com.miui.home.settings.MiuiHomeSettingActivity;;
 xiaoai) am start -a android.settings.VOICE_INPUT_SETTINGS;;
 phone) am start -a android.settings.MANAGE_DEFAULT_APPS_SETTINGS;;
 gallery) am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p com.miui.gallery;;
 weather) am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p com.miui.weather2;;
 disaster) am start -n local.xuanyuan.disastercompat/.EntryActivity;;
 wallet) am start -a android.settings.NFC_SETTINGS;;
 clock) am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p com.android.deskclock;;
 calendar) am start -n com.android.calendar/.homepage.AllInOneActivity;;
 *) fail '未知入口';;
 esac
}
case "$1" in
 status) status;;
 job) job;;
 reconcile) reconcile;;
 plan) [ "$#" = 3 ] || fail '参数数量错误'; preflight "$2" "$3";;
 start) [ "$#" = 3 ] || fail '参数数量错误'; start "$2" "$3";;
 worker) [ "$#" = 4 ] || fail '参数数量错误'; worker "$2" "$3" "$4";;
 open) [ "$#" = 2 ] || fail '参数数量错误'; platform; validate_ids "$2"; open_component "$2";;
 lsp) platform; "$K" module action zygisk_lsposed;;
 reboot) platform; reconcile; [ ! -d "$S/lock" ] || fail '任务进行中不能重启'; reboot;;
 *) fail '未知命令';;
esac
