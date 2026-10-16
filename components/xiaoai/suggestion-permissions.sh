#!/system/bin/sh
# One-time grants for suggestions; subsequent user revocations are respected.
set -eu
[ "$(getprop ro.product.device)" = xuanyuan ] && [ "$(getprop ro.build.version.sdk)" = 37 ] && [ "$(getprop ro.build.version.incremental)" = OS4.0.0.6.XOAEUXM ] || exit 1
STATE=/data/adb/xuanyuan-os4-xiaoai-state
MARKER="$STATE/suggestion-permissions-v1.done"
[ ! -f "$MARKER" ] || { echo 'Suggestions: initial grants already applied; user choices retained'; exit 0; }
check_apk() {
 LIVE=$(pm path --user 0 "$1" | sed -n 's/^package://p')
 [ -f "$LIVE" ] && [ "$(sha256sum "$LIVE" | cut -d' ' -f1)" = "$2" ]
}
check_apk com.xiaomi.aicr f081299f3e638d188a2d3d2ace6aeef4ab9d0226f775fc7474495812f67b8520 || { echo 'Suggestions: engine mismatch'; exit 1; }
check_apk com.miui.personalassistant 6ecb326cd18351e032f5fe493c1bc1bb28e417bd03954e5133c237bcffc43562 || { echo 'Suggestions: install matching assistant 1.4 first'; exit 1; }
mkdir -p "$STATE"
chmod 700 "$STATE"
if [ ! -f "$STATE/suggestion-permissions-before.txt" ]; then
 { dumpsys package com.xiaomi.aicr; cmd appops get com.xiaomi.aicr; dumpsys package com.miui.personalassistant; } | tee "$STATE/suggestion-permissions-before.txt" >/dev/null
 chmod 600 "$STATE/suggestion-permissions-before.txt"
fi
# Foreground location must precede background location. No AppOps blanket override.
for PERMISSION in POST_NOTIFICATIONS ACCESS_COARSE_LOCATION ACCESS_FINE_LOCATION ACCESS_BACKGROUND_LOCATION READ_CALENDAR BLUETOOTH_CONNECT BLUETOOTH_SCAN ACTIVITY_RECOGNITION; do
 pm grant --user 0 com.xiaomi.aicr "android.permission.$PERMISSION"
done
pm grant --user 0 com.miui.personalassistant android.permission.POST_NOTIFICATIONS
touch "$MARKER"
chmod 600 "$MARKER"
echo 'Suggestions: initial runtime grants applied; agreements unchanged'
