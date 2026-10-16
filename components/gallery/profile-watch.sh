#!/system/bin/sh
MOD=/data/adb/modules/xuanyuan-os4-gallery
STATE=/data/adb/xuanyuan-os4-gallery-state
while [ "$(getprop sys.boot_completed)" != 1 ]; do sleep 2; done
while [ -d "$MOD" ] && [ ! -f "$MOD/disable" ] && [ ! -f "$MOD/remove" ]; do sleep 15; done
sh "$STATE/profiles.sh" restore
