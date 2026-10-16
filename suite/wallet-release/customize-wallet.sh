#!/system/bin/sh
[ "$KSU" = true ] || abort 'KernelSU required'
[ -x /data/adb/metamodule/meta-overlayfs ] || abort 'Activate OverlayFS MetaModule first'
(cd "$MODPATH" && sha256sum -c checksums.sha256) || abort 'Wallet payload checksum mismatch'
sh "$MODPATH/wallet.sh" migrate || abort 'Wallet preflight/migration failed; stopped'
set_perm_recursive "$MODPATH" 0 0 0755 0644
for script in "$MODPATH"/*.sh; do set_perm "$script" 0 0 0755; done
ui_print 'Wallet staged. Reboot activates CN TSM and registers the reviewed wallet APK. Payment default preserved.'
