#!/system/bin/sh
# Exact-ROM wallet lifecycle. mode/status never clear data or install APKs.
W_DIR=${0%/*}
W_STATE=/data/adb/xuanyuan-os4-wallet-state
W_MARK=/data/adb/xuanyuan-os4-wallet-reset-authorized
W_EEA=c31f66629723c3c60a8d0862e68f2777b0187afe7271bbec2df7468bd5d350bb
W_CN=567e8f05e4b2cbc7c203ce5f10672756ea8af0542c3fc5aafaa3e677ebcaa671
W_MIPAY=2aa4d85ae0e23764fdc96d0d5d4b314a5a90e915f0ed02a85093522e216e7d51
w_fail() { echo "WALLET_ERROR: $*" >&2; exit 1; }
w_sha() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1; }
w_path() { pm path --user 0 "$1" 2>/dev/null | sed -n 's/^package://p'; }
w_platform() {
 [ "$(id -u)" = 0 ] && [ "$(am get-current-user)" = 0 ] || w_fail 'owner0/root required'
 [ "$(pm list users | grep -c 'UserInfo{')" = 1 ] || w_fail 'single owner0 required'
 [ "$(getprop ro.product.device)" = xuanyuan ] && [ "$(getprop ro.build.version.sdk)" = 37 ] && [ "$(getprop ro.build.version.incremental)" = OS4.0.0.6.XOAEUXM ] || w_fail 'exact xuanyuan EEA OS4.0.0.6 required'
}
w_wallet() {
 W_PATH=$(w_path com.mipay.wallet)
 if [ -n "$W_PATH" ]; then
  [ -f "$W_PATH" ] || w_fail 'split/unknown wallet path'
  case "$(w_sha "$W_PATH")" in
   "$W_MIPAY"|c5fa1012886f21d9be2453d66e741d6821e9b94d39a6881318c3d1d196ddb058) ;;
   *) w_fail 'unreviewed wallet APK; preserved';;
  esac
 elif [ -n "$(pm list packages -u --user 0 com.mipay.wallet)" ]; then
  w_fail 'unregistered wallet remnants; preserved'
 fi
}
w_mode() {
 w_platform; w_wallet
 W_TSM=/product/app/MITSMClientGlobal/MITSMClientGlobal.apk
 [ "$(w_path com.miui.tsmclient)" = "$W_TSM" ] || w_fail 'unknown TSM path/update'
 W_HASH=$(w_sha "$W_TSM")
 W_UID=$(pm list packages -U --user 0 com.miui.tsmclient)
 case "$W_HASH:$W_UID" in
  "$W_EEA:package:com.miui.tsmclient uid:10214") echo eea;;
  "$W_CN:package:com.miui.tsmclient uid:1027") echo cn;;
  *) w_fail 'TSM APK/UID pair is not reviewed';;
 esac
}
w_migrate() {
 W_MODE=$(w_mode) || exit 1
 [ "$W_MODE" != cn ] || { echo 'Existing CN TSM; no reset'; return 0; }
 W_BOOT=$(cat /proc/sys/kernel/random/boot_id)
 [ "$(cat "$W_MARK" 2>/dev/null)" = "RESET_XIAOMI_TSM_ONLY:$W_BOOT:$W_EEA" ] || w_fail 'explicit one-job migration consent required'
 mkdir -p "$W_STATE"; chmod 700 "$W_STATE"
 W_BACK="$W_STATE/first-migration-$(date +%s)-$$"
 mkdir "$W_BACK" && chmod 700 "$W_BACK" || w_fail 'cannot create private recovery folder'
 W_ROLE=$(cmd role get-role-holders --user 0 android.app.role.WALLET) || w_fail 'wallet role snapshot failed; no clear'
 W_PAYMENT=$(settings get secure nfc_payment_default_component) || w_fail 'payment default snapshot failed; no clear'
 printf '%s\n' "$W_ROLE" > "$W_BACK/wallet-role.before" || w_fail 'cannot save wallet role; no clear'
 printf '%s\n' "$W_PAYMENT" > "$W_BACK/payment.before" || w_fail 'cannot save payment default; no clear'
 for W_PARENT in /data/user/0 /data/user_de/0; do
  if [ -d "$W_PARENT/com.miui.tsmclient" ]; then
   case "$W_PARENT" in /data/user/0) W_NAME=ce;; *) W_NAME=de;; esac
   tar -cpf "$W_BACK/tsm-$W_NAME.tar" -C "$W_PARENT" com.miui.tsmclient || w_fail 'private TSM backup failed; no clear'
   chmod 600 "$W_BACK/tsm-$W_NAME.tar"
  fi
 done
 [ "$(w_mode)" = eea ] || w_fail 'TSM changed during backup; no clear'
 [ "$(cat "$W_MARK" 2>/dev/null)" = "RESET_XIAOMI_TSM_ONLY:$W_BOOT:$W_EEA" ] || w_fail 'consent changed during backup; no clear'
 # Consume before the irreversible action; the controller also cleans on failure.
 rm -f "$W_MARK" || w_fail 'cannot consume consent'
 W_RESULT=$(pm clear --user 0 com.miui.tsmclient 2>&1)
 [ "$W_RESULT" = Success ] || w_fail "TSM clear failed: $W_RESULT"
 printf '%s\n' "$W_BOOT" > "$W_STATE/migration-boot"
 echo TSM_RESET_FOR_UID_MIGRATION > "$W_STATE/phase"
 echo 'First EEA TSM migration prepared; reboot required. UID-bound keys are not restored by the backup.'
}
w_ready() {
 [ "$(w_mode)" = cn ] || w_fail 'CN TSM UID1027 not active; reboot/check migration'
 W_PATH=$(w_path com.mipay.wallet)
 [ -n "$W_PATH" ] || w_fail 'wallet not installed'
 pm list packages --user 0 com.mipay.wallet | grep -qx package:com.mipay.wallet || w_fail 'wallet not registered for owner0'
 if pm list packages -d --user 0 com.mipay.wallet | grep -qx package:com.mipay.wallet; then w_fail 'wallet disabled'; fi
 echo 'READY: exact CN TSM UID1027 and reviewed wallet registered/enabled; payment/card functionality untested'
}
w_prepare() {
 [ "$(w_mode)" = cn ] || w_fail 'CN TSM UID1027 not active'
 if [ -z "$(w_path com.mipay.wallet)" ]; then
  [ "$(w_sha "$W_DIR/payload/Mipay.apk")" = "$W_MIPAY" ] || w_fail 'Mipay payload mismatch'
  cat "$W_DIR/payload/Mipay.apk" | pm install -r --user 0 -i com.xiaomi.market -S "$(stat -c %s "$W_DIR/payload/Mipay.apk")" || w_fail 'Mipay install failed'
 fi
 pm enable --user 0 com.mipay.wallet >/dev/null || w_fail 'cannot enable wallet'
 w_ready
}
[ "$#" = 1 ] || w_fail 'one action required'
case "$1" in mode) w_mode;; migrate) w_migrate;; prepare) w_prepare;; status) w_ready;; *) w_fail 'unknown action';; esac
