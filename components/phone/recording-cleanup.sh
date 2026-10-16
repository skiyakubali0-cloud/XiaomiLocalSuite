#!/system/bin/sh
# An owned runtime overlay must not outlive the module being disabled/removed.
for i in $(seq 1 120); do
  [ "$(getprop sys.boot_completed)" = 1 ] && break
  sleep 2
done
MOD=/data/adb/modules/xuanyuan-os4-phone
while [ -f "$MOD/module.prop" ] && [ ! -e "$MOD/disable" ] && [ ! -e "$MOD/remove" ] && [ "$(getprop ro.build.version.incremental)" = OS4.0.0.6.XOAEUXM ]; do
  sleep 15
done
cmd overlay disable --user 0 com.android.shell:XuanyuanCallRecording
