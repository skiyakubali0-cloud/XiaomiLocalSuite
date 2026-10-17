#!/system/bin/sh
# One explicit flash plan. No preference writes, reboot, or wallet reset consent.
[ "$#" = 1 ] || exit 1
case "$1" in flash|resume) AUTO_ACTION=$1;; *) exit 1;; esac
AUTO_IDS='@SELECTED_IDS@'
M=${0%/*}
cd "$M" || exit 1
M=$PWD
AUTO_PENDING="$M/install-selected.pending"
AUTO_RESULT="$M/install-selected.result"
AUTO_OK="$M/install-selected.ok"
[ "$AUTO_ACTION" != resume ] || [ -f "$AUTO_PENDING" ] || exit 0
set -- library
. "$M/control.sh"
set -e
AUTO_JOB='' AUTO_WALLET=not-selected AUTO_BATCH='' AUTO_DEFERRED='' AUTO_OWN_LOCK=false
AUTO_PAIR=false AUTO_PAIR_ROOT=''
auto_result() {
 printf 'state=%s\nselected=%s\nwallet=%s\njob=%s\n' "$1" "$AUTO_IDS" "$AUTO_WALLET" "$AUTO_JOB" > "$AUTO_RESULT.new"
 chmod 600 "$AUTO_RESULT.new"
 mv "$AUTO_RESULT.new" "$AUTO_RESULT"
}
auto_exit() {
 AUTO_RC=$?
 if [ "$AUTO_RC" != 0 ]; then
  rm -f "$AUTO_PENDING" "$AUTO_OK"
  if [ "$AUTO_OWN_LOCK" = true ]; then
   rm -f "$S/lock/boot" "$S/lock/created"
   rmdir "$S/lock" 2>/dev/null || true
  fi
  auto_result failed
  if [ -n "$AUTO_JOB" ] && [ "$(cat "$S/latest" 2>/dev/null)" = "$AUTO_JOB" ]; then
   echo failed > "$AUTO_JOB/state"
   echo '自动部署失败，已停止；部分步骤可能完成，请查看日志并单独恢复。' > "$AUTO_JOB/message"
  fi
 fi
}
trap auto_exit EXIT
platform
integrity
AUTO_BOOT=$(boot)
[ -n "$AUTO_BOOT" ] || fail 'Cannot read boot identity'
AUTO_FINGERPRINT=$(sha "$M/control.sha256")
[ "${#AUTO_FINGERPRINT}" = 64 ] || fail 'Cannot read package fingerprint'
validate_ids "$AUTO_IDS"
[ "$(printf '%s' "$ORDER" | tr ' ' ',')" = "$AUTO_IDS" ] || fail 'Automatic selection differs from catalog'
if [ "$AUTO_ACTION" = flash ]; then
 [ "${KSU:-}" = true ] || fail 'KernelSU installer required'
else
 [ "$(wc -l < "$AUTO_PENDING" | tr -d ' ')" = 4 ] || fail 'Invalid continuation record'
 [ "$(sed -n '1p' "$AUTO_PENDING")" = "$AUTO_FINGERPRINT" ] || fail 'Package changed; continuation stopped'
 [ "$(sed -n '4p' "$AUTO_PENDING")" = phone ] || fail 'Invalid deferred component'
 case ",$AUTO_IDS," in *,phone,*) ;; *) fail 'Phone not selected';; esac
 [ -n "$(sed -n '2p' "$AUTO_PENDING")" ] || fail 'Invalid flash boot identity'
 [ "$(sed -n '2p' "$AUTO_PENDING")" != "$AUTO_BOOT" ] || exit 0
 AUTO_PREVIOUS=$(sed -n '3p' "$AUTO_PENDING")
 case "$AUTO_PREVIOUS" in "$S"/jobs/flash-*) ;; *) fail 'Invalid continuation job';; esac
 AUTO_JOB_NAME=${AUTO_PREVIOUS#"$S/jobs/flash-"}
 case "$AUTO_JOB_NAME" in ''|*[!0-9-]*) fail 'Invalid continuation job name';; esac
 if [ "$(cat "$S/latest" 2>/dev/null)" != "$AUTO_PREVIOUS" ]; then
  rm -f "$AUTO_PENDING"
  auto_result cancelled
  echo '用户已执行其他组件任务；自动续装已取消。'
  exit 0
 fi
 [ "$(cat "$AUTO_PREVIOUS/state" 2>/dev/null)" = succeeded ] || fail 'Previous batch did not succeed'
fi
[ ! -e "$S/lock" ] && [ ! -e /data/adb/xuanyuan-unified-state/lock ] || fail 'Existing task lock; no automatic takeover'
if [ "$AUTO_ACTION:${AUTO_PAIRED_XIAOAI:-false}" = flash:true ]; then
 case ",$AUTO_IDS," in *,xiaoai,*) ;; *) fail 'Unselected XiaoAI pair';; esac
 payload_ok xiaoai
 AUTO_PRIVACY=$("$BB" unzip -p "$M/payload/xiaoai.zip" privacy.sh | sha256sum | cut -d' ' -f1)
 [ "${#AUTO_PRIVACY}" = 64 ] || fail 'Cannot verify paired XiaoAI'
 AUTO_PAIR_ROOT="$MODULES/xuanyuan-os4-xiaoai"
 if [ -e "${MODULES}_update/xuanyuan-os4-xiaoai" ]; then AUTO_PAIR_ROOT="${MODULES}_update/xuanyuan-os4-xiaoai"; fi
 [ "$(prop "$AUTO_PAIR_ROOT" id)" = xuanyuan-os4-xiaoai ] && [ "$(prop "$AUTO_PAIR_ROOT" versionCode)" = "$CODE" ] && [ "$(sha "$AUTO_PAIR_ROOT/privacy.sh")" = "$AUTO_PRIVACY" ] || fail 'Paired XiaoAI staging does not match this payload'
 AUTO_PAIR=true
fi
for AUTO_PATH in "${MODULES}_update"/* "$MODULES"/*/update "$MODULES"/*/remove; do
 [ -e "$AUTO_PATH" ] || continue
 if [ "$AUTO_ACTION" = flash ] && [ "$AUTO_PATH" = "$M" ]; then continue; fi
 if [ "$AUTO_PAIR" = true ]; then
  case "$AUTO_PATH" in
   "${MODULES}_update/xuanyuan-os4-xiaoai") [ "$AUTO_PAIR_ROOT" = "$AUTO_PATH" ] || fail 'Unexpected XiaoAI staging'; continue;;
   "$MODULES/xuanyuan-os4-xiaoai/update") continue;;
  esac
 fi
 fail 'Other module changes pending; reboot and review first'
done
AUTO_LATEST=$(cat "$S/latest" 2>/dev/null || true)
if [ -n "$AUTO_LATEST" ]; then
 case "$AUTO_LATEST" in "$S"/jobs/*) ;; *) fail 'Invalid previous job';; esac
 case "$(cat "$AUTO_LATEST/state" 2>/dev/null)" in queued|running) fail 'Existing unfinished task';; esac
fi
[ "$(prop "$MODULES/meta-overlayfs" versionCode)" = 13100 ] || fail 'OverlayFS 1.3.1 required'
[ ! -e "$MODULES/meta-overlayfs/update" ] && [ ! -e "${MODULES}_update/meta-overlayfs" ] || fail 'OverlayFS update pending'
[ ! -e /data/adb/metamodule/modules.img ] || mountpoint -q /data/adb/metamodule/mnt || fail 'Reboot to mount OverlayFS first'
for AUTO_ID in $ORDER; do
 lookup "$AUTO_ID"
 if [ "$KIND" = module ]; then
  [ ! -e "$MODULES/$MID/remove" ] || fail 'Selected module removal pending'
  if [ "$AUTO_ID:$AUTO_PAIR" != xiaoai:true ]; then
   [ ! -e "$MODULES/$MID/update" ] && [ ! -e "${MODULES}_update/$MID" ] || fail 'Selected module has pending changes'
  fi
 fi
 payload_ok "$AUTO_ID"
done
for AUTO_DEP in zygisk_lsposed zygisksu; do
 [ ! -e "$MODULES/$AUTO_DEP/update" ] && [ ! -e "$MODULES/$AUTO_DEP/remove" ] && [ ! -e "${MODULES}_update/$AUTO_DEP" ] || fail 'Framework update pending'
done
case ",$AUTO_IDS," in *,wallet,*)
 AUTO_WALLET=$(wallet_check) || fail 'Unknown wallet/TSM identity; preserved'
 case "$AUTO_WALLET" in eea) AUTO_WALLET=confirmation-required;; cn) ;; *) fail 'Invalid wallet mode';; esac
 ;; esac
auto_market_ready() {
 enabled xuanyuan-os4-market && present com.xiaomi.market || return 1
 ! pm list packages -d --user 0 | grep -qx 'package:com.xiaomi.market' || return 1
 AUTO_BTIME=$("$BB" awk '$1=="btime"{print $2}' /proc/stat)
 AUTO_CTIME=$(stat -c %Z "$MODULES/xuanyuan-os4-market/module.prop")
 case "$AUTO_BTIME:$AUTO_CTIME" in *[!0-9:]*|:*|*:) return 1;; esac
 [ "$AUTO_CTIME" -lt "$AUTO_BTIME" ]
}
if [ "$AUTO_ACTION" = resume ]; then
 auto_market_ready || fail 'Market boot barrier not satisfied'
 AUTO_BATCH=phone
else
 for AUTO_ID in $ORDER; do
  if [ "$AUTO_ID:$AUTO_WALLET" = wallet:confirmation-required ]; then continue; fi
  if [ "$AUTO_ID:$AUTO_PAIR" = xiaoai:true ]; then continue; fi
  if [ "$AUTO_ID" = phone ] && ! auto_market_ready; then AUTO_DEFERRED=phone; continue; fi
  AUTO_BATCH=${AUTO_BATCH:+$AUTO_BATCH,}$AUTO_ID
 done
fi
# Extra native guards are identical to the reviewed three-component flash route.
case ",$AUTO_BATCH," in *,assistant,*)
 case "$(sha /system_ext/lib64/libhyper_os_core_system_private.dylib.so)" in
  a7de453780f33d2dec0cfca8832d218ee798f3208df06af36744f416313afa1f|5d7b4fd34dd7878d1d4d988afcc456672ca3eb7df9345ce9767783810ac2f182|71fa522160812cb9bf5f5f4f0f0227ed9acb227c9102521a65c0c6e3d172212f) ;;
  *) fail 'Rust runtime differs from reviewed build';;
 esac
 [ "$(sha /apex/com.android.runtime/lib64/bionic/libc.so)" = f6c25ea4d8b9a4dc76d6964f78edc9831cd676837a8f91d93a1cb4e87808e32e ] || fail 'Bionic runtime differs'
 AUTO_HOME=$(dumpsys package com.miui.home | sed -n 's/^    versionCode=\([0-9]*\).*/\1/p' | head -n 1)
 [ "$AUTO_HOME" = 801027654 ] || fail 'Launcher 801027654 required'
 AUTO_RETIRED=/data/adb/metamodule/mnt/xuanyuan-os4-assistant/product/priv-app/MiuiHome/MiuiHome.apk
 [ ! -f "$AUTO_RETIRED" ] || [ "$(sha "$AUTO_RETIRED")" = b5e9aaa1ef1f052e3b9e31c685ff201436700728d5fc52d9d56d0c9326fdfa9c ] || fail 'Unexpected retired launcher'
 ;; esac
case ",$AUTO_BATCH," in *,xiaoai,*)
 pm list libraries | grep -qx 'library:vendor.xiaomi.hardware.misys.V3_0' || fail 'misys V3_0 required'
 [ "$(sha /system_ext/framework/miui-services.jar)" = cef17afe99cfa6396922e2fe1dce6642ec86ddcf141589b8ef4d007d6920ecdb ] || fail 'miui-services differs'
 [ "$(pkg_sha com.xiaomi.aicr)" = f081299f3e638d188a2d3d2ace6aeef4ab9d0226f775fc7474495812f67b8520 ] || fail 'Original AI engine 4.12.19 required'
 ;; esac
if [ -n "$AUTO_BATCH" ]; then
 preflight install "$AUTO_BATCH"
 mkdir -p "$S/jobs"
 mkdir "$S/lock" 2>/dev/null || fail 'Task lock exists'
 AUTO_OWN_LOCK=true
 if [ "$AUTO_ACTION" = resume ] && { [ "$(cat "$S/latest" 2>/dev/null)" != "$AUTO_PREVIOUS" ] || [ "$(cat "$AUTO_PREVIOUS/state" 2>/dev/null)" != succeeded ]; }; then
  rmdir "$S/lock"; AUTO_OWN_LOCK=false
  rm -f "$AUTO_PENDING"
  auto_result cancelled
  echo '手动任务已改变部署记录；自动续装已取消。'
  exit 0
 fi
 boot > "$S/lock/boot"
 date +%s > "$S/lock/created"
 AUTO_JOB="$S/jobs/flash-$(date +%s)-$$"
 mkdir "$AUTO_JOB"
 echo "$AUTO_JOB" > "$S/latest"
 echo queued > "$AUTO_JOB/state"
 AUTO_PIPE=0
 AUTO_OWN_LOCK=false
 # A pipe is required for Binder-safe stdout. tee exit alone is not success.
 XLS_FLASH_WORKER=1 sh "$M/control.sh" worker "$AUTO_JOB" install "$AUTO_BATCH" 2>&1 | "$BB" tee "$AUTO_JOB/log" || AUTO_PIPE=$?
 [ "$AUTO_PIPE" = 0 ] && [ "$(cat "$AUTO_JOB/state")" = succeeded ] || fail "Automatic batch failed; log: $AUTO_JOB/log"
 [ ! -e "$S/lock" ] || fail 'Worker lock not released'
fi
rm -f "$AUTO_PENDING" "$AUTO_OK"
if [ -n "$AUTO_DEFERRED" ]; then
 [ -n "$AUTO_JOB" ] || fail 'Cannot establish continuation job'
 printf '%s\n%s\n%s\nphone\n' "$AUTO_FINGERPRINT" "$AUTO_BOOT" "$AUTO_JOB" > "$AUTO_PENDING.new"
 chmod 600 "$AUTO_PENDING.new"
 mv "$AUTO_PENDING.new" "$AUTO_PENDING"
 auto_result reboot-required
 AUTO_MESSAGE='当前批次已完成；手动重启后自动续装电话，不自动重启。'
elif [ "$AUTO_WALLET" = confirmation-required ]; then
 auto_result wallet-confirmation-required
 AUTO_MESSAGE='所选非钱包组件部署完成；首次钱包TSM迁移须在组件配置中单独确认。'
else
 printf '%s\n' "$AUTO_IDS" > "$AUTO_OK"
 auto_result deployed
 AUTO_MESSAGE='所选组件部署完成；挂载须手动重启，兼容开关及LSPosed仍需用户配置。'
fi
if [ -n "$AUTO_JOB" ]; then printf '%s\n' "$AUTO_MESSAGE" > "$AUTO_JOB/message"; fi
echo "$AUTO_MESSAGE"
