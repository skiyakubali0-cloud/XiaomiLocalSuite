#!/system/bin/sh
# current11: explicit actions only; no boot service, preferences or credential writes.
M=${0%/*}
P_ARGC=$# ACTION=${1:-} P_COMPONENTS=${2:-} P_FEATURES=${3:-}
set -- library
. "$M/control.sh"
P_ORDER='market assistant xiaoai phone gallery weather disaster wallet clock calendar mipush'
if [ "$ACTION" = capabilities ]; then
 [ "$P_ARGC" = 1 ] || fail 'Expected capabilities without arguments'
 platform; integrity
 [ "$(prop "$M" id)" = xuanyuan-os4-suite ] && [ "$(prop "$M" versionCode)" = 2026101604 ] || fail 'Requires suite 1.7 / 2026101604'
 printf '%s\n' "$ORDER" | tr ' ' ','
 exit 0
fi
P_FEATURE_ORDER='phone privacy suggestions warning clock'
P_PROFILE=''
P_STATE=blocked P_BATCH='' P_WALLET=false P_MESSAGE='Preset check failed' P_BOOT='' P_JOB=''
emit() {
 printf '{"state":"%s","ids":"%s","install_ids":"%s","wallet_pending":%s,"message":' "$P_STATE" "$P_PROFILE" "$P_BATCH" "$P_WALLET"
 printf '%s' "$P_MESSAGE" | json
 printf ',"boot":'; printf '%s' "$P_BOOT" | json
 [ -z "$P_JOB" ] || printf ',"job":%s' "$P_JOB"
 printf '}\n'
}
trap emit EXIT
blocked() { P_STATE=blocked; P_MESSAGE=$*; exit 1; }
check() { P_ERROR=$( ( "$@" ) 2>&1) || blocked "$P_ERROR"; }
P_BOOT=$(boot)
[ "$P_ARGC" = 3 ] || blocked 'Expected ACTION COMPONENT_CSV FEATURE_CSV; use - for empty selection'
case "$ACTION" in plan|apply|apply-wallet|migrate|reboot|lsp) ;; *) blocked 'Unknown preset action';; esac
normalize() {
 P_NORMAL=''
 [ "$1" != - ] || return 0
 case "$1" in ''|*[!a-z,]*|,*|*,|*,,*) blocked 'Invalid selection CSV';; esac
 P_SEEN=,
 for P_TOKEN in $(printf '%s' "$1" | tr ',' ' '); do
  case " $2 " in *" $P_TOKEN "*) ;; *) blocked 'Unknown selection ID';; esac
  case "$P_SEEN" in *",$P_TOKEN,"*) blocked 'Duplicate selection ID';; esac
  P_SEEN=$P_SEEN$P_TOKEN,
 done
 for P_TOKEN in $2; do
  case "$P_SEEN" in *",$P_TOKEN,"*) P_NORMAL=${P_NORMAL:+$P_NORMAL,}$P_TOKEN;; esac
 done
}
normalize "$P_COMPONENTS" "$P_ORDER"; P_PROFILE=$P_NORMAL
normalize "$P_FEATURES" "$P_FEATURE_ORDER"; P_FEATURES=$P_NORMAL
p_selected() { case ",$P_PROFILE," in *",$1,"*) return 0;; *) return 1;; esac; }
add_component() { p_selected "$1" || P_PROFILE=${P_PROFILE:+$P_PROFILE,}$1; }
for P_FEATURE in $(printf '%s' "$P_FEATURES" | tr ',' ' '); do
 case "$P_FEATURE" in
  phone) add_component phone;;
  privacy|suggestions) add_component xiaoai;;
  warning) add_component disaster;;
  clock) add_component clock;;
 esac
done
if p_selected phone; then add_component market; fi
if p_selected xiaoai; then add_component assistant; fi
normalize "${P_PROFILE:--}" "$P_ORDER"; P_PROFILE=$P_NORMAL
check platform
check integrity
[ "$(prop "$M" id)" = xuanyuan-os4-suite ] && [ "$(prop "$M" versionCode)" = 2026101604 ] || blocked 'Requires suite 1.7 / 2026101604'
ORDER=$P_ORDER
P_UNIFIED_STATE=/data/adb/xuanyuan-unified-state
P_NEXT=${MODULES}_update
target() {
 lookup "$1" || blocked 'Catalog component missing'
 case "$1:$CODE" in
  phone:2026101502|xiaoai:2026101603|disaster:2026101501) ;;
  phone:*|xiaoai:*|disaster:*) blocked 'Catalog target does not match current11';;
 esac
}
module_version_guard() { OP=install; module_version_ok || fail 'Unreviewed module version'; }
job_read() {
 P_J=$(cat "$S/latest" 2>/dev/null)
 case "$P_J" in "$S"/jobs/*)
  P_JOB=$(printf '{"state":'; cat "$P_J/state" 2>/dev/null | json
   printf ',"message":'; cat "$P_J/message" 2>/dev/null | json
   printf ',"log":'; tail -100 "$P_J/log" 2>/dev/null | json; printf '}');;
 esac
}
# Never call status/job/reconcile here: even a stale lock is a read-only barrier.
job_read
if [ -d "$S/lock" ] || { [ -n "$P_J" ] && case "$(cat "$P_J/state" 2>/dev/null)" in queued|running) true;; *) false;; esac; }; then
 P_STATE=running; P_MESSAGE='Controller job/lock exists; inspect before continuing'; exit 0
fi
P_JOB=''
[ ! -d "$P_UNIFIED_STATE/lock" ] || blocked 'Migration lock exists; inspect migration records'
P_DISABLED=$(pm list packages -d --user 0) || blocked 'Cannot read package enablement'
pkg_disabled() { printf '%s\n' "$P_DISABLED" | grep -qx "package:$1"; }
P_NEED='' P_PENDING=''
# Validate all selected components before choosing even the market-only batch.
for P_ID in $(printf '%s' "$P_PROFILE" | tr ',' ' '); do
 target "$P_ID"
 P_MISSING=false
 if [ "$KIND" = module ]; then
  if [ -e "$MODULES/$MID" ]; then
   [ -f "$MODULES/$MID/module.prop" ] || blocked "Unknown module $MID"
   [ "$(prop "$MODULES/$MID" id)" = "$MID" ] || blocked "Unknown module identity $MID"
   check module_version_guard
   [ "$(prop "$MODULES/$MID" versionCode)" = "$CODE" ] && enabled "$MID" || P_MISSING=true
  else P_MISSING=true; fi
  # Fresh/disabled modules expose stock EEA packages, not the CN ownership set.
  if enabled "$MID"; then check owned_check "$P_ID"; fi
  while IFS='|' read -r P_OWNER P_PKG P_HASH; do
   [ "$P_OWNER" != "$P_ID" ] || ! pkg_disabled "$P_PKG" || P_MISSING=true
  done < "$M/owned-packages.txt"
 else
  if present "$PKG"; then
   # shared_check permits only reviewed predecessors, never arbitrary APKs/splits.
   if [ "$P_ID" = calendar ]; then check calendar_check
   else check shared_check; fi
   [ "$(pkg_sha "$PKG")" = "$SHA" ] && ! pkg_disabled "$PKG" || P_MISSING=true
  else
   [ -z "$(path_of "$PKG")" ] || blocked "Unregistered package $PKG"
   P_MISSING=true
  fi
 fi
 [ ! -e "$S/restored/$P_ID" ] || P_MISSING=true
 if [ "$P_ID" = wallet ]; then
  W_MODE=$(wallet_check) || blocked 'Unknown wallet/TSM identity; preserved'
  if [ "$W_MODE" = eea ]; then P_WALLET=true; P_MISSING=true; fi
  if ! present com.mipay.wallet || pkg_disabled com.mipay.wallet; then P_MISSING=true; fi
 fi
 [ "$P_MISSING" = false ] || P_NEED=${P_NEED:+$P_NEED,}$P_ID
done
# Remaining package identities are not all represented in owned-packages.txt.
known_apk() {
 if present "$1" || [ -n "$(path_of "$1")" ]; then
  P_HASH=$(pkg_sha "$1"); [ -n "$P_HASH" ] || blocked "Unknown/split APK $1"
  case " $2 " in *" $P_HASH "*) ;; *) blocked "Unknown APK $1";; esac
 fi
}
case ",$P_PROFILE," in
 *,phone,*|*,xiaoai,*|*,disaster,*|*,clock,*|*,mipush,*) check shared_check;;
esac
if p_selected calendar; then check calendar_check; fi
if p_selected clock; then
[ "$(pkg_sha com.android.deskclock)" = 41defcfd640a3ba5d359c20004d9dced5f6c0810204c41c94530af2a2bc1e9f6 ] || blocked 'Native clock must remain exact'
fi
if p_selected gallery; then
known_apk com.miui.gallery 'c25c993cc1462a955b145035ee071d98781ba51370bad232a78eb567eb84cfbc be6bb05752cf667430c9359cd46fa8f4ed3552ecbe2e90a7b6279eaeb471f4a2 6a9c9677a6a6ef398c3d60dad58c71942adab010b8e4e7727b2c028063c3fd9d'
known_apk com.hyper.gallery.plugin 'd0a6af98b4910113fb4ecf62fff349881ec1adde8291682fe500bde59eadf8d1 f763216706094ca04cf2c4e67600595bbfa55f0533b8468a7c36ca2463bf9497'
known_apk com.miui.mediaeditor '52343b5d46f227100fc0b75ee6eed633a431db51f95eb3c2f1ba44ad40aacefc 365954e0e94263b7372fa5e6f4d244690b5edd9607b5642a1488a622732f7756 e7c37c8ee2e10e8e45b60ad3ff293ad8a0b1c702f9e79aaa8df97ecfbcf4f699'
known_apk com.miui.extraphoto 'ca7794bb50c7ab612aab9494d0fc8fe887bfbd5a28ba3ffd8fecaba7a218c7c4 b6149345f1aa4f3b84d84152b186f5c60bc6bc4c95957ac3cc232fb047722756'
fi
if p_selected weather; then
known_apk com.miui.weather2 '2a8faed30ce5ffe4ae0229dce0d520d882dff990f6ef158e5fbb555153b7e887 017d613137c0512a937dc6b8565da856099e988feab47b9eabc5c3d0a13f06e6 9439e87555133762d362bfba651e7ab6e2f01e78b280fdd7ec745cbb6403b025'
known_apk com.miui.core '5abe56881dafbe3540e11c4ff4a450ae7bcd19d93753a251326f09314a2bb9e9 585703b25f0bce27f06f76ed568af9a9bbf58bcf7810600ad23eb4ab57be6902'
fi
if p_selected phone; then
known_apk com.miui.yellowpage 'e07e59b9d9a99b0cce4bf06b9734002016b1c3bebe701c6ee368cdc8161cb733 0c5c655fe93ffc0eade6a77dc56c05754d4a3afab8a6c122acd3a2f8a160c0ba'
known_apk com.miui.audiomonitor '83133a62f37cefe873075064d39c5e176e768af251d678438a242116be8178b1 f84954e6ef361a8204c565bfe365e66344e2984036febe784c1485e113d1ba71'
fi
P_LEGACY=false
for P_FEATURE in $(printf '%s' "$P_FEATURES" | tr ',' ' '); do
 case "$P_FEATURE" in
  phone) P_PAIR='smscompat:7bcafbdba0dc0acc54541e569ecc5c0c15680d433e4794f855b15dc6c6a1c2bb';;
  privacy) P_PAIR='aiprivacy:deb3c55f637b34db05ed2fe61cc62392dd9eb506f7934ca8c14eb0af87da894f';;
  suggestions) P_PAIR='suggestioncompat:0e5eb88a019a25798a88d25e34d5035311c1513d3bd6da72d2053ddd73112757';;
  warning) P_PAIR='disastercompat:fdf55ce527873da0036bf4219eeb6c3775bfaadae2adeb42583e6712bb3f55f3';;
  clock) P_PAIR='clockcompat:7c85575c3b32decdc5398d905d7a1d4f3655b9f1f3ee8cdbad59721d1521a073';;
 esac
 P_PKG=local.xuanyuan.${P_PAIR%%:*}
 known_apk "$P_PKG" "${P_PAIR#*:}"
 if present "$P_PKG" || [ -n "$(path_of "$P_PKG")" ]; then P_LEGACY=true; fi
done
# Unknown updates anywhere are a global stop; only exact current11 stages are trusted.
for P_PATH in "$P_NEXT"/* "$MODULES"/*/update "$MODULES"/*/remove; do
 [ -e "$P_PATH" ] || continue
 P_DIR=$P_PATH
 case "$P_PATH" in */remove) blocked 'Module removal pending';; */update) P_DIR=${P_PATH%/update};; esac
 P_MATCH=''
 if [ "${P_DIR##*/}" = xuanyuan-os4-suite ]; then
  [ "$(prop "$P_DIR" id)" = xuanyuan-os4-suite ] && [ "$(prop "$P_DIR" versionCode)" = 2026101604 ] || blocked 'Unknown staged suite'
  P_PENDING=suite; continue
 fi
 for P_ID in $P_ORDER; do
  target "$P_ID"
  [ "$KIND" = module ] && [ "${P_DIR##*/}" = "$MID" ] || continue
  P_MATCH=$P_ID
  if [ -d "$P_NEXT/$MID" ]; then P_DIR=$P_NEXT/$MID; fi
  [ "$(prop "$P_DIR" id)" = "$MID" ] && [ "$(prop "$P_DIR" versionCode)" = "$CODE" ] || blocked "Unknown staged version $MID"
  case ",$P_PENDING," in *",$P_ID,"*) ;; *) P_PENDING=${P_PENDING:+$P_PENDING,}$P_ID;; esac
  break
 done
 [ -n "$P_MATCH" ] || blocked 'Unknown pending module update'
done
if [ "$ACTION" = reboot ]; then
 check sh "$M/control.sh" reboot
 P_STATE=reboot; P_MESSAGE='Explicit guarded reboot requested'; exit 0
fi
if [ "$ACTION" = lsp ]; then
 check "$K" module action zygisk_lsposed
 P_STATE=ready; P_MESSAGE='LSPosed action opened'; exit 0
fi
if [ -n "$P_PENDING" ] || [ "$(cat "$P_UNIFIED_STATE/migration-boot" 2>/dev/null)" = "$P_BOOT" ]; then
 P_STATE=reboot; P_MESSAGE='Trusted staged changes require reboot'; exit 0
fi
if [ "$P_LEGACY" = true ] && [ "$P_FEATURES" != phone,privacy,suggestions,warning,clock ]; then
 blocked 'Selected legacy helper requires manual migration: review the existing unified-settings five-package migration scope, or select all five compatibility features for the fixed five-package migration'
fi
if p_selected market; then
case ",$P_NEED," in
 *,market,*) P_BATCH=market;;
 *)
  # Inode change time cannot inherit a ZIP's old mtime: require a later boot.
  if ! enabled xuanyuan-os4-market || ! present com.xiaomi.market || pkg_disabled com.xiaomi.market; then
   P_BATCH=market
  else
   P_BTIME=$("$BB" awk '$1=="btime"{print $2}' /proc/stat)
   P_CTIME=$(stat -c %Z "$MODULES/xuanyuan-os4-market/module.prop")
   case "$P_BTIME:$P_CTIME" in *[!0-9:]*|:*|*:) blocked 'Cannot prove market boot barrier';; esac
   if [ "$P_CTIME" -ge "$P_BTIME" ]; then
    P_STATE=reboot; P_MESSAGE='Market requires a completed boot since installation'; exit 0
   fi
   P_BATCH=$P_NEED
  fi;;
esac
else
 P_BATCH=$P_NEED
fi
case ",$P_BATCH," in *,wallet,*) ;; *) P_WALLET=false;; esac
if [ -n "$P_BATCH" ]; then
 check preflight install-wallet "$P_BATCH"
 P_STATE=install; P_MESSAGE='Install/re-enable selected current11 components'
 if [ "$ACTION" = apply ] || [ "$ACTION" = apply-wallet ]; then
  [ "$P_WALLET" != true ] || [ "$ACTION" = apply-wallet ] || blocked 'Confirm first Xiaomi TSM migration in the unified app'
  # start atomically owns the controller lock before any enable operation.
  if [ "$ACTION" = apply-wallet ]; then check start install-wallet "$P_BATCH"; else check start install "$P_BATCH"; fi
  for P_ID in $(printf '%s' "$P_BATCH" | tr ',' ' '); do
   target "$P_ID"
   if [ "$KIND" = module ] && [ -e "$MODULES/$MID/disable" ]; then check "$K" module enable "$MID"; fi
   if [ -n "$PKG" ] && present "$PKG" && pkg_disabled "$PKG"; then check enable_pkg "$PKG"; fi
   if [ "$P_ID" = wallet ] && present com.mipay.wallet && pkg_disabled com.mipay.wallet; then check enable_pkg com.mipay.wallet; fi
  done
  P_STATE=running; P_MESSAGE='Controller installation job started'; job_read
 fi
 [ "$ACTION" != migrate ] || blocked 'Finish installations and reboot before migration'
 exit 0
fi
if [ "$P_LEGACY" = true ]; then
 check sh "$M/migrate-legacy.sh" status
 P_STATE=migrate; P_MESSAGE='Publish five OFF settings in APK UI, then request migration'
 if [ "$ACTION" = migrate ]; then
  check sh "$M/migrate-legacy.sh" remove
  P_STATE=reboot; P_MESSAGE='Legacy helper migration requires reboot'
 fi
else
 P_STATE=ready; P_MESSAGE='current11 ready'
 [ "$P_WALLET" = false ] || P_MESSAGE='Ready except manual wallet migration'
fi
