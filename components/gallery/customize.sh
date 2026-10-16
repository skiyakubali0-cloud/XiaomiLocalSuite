#!/system/bin/sh
[ "$KSU" = true ] || abort 'KernelSU required'
[ "$(getprop ro.product.device)" = xuanyuan ] || abort 'xuanyuan only'
[ "$(getprop ro.build.version.sdk)" = 37 ] || abort 'Android17 only'
[ "$(getprop ro.build.version.incremental)" = OS4.0.0.6.XOAEUXM ] || abort 'Exact EEA OS4.0.0.6 required'
[ -x /data/adb/metamodule/meta-overlayfs ] || abort 'Activate meta-overlayfs first'
(cd "$MODPATH" && sha256sum -c checksums.sha256) || abort 'Payload mismatch'
P=$(pm path com.miui.gallery)
case "$P" in
 *'
'*) abort 'com.miui.gallery multiple APK paths; review before install' ;;
 'package:/product/priv-app/MIUIGalleryGlobal/MIUIGalleryGlobal.apk') ;;
 package:/data/app/*/com.miui.gallery-*/base.apk)
  U=${P#package:}
  UH=$(sha256sum "$U" | cut -d' ' -f1)
  [ "$UH" = '6a9c9677a6a6ef398c3d60dad58c71942adab010b8e4e7727b2c028063c3fd9d' ] || abort 'com.miui.gallery updated APK mismatch'
  ;;
 *) abort 'com.miui.gallery has another update/path; review before install' ;;
esac
H=$(sha256sum /product/priv-app/MIUIGalleryGlobal/MIUIGalleryGlobal.apk | cut -d' ' -f1)
case "$H" in c25c993cc1462a955b145035ee071d98781ba51370bad232a78eb567eb84cfbc|be6bb05752cf667430c9359cd46fa8f4ed3552ecbe2e90a7b6279eaeb471f4a2) ;; *) abort 'com.miui.gallery unknown APK' ;; esac
P=$(pm path com.hyper.gallery.plugin)
[ "$P" = 'package:/product/app/HyperGalleryPluginGlobal/HyperGalleryPluginGlobal.apk' ] || abort 'com.hyper.gallery.plugin has another update/path; review before install'
H=$(sha256sum /product/app/HyperGalleryPluginGlobal/HyperGalleryPluginGlobal.apk | cut -d' ' -f1)
case "$H" in d0a6af98b4910113fb4ecf62fff349881ec1adde8291682fe500bde59eadf8d1|f763216706094ca04cf2c4e67600595bbfa55f0533b8468a7c36ca2463bf9497) ;; *) abort 'com.hyper.gallery.plugin unknown APK' ;; esac
P=$(pm path com.miui.mediaeditor)
case "$P" in
 *'
'*) abort 'com.miui.mediaeditor multiple APK paths; review before install' ;;
 'package:/product/data-app/MIMediaEditorGlobal/MIMediaEditorGlobal.apk') ;;
 package:/data/app/*/com.miui.mediaeditor-*/base.apk)
  U=${P#package:}
  UH=$(sha256sum "$U" | cut -d' ' -f1)
  [ "$UH" = 'e7c37c8ee2e10e8e45b60ad3ff293ad8a0b1c702f9e79aaa8df97ecfbcf4f699' ] || abort 'com.miui.mediaeditor updated APK mismatch'
  ;;
 *) abort 'com.miui.mediaeditor has another update/path; review before install' ;;
esac
H=$(sha256sum /product/data-app/MIMediaEditorGlobal/MIMediaEditorGlobal.apk | cut -d' ' -f1)
case "$H" in 52343b5d46f227100fc0b75ee6eed633a431db51f95eb3c2f1ba44ad40aacefc|365954e0e94263b7372fa5e6f4d244690b5edd9607b5642a1488a622732f7756) ;; *) abort 'com.miui.mediaeditor unknown APK' ;; esac
P=$(pm path com.miui.extraphoto)
[ "$P" = 'package:/product/priv-app/MiuiExtraPhoto/MiuiExtraPhoto.apk' ] || abort 'com.miui.extraphoto has another update/path; review before install'
H=$(sha256sum /product/priv-app/MiuiExtraPhoto/MiuiExtraPhoto.apk | cut -d' ' -f1)
case "$H" in ca7794bb50c7ab612aab9494d0fc8fe887bfbd5a28ba3ffd8fecaba7a218c7c4|b6149345f1aa4f3b84d84152b186f5c60bc6bc4c95957ac3cc232fb047722756) ;; *) abort 'com.miui.extraphoto unknown APK' ;; esac
STATE=/data/adb/xuanyuan-os4-gallery-state
mkdir -p "$STATE"; chmod 700 "$STATE"
for p in com.miui.gallery com.hyper.gallery.plugin com.miui.mediaeditor com.miui.extraphoto; do am force-stop "$p"; done
BACKUP="$STATE/backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"; chmod 700 "$BACKUP"
for area in user user_de; do
 (cd /data/$area/0 && tar -czf "$BACKUP/$area.tar.gz" com.miui.gallery com.hyper.gallery.plugin com.miui.mediaeditor com.miui.extraphoto) || abort 'Data backup failed; installation stopped'
 gzip -t "$BACKUP/$area.tar.gz" || abort 'Backup validation failed'
done
set_perm_recursive "$MODPATH" 0 0 0755 0644
for p in "$MODPATH"/*.sh; do set_perm "$p" 0 0 0755; done
ui_print 'Private app data backup saved under /data/adb/xuanyuan-os4-gallery-state'
ui_print '停用/移除模块并重启仅撤销模块挂载；保留现有 /data/app 相册及编辑器更新，不等于恢复完整国际版程序。不卸载更新、不覆盖数据库或照片。'
ui_print 'Reboot required. AI agreements/models/account remain user choices.'

sh "$MODPATH/profiles.sh" apply || abort 'KSU per-app profile setup failed'
cp "$MODPATH/profiles.sh" "$STATE/profiles.sh"
mkdir -p /data/adb/service.d
cp "$MODPATH/profile-watch.sh" /data/adb/service.d/xuanyuan-gallery-profile-watch.sh
chmod 700 /data/adb/service.d/xuanyuan-gallery-profile-watch.sh
