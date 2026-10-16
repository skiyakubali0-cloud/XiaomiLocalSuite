#!/system/bin/sh
/data/adb/ksu/bin/ksud module disable xuanyuan-os4-disaster || exit 1
echo 'Module disabled. Reboot to restore the original EEA APK. No data has been cleared.'
echo 'If a Market /data/app update was installed later, disabling the overlay does not remove it.'
