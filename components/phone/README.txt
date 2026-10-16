统一 API102 内部组件：phone 1.8.1，versionCode 2026101502。
仅 xuanyuan / EEA OS4.0.0.6.XOAEUXM / Android17 API37 / 用户0。
原始小米签名 APK、DEX、assets 与 native 文件逐字节保留。
外部前提：KernelSU、Zygisk、支持 API102 的 LSPosed/Vector、OverlayFS MetaModule。
请通过父套件安装共享 local.xuanyuan.mipushcompat v13；本子包不携带或重装旧插件 APK。
统一设置中的五项兼容默认关闭。先在父WebUI暂存现代Root子模块，再选择旧插件迁移，重启应用更新后配置唯一LSP入口/开关/作用域并再重启。
安装不写 LSP 数据库，不改兼容偏好、不自动迁移、接受协议或开启录音/报警。
电话需先启用商店并重启；保留默认电话/短信记录、黄页与录音监控精确恢复脚本。
挂载标记：/product/etc/xuanyuan-suite-phone.enabled。恢复后重启并关闭统一设置中的电话兼容。
任何单项恢复均保留共享 APK、其他组件、原有应用数据和个人备份。
主机转换测试不等于实机功能验证；真实通话、录音、灾害推送和报警行为仍须单独验证。
完整说明见父套件 guides/统一套件1.4说明.txt。
