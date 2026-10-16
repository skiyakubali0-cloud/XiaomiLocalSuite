#!/system/bin/sh
[ "$KSU" = true ] || abort "KernelSU required"
[ "$(getprop ro.product.device)" = xuanyuan ] || abort "xuanyuan only"
[ "$(getprop ro.build.version.sdk)" = 37 ] || abort "Android 17 only"
[ "$(getprop ro.build.version.incremental)" = OS4.0.0.6.XOAEUXM ] || abort "This release requires OS4.0.0.6.XOAEUXM"
[ -x /data/adb/metamodule/meta-overlayfs ] || abort "Activate OverlayFS MetaModule first"
(cd "$MODPATH" && sha256sum -c checksums.sha256) || abort "Payload hash mismatch"
set_perm_recursive "$MODPATH" 0 0 0755 0644
for script in "$MODPATH"/*.sh; do set_perm "$script" 0 0 0755; done
ui_print "- Original xuanyuan CN Android 17 APK; reboot required"

case "$(sha256sum /system_ext/lib64/libhyper_os_core_system_private.dylib.so | awk '{print $1}')" in
  a7de453780f33d2dec0cfca8832d218ee798f3208df06af36744f416313afa1f|5d7b4fd34dd7878d1d4d988afcc456672ca3eb7df9345ce9767783810ac2f182|71fa522160812cb9bf5f5f4f0f0227ed9acb227c9102521a65c0c6e3d172212f) ;;
  *) abort "Rust runtime differs from tested build" ;;
esac
[ "$(sha256sum /apex/com.android.runtime/lib64/bionic/libc.so | awk '{print $1}')" = f6c25ea4d8b9a4dc76d6964f78edc9831cd676837a8f91d93a1cb4e87808e32e ] || abort "Bionic runtime differs from tested build"
HOME_VERSION=$(dumpsys package com.miui.home | sed -n 's/^    versionCode=\([0-9]*\).*/\1/p' | head -n 1)
[ "$HOME_VERSION" = 801027654 ] || abort "This adapter requires launcher 801027654"
# MetaModule 1.3.1 merges payloads. Remove only our known retired CN test APK.
RETIRED=/data/adb/metamodule/mnt/xuanyuan-os4-assistant/product/priv-app/MiuiHome/MiuiHome.apk
if [ -f "$RETIRED" ]; then
  [ "$(sha256sum "$RETIRED" | awk '{print $1}')" = b5e9aaa1ef1f052e3b9e31c685ff201436700728d5fc52d9d56d0c9326fdfa9c ] || abort "Unexpected retired launcher payload"
  rm -f "$RETIRED" || abort "Cannot remove retired test payload"
  rmdir "${RETIRED%/*}" 2>/dev/null
fi
OLD=/data/adb/modules/xuanyuan-os4-assistant
if [ -f "$OLD/control.sh" ] && [ ! -e "$OLD/use_china" ]; then rm -f "$MODPATH/use_china"; fi
