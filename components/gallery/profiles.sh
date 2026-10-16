#!/system/bin/sh
STATE=/data/adb/xuanyuan-os4-gallery-state
K=/data/adb/ksu/bin/ksud
PACKAGES='com.miui.gallery com.hyper.gallery.plugin com.miui.mediaeditor com.miui.extraphoto'
mkdir -p "$STATE/profiles"; chmod 700 "$STATE" "$STATE/profiles"
case "$1" in
apply)
 for pkg in $PACKAGES; do
  "$K" profile get "$pkg" > "$STATE/profiles/current.json" || exit 1
  grep -q '"allow_su": false' "$STATE/profiles/current.json" || exit 1
  uid=$(sed -n 's/.*"uid": \([0-9]*\).*/\1/p' "$STATE/profiles/current.json")
  [ -n "$uid" ] || exit 1
  base="$STATE/profiles/$pkg.$uid"
  [ -f "$base.before" ] || cp "$STATE/profiles/current.json" "$base.before"
  sed -e 's/"use_default": true/"use_default": false/' -e 's/"umount_modules": true/"umount_modules": false/' "$STATE/profiles/current.json" > "$STATE/profiles/apply.json"
  "$K" profile set "$STATE/profiles/apply.json" || exit 1
  "$K" profile get "$pkg" > "$base.applied" || exit 1
 done
 ;;
restore)
 for pkg in $PACKAGES; do
  "$K" profile get "$pkg" > "$STATE/profiles/current.json" || continue
  uid=$(sed -n 's/.*"uid": \([0-9]*\).*/\1/p' "$STATE/profiles/current.json")
  base="$STATE/profiles/$pkg.$uid"
  [ -f "$base.before" ] && [ -f "$base.applied" ] || continue
  # Preserve later user profile changes; restore only the exact profile we applied.
  if cmp -s "$STATE/profiles/current.json" "$base.applied"; then
   "$K" profile set "$base.before" || continue
   rm "$base.applied"
  fi
 done
 ;;
*) exit 2 ;;
esac
