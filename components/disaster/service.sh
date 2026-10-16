#!/system/bin/sh
MODDIR=${0%/*}
STATE=/data/adb/xuanyuan-disaster-state
mkdir -p "$STATE"
chmod 700 "$STATE"
run() {
 for i in $(seq 1 90); do
  [ "$(getprop sys.boot_completed)" = 1 ] && break
  sleep 2
 done
 [ "$(getprop sys.boot_completed)" = 1 ] || return 1
 LIVE=$(pm path --user 0 com.miui.securitycenter | sed -n 's/^package://p')
 [ -f "$LIVE" ] || return 1
 [ "$(sha256sum "$LIVE" | cut -d' ' -f1)" = f3d338484cc5fd3f3fec9e8d9d0b4c6370923fba0f5e0d81975a45e914cbc776 ] || { echo 'INACTIVE: SecurityCenter update differs'; return 1; }
 echo 'PAYLOAD_READY: UI, LSPosed loading, consent, and push subscription require separate checks'
}
run 2>&1 | cat > "$STATE/status.log"
