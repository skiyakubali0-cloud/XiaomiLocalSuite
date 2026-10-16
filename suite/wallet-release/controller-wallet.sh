wallet_check() { sh "$M/wallet.sh" mode; }
wallet_install() (
 W_MARK=/data/adb/xuanyuan-os4-wallet-reset-authorized
 [ ! -e "$W_MARK" ] || fail '存在旧TSM授权，请先核对，未执行更改'
 trap 'rm -f "$W_MARK"' EXIT
 W_MODE=$(wallet_check) || fail '钱包/TSM身份检查失败'
 if [ "$W_MODE" = eea ]; then
  [ "${WALLET_MIGRATION:-0}" = 1 ] || fail '请从统一插件确认首次TSM迁移'
  printf 'RESET_XIAOMI_TSM_ONLY:%s:c31f66629723c3c60a8d0862e68f2777b0187afe7271bbec2df7468bd5d350bb\n' "$(boot)" > "$W_MARK"
  chmod 600 "$W_MARK"
 fi
 "$K" module install "$M/payload/$FILE" || fail '钱包模块安装失败；已清理一次授权，请保留日志'
)
