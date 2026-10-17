#!/system/bin/sh
# Source the controller with its library argv, retaining this command's argv.
stock_library() { set -- library; . "${0%/*}/control.sh"; }
stock_library
case "${1:-}" in
 status) [ "$#" = 1 ] || fail 'Expected status';;
 disable|enable)
  [ "$#" = 2 ] || fail 'Expected enable/disable phone|sms'
  case "$2" in phone|sms) ;; *) fail 'Unknown original app';; esac;;
 *) fail 'Expected status or enable/disable phone|sms';;
esac
A_ACTION=$1
platform; integrity

stock_target() {
 A_ID=$1
 case "$1" in
  phone) A_OLD=com.google.android.dialer; A_NEW=com.android.contacts; A_ROLE=DIALER;;
  sms) A_OLD=com.google.android.apps.messaging; A_NEW=com.android.mms; A_ROLE=SMS;;
 esac
 A_MARK="$S/stock-apps/$A_ID.disabled"
}
stock_has() { printf '%s\n' "$1" | grep -Fqx "package:$2"; }
stock_packages() {
 A_INSTALLED=$(pm list packages --user 0) || fail 'Package query failed'
 A_ENABLED=$(pm list packages -e --user 0) || fail 'Enabled package query failed'
 A_DISABLED=$(pm list packages -d --user 0) || fail 'Disabled package query failed'
 for A_LIST in "$A_INSTALLED" "$A_ENABLED" "$A_DISABLED"; do
  if printf '%s\n' "$A_LIST" | grep -Eqv '^(package:[[:alnum:]_.]+)?$'; then fail 'Invalid package query'; fi
 done
}
stock_role() {
 A_HOLDER=$(cmd role get-role-holders --user 0 "android.app.role.$A_ROLE") || fail 'Default role query failed'
}
stock_idle() {
 [ "${1:-}" = owned ] || [ ! -e "$S/lock" ] || return 1
 [ ! -e /data/adb/xuanyuan-unified-state/lock ] || return 1
 if [ -e "$S/latest" ]; then
  A_LATEST=$(cat "$S/latest") || return 1
  case "$A_LATEST" in "$S"/jobs/*) ;; *) return 1;; esac
  A_STATE=$(cat "$A_LATEST/state") || return 1
  case "$A_STATE" in ''|queued|running) return 1;; esac
 fi
}
stock_component() {
 case " $ORDER " in *' phone '*) ;; *) return 1;; esac
 lookup phone && [ "$KIND" = module ] && enabled "$MID" || return 1
 [ "$(prop "$MODULES/$MID" id)" = xuanyuan-os4-phone ] || return 1
 OP=stock
 module_version_ok || return 1
 for A_DIR in "$M" "$MODULES/$MID"; do
  [ ! -e "$A_DIR/disable" ] && [ ! -e "$A_DIR/remove" ] && [ ! -e "$A_DIR/update" ] || return 1
 done
 [ ! -e "${MODULES}_update/$MID" ] && [ ! -e "${MODULES}_update/xuanyuan-os4-suite" ] && [ ! -e "${MODULES}_update/${M##*/}" ] || return 1
 A_PAYLOAD_HASH=$(sha256sum "$M/payload/$FILE") || return 1
 [ "${A_PAYLOAD_HASH%% *}" = "$SHA" ] || return 1
 for A_SCRIPT in restore-stock.sh uninstall.sh; do
  # The sentinel preserves trailing newlines and the unzip exit status without
  # extracting files during read-only status checks.
  A_CONTENT=$("$BB" unzip -p "$M/payload/$FILE" "$A_SCRIPT" && printf '.') || return 1
  A_HOOK_HASH=$(printf '%s' "${A_CONTENT%.}" | sha256sum) || return 1
  A_LIVE_HASH=$(sha256sum "$MODULES/$MID/$A_SCRIPT") || return 1
  [ "${A_LIVE_HASH%% *}" = "${A_HOOK_HASH%% *}" ] || return 1
 done
}
# 1 means an unmet gate; 2 means a failed query, which status must report.
stock_owned() {
 stock_has "$A_INSTALLED" "$1" && stock_has "$A_ENABLED" "$1" && ! stock_has "$A_DISABLED" "$1" || return 1
 A_EXPECTED=$("$BB" awk -F'|' -v p="$1" '$1=="phone" && $2==p{print $3}' "$M/owned-packages.txt") || return 2
 [ "${#A_EXPECTED}" = 64 ] || return 1
 case "$A_EXPECTED" in *[!0-9a-f]*) return 1;; esac
 A_PATH=$(pm path --user 0 "$1") || return 2
 case "$A_PATH" in package:/*) A_PATH=${A_PATH#package:};; *) return 2;; esac
 [ -f "$A_PATH" ] || return 2
 A_HASH=$(sha256sum "$A_PATH") || return 2
 [ "${A_HASH%% *}" = "$A_EXPECTED" ]
}
stock_ready() {
 stock_component && [ "$A_HOLDER" = "$A_NEW" ] || return 1
 stock_owned "$A_NEW" || return $?
 [ "$A_ID" != phone ] || stock_owned com.android.incallui
}
stock_status() {
 stock_target "$1"; stock_role
 A_PRESENT=false A_OFF=false A_CAN=false
 stock_has "$A_INSTALLED" "$A_OLD" && A_PRESENT=true
 stock_has "$A_DISABLED" "$A_OLD" && A_OFF=true
 if stock_idle && [ "$A_PRESENT:$A_OFF" = true:false ] && stock_has "$A_ENABLED" "$A_OLD"; then
  stock_ready; A_RC=$?
  case "$A_RC" in 0) A_CAN=true;; 2) fail 'Replacement identity query failed';; esac
 fi
 printf '{"installed":%s,"disabled":%s,"holder":' "$A_PRESENT" "$A_OFF"
 printf '%s' "$A_HOLDER" | json
 printf ',"can_disable":%s}' "$A_CAN"
}
if [ "$A_ACTION" = status ]; then
 stock_packages
 A_PHONE=$(stock_status phone) || exit 1
 A_SMS=$(stock_status sms) || exit 1
 printf '{"phone":%s,"sms":%s}\n' "$A_PHONE" "$A_SMS"
 exit 0
fi

stock_idle || fail 'Controller or migration task pending; no lock takeover'
mkdir -p "$S" || fail 'Cannot create controller state'
mkdir "$S/lock" 2>/dev/null || fail 'Controller lock exists'
stock_unlock() {
 rm -f "$S/lock/boot" "$S/lock/pid" "$S/lock/created"
 rmdir "$S/lock"
}
trap stock_unlock EXIT
trap 'exit 130' INT TERM
boot > "$S/lock/boot" && [ -s "$S/lock/boot" ] &&
 printf '%s\n' "$$" > "$S/lock/pid" && date +%s > "$S/lock/created" || fail 'Cannot record lock ownership'
# Recheck inside the same controller lock; never reconcile somebody else's lock.
platform; integrity
stock_idle owned || fail 'Controller or migration task pending'
stock_target "$2"; stock_packages
stock_has "$A_INSTALLED" "$A_OLD" || fail 'Original app is not installed for user 0; cannot restore or disable it'
if [ "$A_ACTION" = enable ]; then
 pm enable --user 0 "$A_OLD" || fail 'Original app enable failed; marker retained'
 stock_packages
 stock_has "$A_INSTALLED" "$A_OLD" && stock_has "$A_ENABLED" "$A_OLD" && ! stock_has "$A_DISABLED" "$A_OLD" || fail 'Original app enable not verified; marker retained'
 rm -f "$A_MARK" || fail 'Cannot remove original app marker'
 echo 'Original app enabled; data preserved.'
 exit 0
fi
stock_role
stock_ready || fail 'Replacement, role or module gate failed; no app disabled'
if stock_has "$A_DISABLED" "$A_OLD"; then
 echo 'Original app already disabled; ownership marker unchanged.'
 exit 0
fi
stock_has "$A_ENABLED" "$A_OLD" || fail 'Original app enabled state unknown'
mkdir -p "$S/stock-apps" && printf '%s\n' "$A_OLD" > "$A_MARK" || fail 'Cannot record original app marker'
stock_disabled() (
 stock_packages; stock_role
 stock_has "$A_INSTALLED" "$A_OLD" && stock_has "$A_DISABLED" "$A_OLD" && ! stock_has "$A_ENABLED" "$A_OLD" && [ "$A_HOLDER" = "$A_NEW" ]
)
if pm disable-user --user 0 "$A_OLD" && stock_disabled; then
 echo 'Original app disabled; data preserved.'
 exit 0
fi
# Even a failed pm command may have mutated state. Retain ownership until the
# original is positively verified enabled; a changed role is never rewritten.
stock_rolled_back() (
 stock_packages
 stock_has "$A_INSTALLED" "$A_OLD" && stock_has "$A_ENABLED" "$A_OLD" && ! stock_has "$A_DISABLED" "$A_OLD"
)
if pm enable --user 0 "$A_OLD" && stock_rolled_back; then
 rm -f "$A_MARK" || fail 'Rollback verified but marker removal failed'
 fail 'Disable failed or role changed; original app re-enabled'
fi
fail 'Disable failed; rollback not verified, marker retained for recovery'
