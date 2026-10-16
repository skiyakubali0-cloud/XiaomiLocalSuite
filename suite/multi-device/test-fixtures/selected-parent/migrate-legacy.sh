#!/system/bin/sh
# Fixed five-package migration. Xiaomi apps, account data, cards and XMSF are excluded.
set -eu
S=/data/adb/xuanyuan-unified-state
SELF=local.xuanyuan.mipushcompat
SELF_SHA=660cb1245fa9dac261d64570fba557ba44c166382960799b27bc130b59e14d25
fail() { echo "$*" >&2; exit 1; }
sha() { sha256sum "$1" | cut -d' ' -f1; }
path() { pm path --user 0 "$1" 2>/dev/null | sed -n 's/^package://p' || true; }
known() {
 case "$1" in
 local.xuanyuan.smscompat) echo 7bcafbdba0dc0acc54541e569ecc5c0c15680d433e4794f855b15dc6c6a1c2bb;;
 local.xuanyuan.aiprivacy) echo deb3c55f637b34db05ed2fe61cc62392dd9eb506f7934ca8c14eb0af87da894f;;
 local.xuanyuan.suggestioncompat) echo 0e5eb88a019a25798a88d25e34d5035311c1513d3bd6da72d2053ddd73112757;;
 local.xuanyuan.disastercompat) echo fdf55ce527873da0036bf4219eeb6c3775bfaadae2adeb42583e6712bb3f55f3;;
 local.xuanyuan.clockcompat) echo 7c85575c3b32decdc5398d905d7a1d4f3655b9f1f3ee8cdbad59721d1521a073;;
 *) return 1;;
 esac
}
PACKAGES='local.xuanyuan.smscompat local.xuanyuan.aiprivacy local.xuanyuan.suggestioncompat local.xuanyuan.disastercompat local.xuanyuan.clockcompat'
[ "$#" = 1 ] || fail '需要一个固定操作'
case "$1" in status|remove|restore) ;; *) fail '未知操作';; esac
[ "$(id -u)" = 0 ] || fail '需要Root'
[ "$(getprop ro.product.device)" = xuanyuan ] && [ "$(getprop ro.build.version.sdk)" = 37 ] && [ "$(getprop ro.build.version.incremental)" = OS4.0.0.6.XOAEUXM ] || fail '不支持此机型或系统'
[ "$(am get-current-user)" = 0 ] && [ "$(pm list users | grep -c 'UserInfo{')" = 1 ] || fail '只支持机主单用户0'
P=$(path "$SELF")
[ -n "$P" ] && [ -f "$P" ] && [ "$(sha "$P")" = "$SELF_SHA" ] || fail '统一插件不是本套件精确版本'
BOOT=$(cat /proc/sys/kernel/random/boot_id)
if [ "$1" = status ]; then
 [ ! -d "$S/lock" ] || fail '迁移任务仍在运行或已中断，请检查记录'
 if [ -f "$S/migration-boot" ] && [ "$(cat "$S/migration-boot")" = "$BOOT" ]; then
  echo MIGRATION_REBOOT_REQUIRED
 else echo MIGRATION_READY
 fi
 exit 0
fi
mkdir -p "$S/apks";chmod 700 "$S" "$S/apks"
mkdir "$S/lock" 2>/dev/null || fail '已有迁移任务或中断标记，请检查记录'
trap 'rmdir "$S/lock" 2>/dev/null || true' EXIT
trap 'exit 130' INT TERM
# Complete every source/hash check before modifying any installed package.
COUNT=0
# Old component boot scripts can reinstall legacy APKs or reference their old CLI.
# Require the reviewed replacement to be active/staged before removing its helper.
modern_child() {
 ID=$1
 REQUIRED=2026101501
 case "$ID" in phone) REQUIRED=2026101502;; xiaoai) REQUIRED=2026101504;; esac
 LIVE=/data/adb/modules/xuanyuan-os4-$ID
 NEXT=/data/adb/modules_update/xuanyuan-os4-$ID
 [ ! -f "$LIVE/module.prop" ] || [ -e "$LIVE/disable" ] || [ -e "$LIVE/remove" ] || {
  CODE=$(sed -n 's/^versionCode=//p' "$LIVE/module.prop")
  [ "$CODE" = "$REQUIRED" ] || {
   [ -f "$NEXT/module.prop" ] && [ "$(sed -n 's/^versionCode=//p' "$NEXT/module.prop")" = "$REQUIRED" ] || fail "请先在套件中安装/升级 $ID 组件，再迁移旧插件"
  }
 }
}
for PKG in $PACKAGES; do
 EXPECTED=$(known "$PKG")
 P=$(path "$PKG")
 if [ -n "$P" ]; then [ -f "$P" ] && [ "$(sha "$P")" = "$EXPECTED" ] || fail "$PKG 是未知版本或分包；没有开始迁移"; fi
 if [ "$1" = remove ] && [ -n "$P" ]; then
  case "$PKG" in
   local.xuanyuan.smscompat) modern_child phone;;
   local.xuanyuan.aiprivacy|local.xuanyuan.suggestioncompat) modern_child xiaoai;;
   local.xuanyuan.disastercompat) modern_child disaster;;
  esac
  COUNT=$((COUNT+1))
 fi
 if [ "$1" = restore ] && [ -f "$S/apks/$PKG.apk" ]; then
  [ "$(sha "$S/apks/$PKG.apk")" = "$EXPECTED" ] || fail "$PKG 备份校验失败；没有开始恢复"
  COUNT=$((COUNT+1))
 fi
done
[ "$COUNT" -gt 0 ] || { echo '没有需要处理的已知兼容APK';exit 0; }
if [ "$1" = remove ]; then
 # Save APKs and package state first. -k keeps the compatibility apps' own data.
 for PKG in $PACKAGES; do
  P=$(path "$PKG");[ -n "$P" ] || continue
  if [ ! -f "$S/apks/$PKG.apk" ]; then cp "$P" "$S/apks/$PKG.apk";chmod 600 "$S/apks/$PKG.apk";fi
  [ "$(sha "$S/apks/$PKG.apk")" = "$(known "$PKG")" ] || fail '备份校验失败；没有开始卸载'
  dumpsys package "$PKG" > "$S/$PKG.before.txt";chmod 600 "$S/$PKG.before.txt"
 done
 # Reference snapshots only; never write/restore the LSPosed database.
 mkdir -p "$S/lsp-reference";chmod 700 "$S/lsp-reference"
 for F in modules_config.db modules_config.db-wal modules_config.db-shm; do
  [ ! -f "/data/adb/lspd/config/$F" ] || { cp "/data/adb/lspd/config/$F" "$S/lsp-reference/$F";chmod 600 "$S/lsp-reference/$F"; }
 done
fi
printf '%s\n' "$BOOT" > "$S/migration-boot";chmod 600 "$S/migration-boot"
printf '%s\n' "$1" > "$S/last-action";chmod 600 "$S/last-action"
for PKG in $PACKAGES; do
 if [ "$1" = remove ]; then
  P=$(path "$PKG");[ -n "$P" ] || continue
  pm uninstall -k --user 0 "$PKG" || fail "$PKG 移除未完成；保留备份和重启标记"
  [ -z "$(path "$PKG")" ] || fail "$PKG 仍已安装；请检查记录"
 else
  APK="$S/apks/$PKG.apk";[ -f "$APK" ] || continue
  cat "$APK" | pm install -r --user 0 -S "$(stat -c %s "$APK")" || fail "$PKG 恢复未完成；保留重启标记"
  P=$(path "$PKG");[ -n "$P" ] && [ -f "$P" ] && [ "$(sha "$P")" = "$(known "$PKG")" ] || fail "$PKG 恢复后校验失败"
 fi
done
echo '兼容APK处理完成，原数据保留。请先重启，再核对LSPosed启用和作用域。'
echo '小米应用、MiPush配置、XMSF及钱包凭据未处理。'
