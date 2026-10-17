# 电脑源码工具 ZIP 0.6.0 发布说明

桌面工具 **0.6.0**，Git tag **`tool-v0.6.0`**，以 **Prerelease / 预览版** 发布：[tool-v0.6.0 发布页](https://github.com/skiyakubali0-cloud/XiaomiLocalSuite/releases/tag/tool-v0.6.0)。

附件名称 **`XiaomiLocalSuite-Tool-0.6.0.zip`**。这是源码、启动器和离线教程的便携工具包，需要 Python 3.11+ / Tk 8.6+、JDK 17+、Android SDK build-tools 36.0.0；编译统一插件还需 SDK platform 36。不是签名独立 DMG/EXE，也不是手机 Root 模块。依赖由用户离线准备或显式点击/执行下载动作；工具不自动安装 SDK 或接受许可。

## 内容与边界

- `launch.py` 和 `launchers/macOS.command`、`launchers/linux.sh`、`launchers/windows.cmd`。
- 默认「其他机型 · 从目标固件识别」的 GUI、本地环境检查、离线「使用教程」。
- 新增「小米15 Ultra · OS4.0.0.6 完整1.7适配」：原始材料检查、缺项清单、所选组件 parent 生成、自己的统一 APK 选择及「本地构建统一插件…」入口，见 [FULL_RECIPE.md](FULL_RECIPE.md)。
- 导入、显式解包、分析、勾选、检查和受限候选 ZIP 生成源码；CLI 为 `suite/multi-device/suite_builder.py`。
- `tools/recipe_materials.py check/build`、`tools/recipe_tools.py`、公开配方及生成器；保留 0.5 通用路线、历史 1.4 配方和 `tools/build_suite.py` 私有参考包开发路线。
- 软件来源信息 `SOURCE.json` 与逐文件 `SHA256SUMS`。

不附小米固件/APK/OEM 库或 DEX、第三方 AAR/JAR、SDK/NDK、Zygisk 头文件、签名密钥、用户数据、原始验证日志、设备截图、Git 历史或本地构建产物。完整 OTA 解包还需自行准备 `payload-dumper-go`、`fsck.erofs`。

## 0.6.0 精确原始材料路线

仅支持 `xuanyuan` EEA `OS4.0.0.6.XOAEUXM` / Android 17 / API37 / arm64-v8a，与同机型 CN `OS4.0.0.6.XOACNXM` 及配方锁定的额外 APK。无需私有参考 ZIP；没有材料回退路线，不宣称适配其他版本或机型。天气 23/27、SecurityCenter `13.6.5-261003.0.1` 等缺项须按精确路径、字节数、SHA256 补齐，详情及命令见 [FULL_RECIPE.md](FULL_RECIPE.md)。

11 个组件默认全不选；电话补齐商店，小爱补齐智能助理，钱包须单独手选而不随批量全选。215 项材料 lock 只按所选组件和依赖取用，旧统一 APK 由当前调用者构建替换。原生智能助理/天气补丁及预警 DEX 由用户原始材料和公开配方在本机生成，源码 ZIP 不附 OEM 代码或生成二进制。

统一插件必须为当前公开源码编译、自行签名的 APK，并成对提供 `.build-evidence.json`：核对完整源码文件集合、依赖与 APK 哈希，防止误用旧 code 17 APK；这些哈希记录不是 attestation。GUI 可选择自己的 APK，或使用自己的 keystore/alias、遮蔽输入的密码、已安装 SDK 和 AAR 目录本地构建。密码只传子进程环境，不写配置或命令行，不自动生成密钥。新签名不能覆盖旧签名，私钥需自行私下保存供未来升级。

「联网准备依赖」仅在用户显式点击后获取锁定的 3 份 libxposed AAR 与 4 份预警 DEX 工具 JAR。离线分别使用 `fetch_dependencies.py --local-dir` 与 `recipe_tools.py --local-dir`；预警 JAR 缓存在根目录 `build/recipe-tools/`。公开坐标、下载 URL 与哈希见 `suite/unified-api102/deps.lock.json`、`recipes/generated.json`，不据此作许可法律结论。

生成的 parent 保留 1.7 WebUI、逐项 Root 恢复与 API102 功能；电脑勾选仅决定内容，不触发组件自动安装。用户另行安装 parent（安装统一插件）、手动重启、在 LSPosed 启用并核对/授权作用域，再在手机预设检查并应用，按依赖分批和重启。只读能力 CSV 仅限制本包组件配置页的预设选择与安装，钱包仍默认不选；省略不卸载已有组件，不自动关闭其他页面的既有兼容开关或 hook，也不增加运行时门禁。如需停用，须单独关闭兼容或恢复组件。旧 parent 缺少能力命令时，组件配置页阻止应用并提示升级，不能直接把新 APK 配给旧私有 parent。

桌面端不生成钱包 reset 授权标记。钱包只有明确选中才带 payload；首次 EEA TSM 迁移另需手机端单任务确认，可能清除 TSM 数据及绑定密钥；已有精确 CN TSM 保留。全局 XMSF 不变。本轮没有安排手机操作。

默认流程不依赖旧 1.4；来源仅有 APK 时也必须提供目标固件目录，包含真实 build.prop 与原始 APK。通用路线仅接受目标已有、同签名、非 split 的普通系统 APK，结果保持候选状态。特权/新增权限/依赖、降级、签名差异及关键框架、电话、securitycenter、launcher、钱包/TSM/eSE/NFC、全局 XMSF 等不能据此移植。

**通用候选不自动包含统一 API102 插件、权限修复或已有 1.7 WebUI，不从任意材料复原全部 1.7 功能。** 电脑工具源码 ZIP 包含插件源码。多个 APK 放进同一候选就是同一恢复组，禁用并重启时一起恢复；需要独立恢复则每次单选一个 APK，使用不同配置标识分别生成。不能把既有 1.7 的逐项 WebUI 恢复描述成通用候选能力。

不使用 ADB，不自动安装、重启、清数据或生成钱包 reset。用户生成的含 OEM 材料 ZIP、通用候选 `.build.json`、本地统一 APK及构建证据、配置与诊断留本地，不上传仓库、Issues、PR 或 Releases。静态通过不充当手机功能证明。

## 源码打包与核对

维护者从仓库根目录运行。文档、GUI、启动器、打包器须先由主线审阅并包含在选定提交中；打包只读该 Git 提交的 blob，忽略工作区未提交修改与未跟踪文件。以下命令不提交、不推送、不创建 tag、不上传 release。

```sh
python3 tools/package_tool.py --version
python3 tools/package_tool.py --ref HEAD --output "/local/releases/XiaomiLocalSuite-Tool-0.6.0.zip"
python3 tools/package_tool.py --verify "/local/releases/XiaomiLocalSuite-Tool-0.6.0.zip"
```

`--ref` 默认 `HEAD`。0.6.0 版本常量、GUI 与文档须由主线一并完成，先确认 `--version` 为 0.6.0；发布时核对所选提交与 `tool-v0.6.0` 一致。输出须为新 ZIP，不覆盖已有文件。允许仓库外路径，仓库内仅限被忽略的 `releases/`。

ZIP 顶层为 `XiaomiLocalSuite-Tool-0.6.0/`。`SOURCE.json` 仅含软件提交 `softwarecommit` 与构建版本 `buildversion`；`SHA256SUMS` 以该顶层为基准，覆盖除自身外的全部成员。离线 `--verify` 不需要 Git，验证清单与文件一致性；这不能独立证明来源可信，仍须从指定项目发布页获取并核对版本。

打包使用允许的 Git 文本文件集合，拒绝 symlink、危险路径、私有文件和禁发材料，并调用公开树检查规则。打源码包无需安装构建依赖；打包成功不等于 GUI/SDK 环境就绪。

## 验证与发布说明

原始材料 214/214、完整 1.7 ZIP、实际 macOS GUI 部分包、主机回归及复用边界见 [FULL_RECIPE_VALIDATION.md](FULL_RECIPE_VALIDATION.md)。Linux CI 以发布 tag 对应提交的 Actions 结果为准；0.5 的历史记录保留在 [TOOL_VALIDATION.md](TOOL_VALIDATION.md)。

当前公开构建没有新一轮手机安装或功能验收，不能继承私有 1.7 的真机结论。原生 Windows 完整流程未验证，建议 WSL2 配合 GUI 和 Linux 依赖，见 [USER_GUIDE.md](USER_GUIDE.md)。
