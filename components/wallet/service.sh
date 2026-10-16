#!/system/bin/sh
MODDIR=${0%/*}
STATE=/data/adb/xuanyuan-os4-wallet-state
umask 077
mkdir -p "$STATE"; chmod 700 "$STATE"
run() {
 for i in $(seq 1 120); do
  [ "$(getprop sys.boot_completed)" != 1 ] || break
  sleep 2
 done
 [ "$(getprop sys.boot_completed)" = 1 ] || { echo 'WALLET_ERROR: boot incomplete'; return 1; }
 sh "$MODDIR/wallet.sh" prepare
}
# Binder must inherit pipe FDs, not a private /data/adb log file.
RESULT="$STATE/prepare-$$.exit"
(run; printf '%s\n' "$?" > "$RESULT") 2>&1 | tee "$STATE/status.log" >/dev/null
RC=$(cat "$RESULT" 2>/dev/null)
printf '%s\n' "$RC" > "$STATE/last-exit"
rm -f "$RESULT"
[ "$RC" = 0 ]
