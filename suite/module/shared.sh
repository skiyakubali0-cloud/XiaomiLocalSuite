# Shared APK identity is generated from the reviewed build input.
UNIFIED_PKG=local.xuanyuan.mipushcompat
UNIFIED_SHA=02b4d7bc35ccfa6ec9d3e7ce82171b1a96bf81ba1abb3f1dcff70170c960679f
UNIFIED_PREVIOUS_SHA=221d9cf4691e12382d2a5eab8fabc4470ff5f8a635a75650fca9a6129397c59c
shared_check() {
 UNIFIED_LIVE_SHA=''
 UNIFIED_PATHS=$(pm path --user 0 "$UNIFIED_PKG" 2>/dev/null)
 if [ -z "$UNIFIED_PATHS" ]; then
  UNIFIED_LIST=$(pm list packages -u --user 0 "$UNIFIED_PKG") || return 1
  [ -z "$UNIFIED_LIST" ] || return 1
  return 0
 fi
 case "$UNIFIED_PATHS" in package:*) ;; *) return 1;; esac
 UNIFIED_PATH=${UNIFIED_PATHS#package:}
 # A split installation produces multiple lines and cannot name one regular file.
 [ -f "$UNIFIED_PATH" ] || return 1
 UNIFIED_LIVE_SHA=$(sha256sum "$UNIFIED_PATH" | cut -d' ' -f1)
 [ "$UNIFIED_LIVE_SHA" = "$UNIFIED_SHA" ] || [ "$UNIFIED_LIVE_SHA" = "f51432bb665ba68c1e5232170baea2d8e9d320e83804000e54b13ebdba4c5858" ] || [ "$UNIFIED_LIVE_SHA" = "660cb1245fa9dac261d64570fba557ba44c166382960799b27bc130b59e14d25" ] || [ "$UNIFIED_LIVE_SHA" = "9846373803f3e440372f014cb7bfa499636d99968bed278911ee75116c4d537b" ] || [ "$UNIFIED_LIVE_SHA" = "$UNIFIED_PREVIOUS_SHA" ] || [ "$UNIFIED_LIVE_SHA" = "fe2cc510d76aeca054582d20f092833a336e13b39686fb1d49f5a20a3a5688d7" ] || [ "$UNIFIED_LIVE_SHA" = "e49470e7cf7a08f3d9bc1ae2ebd5ba170ed3fcf0549fe9d927da2b9bf166d973" ] || [ "$UNIFIED_LIVE_SHA" = "cf8e6513f013351ef4d88bdd00f1a490da0bcba67b8a55263bcd57f8350140ac" ] || [ "$UNIFIED_LIVE_SHA" = "346ba49559a7ef1986d479a2f7acff5359c66c8ed4df099c90fa4885ba27e6ca" ]
}
shared_install() {
 [ "$(sha256sum "$M/payload/unified.apk" | cut -d' ' -f1)" = "$UNIFIED_SHA" ] || return 1
 shared_check || return 1
 [ "$UNIFIED_LIVE_SHA" != "$UNIFIED_SHA" ] || return 0
 cat "$M/payload/unified.apk" | pm install -r --user 0 -S "$(stat -c %s "$M/payload/unified.apk")" || return 1
 shared_check && [ "$UNIFIED_LIVE_SHA" = "$UNIFIED_SHA" ]
}
