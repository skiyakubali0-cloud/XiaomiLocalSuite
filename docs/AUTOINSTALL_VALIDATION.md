# 0.7.0 自动部署验证与复用记录

日期：2026-10-17。工具 tag `tool-v0.7.0`；目标为小米15 Ultra `xuanyuan`、EEA `OS4.0.0.6.XOAEUXM`、Android 17/API37/arm64-v8a。使用同机型 CN `OS4.0.0.6.XOACNXM` 和锁定的额外 APK，不需要私有参考 ZIP。

## 实现范围

用户另行刷入生成的 parent ZIP 时，同步部署电脑所选组件及依赖。电话若等待商店完成一次启动，则先部署商店和其他可用项，用户手动重启后仅续装这次计划中的电话。完成、失败或取消后不反复自动安装，不自动重启。

续装核对包指纹、不同 boot、上一任务成功和当前任务记录；拿到锁后再次核对，发现手动 controller 任务已改变记录就取消。自动重新启用已停用组件也在同一 worker 锁内完成，避免覆盖随后发生的手动恢复。已由本次 parent 完成的小爱配对更新，会核对 payload、版本及 CLI 哈希并避免重复安装；错误 staging 不会回退为匹配的 live 文件。

Root 组件部署保留原有应用数据、子组件恢复入口及 guard。取消或失败不表示已完成步骤全部回滚；钱包共享 UID/密钥迁移也不属于普通无损恢复。不修改 compat 偏好、LSPosed 授权或全局 XMSF。

钱包只在单独勾选时打包。首次 EEA→CN TSM 迁移不进入自动批次，须在手机组件配置中作单任务明确确认，确认后才允许重置旧 TSM 数据及关联密钥。已有精确 CN TSM 可按原有 guard 自动安装，不重复清除；未知身份停止。

## 实际材料与生成验证

- 当前公开源码对应的统一 API102 APK及配套构建证据校验通过；本次未更改 Java/manifest 或签名构建代码。
- 从现有原始固件材料及官方签名 APK 重新解析 **214/214 项材料**，派生补丁匹配 lock；没有读取私有参考 ZIP，本轮没有重新解包全量 OTA。
- 最终全 11 组件包生成成功：**1,101,469,378 字节**。结果含 `auto_install_components=true`、`install_policy=during-flash-with-phone-continuation` 和 `wallet_first_migration=phone-confirmation-only`。
- 独立核对全部 214 项材料、父包和 8 个子包的校验清单、catalog 摘要、52 份 shell 语法，以及归档中的最终 helper/worker 逻辑。原有 controller 恢复代码保持原字节。
- 安装包未包含 reset 授权、运行时 pending/result/ok 文件；这些记录只能在执行相应阶段时生成。
- 实际 macOS Tk 控件完成分析、勾选商店/智能助理、检查及生成，最终部分包 **68,561,763 字节**；固定计划与选择一致。

两个含 OEM 材料的最终 ZIP 和本地报告留在私人工作目录，不随公开 Release 分发。

## 主机执行与回归

环境：macOS、Python 3.13.13、Tk 9.1、JDK17、Android SDK platform36/build-tools36.0.0。

| 检查组 | 结果 |
| --- | --- |
| 工具、原料、打包及自动部署 | 108 项通过，其中新增 22 项执行真实 helper/control/worker 脚本 |
| 多机型/GUI | 157 项，2 项历史私有材料集成明确跳过，其余通过 |
| 钱包生命周期 | 24 项通过 |
| 统一 API102 插件 | 91 项通过 |
| Java host 断言 | 784 与 66,588 条通过 |

自动部署测试使用合成 payload、模拟 Android 命令及显式模拟 boot。覆盖全 11 项、CN/EEA 钱包、不探测未选钱包、商店启动门禁、生成 service 仅续装一次、错误 ROM/哈希/锁/pending、worker/tee 失败、手动任务竞态、配对小爱防双装、锁内 enable 及其失败、普通安装和独立恢复。合成应用数据、钱包数据、偏好与框架配置哨兵保持不变。

这不是设备证明：native KernelSU 嵌套安装、OverlayFS、Binder、真实开机/service 和实际应用数据保留均未在本轮手机验证；没有手机安装、重启、电话、报警、推送、支付或卡片操作。

源码工具包从提交的 Git blobs 构建，附 SOURCE.json 和 SHA256SUMS。离线包核对、公开下载摘要与最终提交的 Linux CI 结果由对应 Release 提供；旧提交或本机通过不能代替最终 CI。原生 Windows 完整流程未验证。

## 部署结果与恢复

以下 M 是 parent 目录，正常安装后为 `/data/adb/modules/xuanyuan-os4-suite`。

| 文件 | 用途 |
| --- | --- |
| `M/install-selected.result` | key=value，记录 state、selected、wallet、job |
| `M/install-selected.pending` | 恰好四行：包指纹、原 boot、上一 job、phone；只供这一次电话续装 |
| `M/install-selected.ok` | 所选部署完成且没有首次钱包待确认时生成，不代表兼容/业务功能已验收 |

状态为 `reboot-required`、`wallet-confirmation-required`、`deployed`、`failed` 或 `cancelled`。job 非空时查看该目录的 log/state/message；无 job 时查看 result 和刷入输出。

helper 失败会清除 pending/ok 并记录 failed。父套件保留用于查看日志和逐项恢复，因此 **Root 安装器显示父包安装成功，不等于所有组件部署成功**。先核对结果，再按原有恢复入口处理已完成项。

service 有 pending 时最多等启动完成 120 秒，再按 guard 续装；没有 pending 时只运行原有 reconcile，不创建新安装计划。失败后没有自动重试队列。用户须在 LSPosed 启用统一插件、核对作用域和所需兼容开关，并手动重启使挂载生效。电话跨启动续装后还须再手动重启一次，首次从零部署可能需要两次重启。首次钱包迁移另行确认。

完整步骤见 [FULL_RECIPE.md](FULL_RECIPE.md)。公开工具不附 OEM APK/库/DEX、固件、第三方 AAR/JAR、SDK、私钥或用户数据。
