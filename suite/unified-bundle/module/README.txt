小米本地化统一套件1.4 · 按需一键配置

仅xuanyuan / EEA OS4.0.0.6.XOAEUXM / Android17 API37 / 单用户0。
先准备KernelSU、OverlayFS MetaModule、Zygisk Next与LSPosed/API102，再安装父ZIP并重启。
统一APK1.2/code13；唯一入口local.xuanyuan.unified.UnifiedModule，包名local.xuanyuan.mipushcompat。
打开WebUI或统一设置的“一键配置当前方案”，按需勾选11项组件和5项兼容，再点击应用。
首次默认当前全选配置，之后保留用户选择；必要依赖自动补齐，安装/授权会话冻结选择。
组件取消只跳过安装，不卸载；兼容取消会在应用后关闭该开关。已有额外作用域与MiPush个人选择保留。
只申请当前所需缺失作用域，经正常API102批准和实际回读后保存；不写LSPosed数据库，不绕过授权。
必要重启由用户明确点击；已匹配时不重复安装或重启；保留原逐项恢复入口。
钱包首次迁移未完成时单独提示，不自动reset、不清数据、不改TSM/eSE/Keystore或支付卡片。
不改全局XMSF，不自动接受协议、改默认项或启用录音/报警；真实钱包通知仍待验证。
小爱配套脚本1.7.3/code2026101504对应新版APK；保留AI管理时选择小爱升级。
完整流程：guides/统一套件1.4说明.txt；来源/哈希：webroot/catalog.json、checksums.sha256。
