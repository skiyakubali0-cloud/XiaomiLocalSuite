#!/system/bin/sh
rm -f /data/user_de/0/com.miui.home/files/.os4-assistant-route
for prop in ro.product.mod_device ro.miui.build.region ro.miui.region ro.com.miui.rsa.search; do
  /data/adb/ksu/bin/resetprop --delete "ro.appcompat_override.$prop"
done
am force-stop com.miui.home
am start -a android.intent.action.MAIN -c android.intent.category.HOME
