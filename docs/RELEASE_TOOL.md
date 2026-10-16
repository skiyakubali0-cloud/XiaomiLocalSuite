# 电脑源码工具 ZIP 0.5.0 发布说明

首次公开桌面工具版本 **0.5.0**，Git tag **`tool-v0.5.0`**，GitHub Release 标为 **Prerelease / 预览版**。使用 [tool-v0.5.0 发布页](https://github.com/skiyakubali0-cloud/XiaomiLocalSuite/releases/tag/tool-v0.5.0)，不使用尚无稳定版含义的 `releases/latest`。

附件名称 **`XiaomiLocalSuite-Tool-0.5.0.zip`**。这是源码、启动器和离线教程的便携工具包，需要 Python 3.11+ / Tk 8.6+、JDK 17+、Android SDK build-tools 36.0.0；不是签名独立 DMG/EXE，也不是手机 Root 模块。依赖由用户另行准备，工具不自动下载或接受许可。

## 内容与边界

- `launch.py` 和 `launchers/macOS.command`、`launchers/linux.sh`、`launchers/windows.cmd`。
- 默认「其他机型 · 从目标固件识别」的 GUI、本地环境检查、离线「使用教程」。
- 导入、显式解包、分析、勾选、检查和受限候选 ZIP 生成源码；CLI 为 `suite/multi-device/suite_builder.py`。
- 历史 1.4 配方、可选精确 1.7 重建的公开源码/说明；私有输入不附送。
- 软件来源信息 `SOURCE.json` 与逐文件 `SHA256SUMS`。

不附小米固件/APK/OEM 库或 DEX、第三方 AAR/JAR、SDK/NDK、Zygisk 头文件、签名密钥、用户数据、原始验证日志、设备截图、Git 历史或本地构建产物。完整 OTA 解包还需自行准备 `payload-dumper-go`、`fsck.erofs`。

默认流程不依赖旧 1.4；来源仅有 APK 时也必须提供目标固件目录，包含真实 build.prop 与原始 APK。通用路线仅接受目标已有、同签名、非 split 的普通系统 APK，结果保持候选状态。特权/新增权限/依赖、降级、签名差异及关键框架、电话、securitycenter、launcher、钱包/TSM/eSE/NFC、全局 XMSF 等不能据此移植。

**通用候选不自动包含统一 API102 插件、权限修复或已有 1.7 WebUI，不从任意材料复原全部 1.7 功能。** 电脑工具源码 ZIP 包含插件源码。多个 APK 放进同一候选就是同一恢复组，禁用并重启时一起恢复；需要独立恢复则每次单选一个 APK，使用不同配置标识分别生成。不能把既有 1.7 的逐项 WebUI 恢复描述成通用候选能力。

不使用 ADB，不自动安装、重启、清数据或生成钱包 reset。用户生成的含 OEM 材料 ZIP、`.build.json`、配置与诊断留本地，不上传仓库、Issues、PR 或 Releases。静态通过不充当手机功能证明。

## 源码打包与核对

维护者从仓库根目录运行。文档、GUI、启动器、打包器须先由主线审阅并包含在选定提交中；打包只读该 Git 提交的 blob，忽略工作区未提交修改与未跟踪文件。以下命令不提交、不推送、不创建 tag、不上传 release。

```sh
python3 tools/package_tool.py --version
python3 tools/package_tool.py --ref HEAD --output "/local/releases/XiaomiLocalSuite-Tool-0.5.0.zip"
python3 tools/package_tool.py --verify "/local/releases/XiaomiLocalSuite-Tool-0.5.0.zip"
```

`--ref` 默认 `HEAD`。发布时核对所选提交与 `tool-v0.5.0` 一致；输出须为新 ZIP，不覆盖已有文件。允许仓库外路径，仓库内仅限被忽略的 `releases/`。

ZIP 顶层为 `XiaomiLocalSuite-Tool-0.5.0/`。`SOURCE.json` 仅含软件提交 `softwarecommit` 与构建版本 `buildversion`；`SHA256SUMS` 以该顶层为基准，覆盖除自身外的全部成员。离线 `--verify` 不需要 Git，验证清单与文件一致性；这不能独立证明来源可信，仍须从指定项目发布页获取并核对版本。

打包使用允许的 Git 文本文件集合，拒绝 symlink、危险路径、私有文件和禁发材料，并调用公开树检查规则。打源码包无需安装构建依赖；打包成功不等于 GUI/SDK 环境就绪。

## 验证与发布说明

本版范围为 macOS 实际 GUI 与 Linux CI 验证；不宣称原生 Windows 完整流程通过，也不把 CI 当作所有 Linux 桌面实测。Windows 原生诊断明确不就绪，完整流程建议 WSL2 配合 GUI 和 Linux 依赖，见 [USER_GUIDE.md](USER_GUIDE.md)。

环境诊断、主机回归、工具 ZIP 核对、候选生成、手机安装与真实功能分别记录。尚未完成的回归/远端 CI 不提前写成通过；0.5 最终证据以 [TOOL_VALIDATION.md](TOOL_VALIDATION.md) 与 release 说明为准。候选生成不能证明新机型兼容、云端功能、通知送达、支付、门卡或统一插件可用。

用户另行评估候选仍需 KernelSU、已生效 OverlayFS 1.3.1 和精确 ROM/APK guards。OTA 前禁用候选并重启，不通过清数据、改 SHA 或签名绕过。桌面工具 **0.5.0** 与手机套件 **1.7** 是独立版本体系，旧 1.7 重建仍需私有材料。

权利边界见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)，隐私边界见 [PRIVACY.md](PRIVACY.md)。本说明不作法律结论。
