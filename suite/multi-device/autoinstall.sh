#!/system/bin/sh
# Synchronous install only. IDs are fixed by the offline, pinned recipe.
[ "$#" = 0 ] || { echo 'Automatic install takes no arguments' >&2; exit 1; }
AUTO_IDS='@SELECTED_IDS@'
M=${0%/*}
cd "$M" || exit 1
M=$PWD
set -- library
. "$M/control.sh"
set -e
[ "${KSU:-}" = true ] || fail 'KernelSU required'
platform
integrity
validate_ids "$AUTO_IDS"
[ "$(printf '%s' "$ORDER" | tr ' ' ',')" = "$AUTO_IDS" ] || fail 'Automatic selection differs from catalog order'
for AUTO_ID in $(printf '%s' "$AUTO_IDS" | tr ',' ' '); do
 case "$AUTO_ID" in market|assistant|xiaoai) ;; *) fail 'Unreviewed automatic component';; esac
done
case ",$AUTO_IDS," in *,xiaoai,*) case ",$AUTO_IDS," in *,assistant,*) ;; *) fail 'XiaoAI requires Assistant';; esac;; esac
[ ! -e "$M/install-selected.ok" ] || fail 'Unexpected completion marker'
[ ! -e "$S/lock" ] || fail '已有套件任务锁，请先处理并重新生成安装计划'
AUTO_JOB=$(cat "$S/latest" 2>/dev/null || true)
if [ -n "$AUTO_JOB" ]; then
 case "$AUTO_JOB" in "$S"/jobs/*) ;; *) fail '任务记录路径无效';; esac
 case "$(cat "$AUTO_JOB/state" 2>/dev/null)" in queued|running) fail '已有套件任务未完成';; esac
fi
[ "$(prop "$MODULES/meta-overlayfs" versionCode)" = 13100 ] || fail '需要已验证的OverlayFS 1.3.1'
[ ! -e "$MODULES/meta-overlayfs/update" ] && [ ! -e "${MODULES}_update/meta-overlayfs" ] || fail '元模块有待重启更新'
[ ! -e /data/adb/metamodule/modules.img ] || mountpoint -q /data/adb/metamodule/mnt || fail 'OverlayFS镜像未挂载，请先重启'
for AUTO_ID in $(printf '%s' "$AUTO_IDS" | tr ',' ' '); do
 lookup "$AUTO_ID" || fail '所选组件目录缺失'
 [ ! -e "$MODULES/$MID/update" ] && [ ! -e "$MODULES/$MID/remove" ] && [ ! -e "${MODULES}_update/$MID" ] || fail '所选组件有待重启变更'
done
case ",$AUTO_IDS," in *,xiaoai,*)
 for AUTO_DEP in zygisk_lsposed zygisksu; do
  [ ! -e "$MODULES/$AUTO_DEP/update" ] && [ ! -e "$MODULES/$AUTO_DEP/remove" ] && [ ! -e "${MODULES}_update/$AUTO_DEP" ] || fail '小爱框架依赖有待重启变更'
 done
 ;; esac
# Run all additional child runtime guards before shared APK or child staging.
case ",$AUTO_IDS," in *,assistant,*)
 case "$(sha /system_ext/lib64/libhyper_os_core_system_private.dylib.so)" in
  a7de453780f33d2dec0cfca8832d218ee798f3208df06af36744f416313afa1f|5d7b4fd34dd7878d1d4d988afcc456672ca3eb7df9345ce9767783810ac2f182|71fa522160812cb9bf5f5f4f0f0227ed9acb227c9102521a65c0c6e3d172212f) ;;
  *) fail 'Rust runtime differs from tested build';;
 esac
 [ "$(sha /apex/com.android.runtime/lib64/bionic/libc.so)" = f6c25ea4d8b9a4dc76d6964f78edc9831cd676837a8f91d93a1cb4e87808e32e ] || fail 'Bionic runtime differs from tested build'
 AUTO_HOME=$(dumpsys package com.miui.home | sed -n 's/^    versionCode=\([0-9]*\).*/\1/p' | head -n 1)
 [ "$AUTO_HOME" = 801027654 ] || fail 'This adapter requires launcher 801027654'
 AUTO_RETIRED=/data/adb/metamodule/mnt/xuanyuan-os4-assistant/product/priv-app/MiuiHome/MiuiHome.apk
 if [ -f "$AUTO_RETIRED" ]; then
  [ "$(sha "$AUTO_RETIRED")" = b5e9aaa1ef1f052e3b9e31c685ff201436700728d5fc52d9d56d0c9326fdfa9c ] || fail 'Unexpected retired launcher payload'
 fi
 ;; esac
case ",$AUTO_IDS," in *,xiaoai,*)
 pm list libraries | grep -qx 'library:vendor.xiaomi.hardware.misys.V3_0' || fail 'VoiceTrigger requires misys V3_0'
 [ "$(sha /system_ext/framework/miui-services.jar)" = cef17afe99cfa6396922e2fe1dce6642ec86ddcf141589b8ef4d007d6920ecdb ] || fail 'miui-services版本不匹配'
 [ "$(pkg_sha com.xiaomi.aicr)" = f081299f3e638d188a2d3d2ace6aeef4ab9d0226f775fc7474495812f67b8520 ] || fail 'AI引擎需要原版4.12.19'
 ;; esac
preflight install "$AUTO_IDS"
# No stale-lock takeover and no asynchronous boot/service installation.
mkdir -p "$S/jobs"
mkdir "$S/lock" 2>/dev/null || fail '已有任务在运行'
AUTO_OWN_LOCK=true
trap 'if [ "$AUTO_OWN_LOCK" = true ]; then rmdir "$S/lock" 2>/dev/null || true; fi' EXIT
boot > "$S/lock/boot"
date +%s > "$S/lock/created"
J="$S/jobs/flash-$(date +%s)-$$"
mkdir "$J"
echo "$J" > "$S/latest"
echo queued > "$J/state"
echo '正在刷入图形界面所选组件' > "$J/message"
# A separate synchronous worker retains its existing fail-stop EXIT trap.
# Its pipe supplies Binder-safe stdout and a log outside disposable parent staging.
AUTO_OWN_LOCK=false
sh "$M/control.sh" worker "$J" install "$AUTO_IDS" 2>&1 | "$BB" tee "$J/log"
# tee returning zero is not proof that its worker succeeded.
[ "$(cat "$J/state")" = succeeded ] || fail "组件安装未完成；部分步骤可能已完成，日志：$J/log"
[ ! -e "$S/lock" ] || fail "任务锁未释放，安装结果未确认；日志：$J/log"
printf '%s\n' "$AUTO_IDS" > "$M/install-selected.ok"
echo '所选组件已同步安装，挂载在手动重启后生效；不会自动重启或配置LSPosed。'
