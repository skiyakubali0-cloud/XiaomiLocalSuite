# XiaomiLocalSuite

0.7.1 新增：[原电话与短信 · 禁用 / 恢复](docs/STOCK_APPS.md)。需用当前源码重建统一 API102 APK 和配套 parent ZIP，沿用同一长期签名密钥；旧电话子模块即使版本号相同，也须重新安装并手动重启。

面向小米 HyperOS 的本地化适配工具源码：一个 modern API 102 LSPosed 插件、独立 Root 组件、按需勾选安装入口，以及电脑端 APK/固件兼容检查工具。

**电脑工具 0.7.1 预览版**：[下载 XiaomiLocalSuite-Tool-0.7.1.zip](https://github.com/skiyakubali0-cloud/XiaomiLocalSuite/releases/tag/tool-v0.7.1) · [中文使用教程](docs/USER_GUIDE.md) · [完整 1.7 原始材料路线](docs/FULL_RECIPE.md) · [发布说明](docs/RELEASE_TOOL.md)。需自备 Python/Tk、Java 和 SDK，不是独立 DMG/EXE 或手机模块。解压后运行 `python3 launch.py`，默认通用入口保留，无须旧 1.4。

默认 GUI 只生成目标已有、同签名、非 split 的普通系统 APK 受限候选包；不含统一 API102 插件、权限修复或 1.7 WebUI，不能从任意固件复原全部 1.7 功能。同一候选内多选 APK 作为一组恢复；静态通过不等于手机功能验证。含原厂材料的结果仅本地使用，不公开发布。Windows 原生完整流程未就绪，优先使用具备 GUI 的 WSL2。

0.7.1 的「小米15 Ultra · OS4.0.0.6 完整1.7适配」使用精确 EEA `OS4.0.0.6.XOAEUXM`、同机型 CN `OS4.0.0.6.XOACNXM` 及锁定额外 APK，无需私有参考 ZIP，生成保留 1.7 WebUI、逐项 Root 恢复与 API102 的 parent。11 行默认全不选，电话依赖商店、小爱依赖智能助理，钱包只能单独手选。须提供当前公开源码自行签名的统一 APK 与配套 `.build-evidence.json`；缺项报告路径、大小和 SHA。新版部署方案为用户另行刷入生成 ZIP 时同步安装电脑勾选且满足 guard 的组件；电话若需商店先重启，则先装商店及其他可用项，用户手动重启后仅对该次固定计划自动续装电话。首次 EEA 钱包 TSM 迁移仍须手机明确确认，不随刷入直接重置。步骤见[完整教程](docs/FULL_RECIPE.md)，实际材料生成、主机执行及未验证范围见[验证记录](docs/AUTOINSTALL_VALIDATION.md)。

当前参考实现为小米15 Ultra `xuanyuan`、EEA `OS4.0.0.6.XOAEUXM`、Android17/API37。它不是通用跨机型一键移植工具，未知机型、ROM、APK 或共享 UID 应停止安装并重新审查。

## 仓库包含什么

- `suite/unified-api102/`：统一插件源码、依赖哈希、构建入口与主机回归。modern API102，唯一入口，默认作用域为空。
- `suite/module/`：1.7父套件控制器、勾选计划、WebUI、旧插件迁移与钱包协作逻辑的文本模板。
- `native/assistant/`：自主编写的桌面路由原生代码参考；不附NDK、Zygisk头文件或原厂库。
- `components/`：商店、智能助理、小爱、电话/短信、相册、天气、预警和钱包组件的脚本及配置。
- `suite/multi-device/`：本地 GUI、固件/APK读取与兼容检查；保留通用候选、历史 1.4 和精确 1.7 原始材料入口，原始材料模式保留 0.7.0 刷入部署方案，0.7.1 增加原电话/短信管理。
- `materials.lock.json`：私有二进制材料的相对路径、字节数及精确SHA256；不包含这些材料本身。
- `tools/build_suite.py`：使用本地精确参考包和自行签名统一APK重建当前套件。
- `tools/recipe_materials.py`、`recipes/`：精确 1.7 原始材料检查/构建及公开配方；只解析所选组件与依赖，调用者提供固件/APK及当前统一插件。
- 其余历史packager及fixture保留作回归参考；私有参考包重建仍是独立开发路线，不能替代原始材料模式的输入及构建证据。

## 不包含什么

不分发小米原厂APK、固件、OEM库/DEX、完整安装ZIP、用户数据、截图、设备序列号、日志、卡片凭据、令牌、数据库或签名私钥。使用者需自行合法取得匹配材料；请勿提交到Issues、PR、GitHub Releases或仓库历史。

## 开发与构建

要求Python3.11+、JDK17+；插件构建需要Android SDK platform36、build-tools36.0.0。目标运行ROM仍是Android17/API37，编译SDK36不是目标ROM声明。

开发回归请先用 Git 克隆仓库；Release 解压目录不含 Git 元数据。运行图形工具和离线 ZIP 校验不需要 Git。

```sh
export ANDROID_SDK_ROOT="$HOME/Android/Sdk"
python3 suite/unified-api102/fetch_dependencies.py --download
python3 tools/check_public_tree.py
python3 tools/run_tests.py
```

插件签名方式见[suite/unified-api102/README.md](suite/unified-api102/README.md)，公开原始材料路线见[docs/FULL_RECIPE.md](docs/FULL_RECIPE.md)，保留的私有参考包开发路线见[docs/BUILD_SUITE.md](docs/BUILD_SUITE.md)。新插件仍为 versionCode 17，但新手机预设依赖支持 `preset.sh capabilities` 的新 parent；旧 parent 缺少能力命令会提示升级并阻止应用。本地构建产物不自动上传或安装手机。

**自行签名APK无法直接覆盖此前私人签名的同包名插件。** 仓库不提供旧私钥，也不承诺重现旧APK哈希。签名、APK哈希与CLI校验必须成套生成；原已部署手机的升级需要原签名和重新验证，不要为绕过签名直接卸载旧插件或清数据。

## 1.7 手机端安装与参考验证边界

以下为 0.7.1 精确原始材料路线沿用的部署流程，不是默认通用候选的安装承诺。电脑端只生成文件；用户另行刷入 parent 时，按电脑固定选择同步部署满足 guard 的组件。通用候选的 KernelSU/OverlayFS 门禁、整组恢复和 OTA 前停用要求见[使用教程](docs/USER_GUIDE.md#7-候选安装与恢复边界)。

仅对已重新核对的精确系统：准备 Root、Zygisk、modern API102 LSPosed 及已启用并重启生效的 OverlayFS MetaModule 1.3.1。刷入时安装统一插件及可立即部署的所选组件；电话若受商店重启门禁限制，用户手动重启后 parent service 仅续装该次固定计划的电话。依赖未就绪或执行失败时停止并留日志，不自动反复重试；续装检测到手动 controller 任务改变记录时取消待续装队列。保留数据和原有独立恢复门禁，不自动重启、不写 compat 偏好、不代为启用 LSPosed 插件或授权作用域，用户仍须单独配置兼容。只读能力 CSV 仅限制本包组件配置页的预设选择与安装，不是运行时 hook 门禁；省略不卸载已有组件、不自动关闭其他页面既有开关或 hook，停用须单独关闭兼容或恢复组件。

钱包默认不选。即使电脑明确勾选，首次匹配 EEA TSM 迁移也延后到手机组件配置的单任务明确确认，刷入与续装不直接重置；确认后可能清除旧 TSM 数据及 UID 绑定密钥，旧卡可能失效。已有精确 CN TSM 就绪时可按 guard 自动安装，不重复清除。保留独立恢复不等于钱包共享 UID 或密钥可无损逆转。不要操作支付、卡片或报警接口来冒充安装验证。

不修改全局XMSF，不把它加入统一插件作用域；MiPush仅针对明确支持且用户选择的应用/精确SDK版本。真实通知送达、门卡、支付、电话及云端AI能力需要分别验证。

## 验证范围

0.7.0 的全量材料与自动部署记录保留在 [AUTOINSTALL_VALIDATION.md](docs/AUTOINSTALL_VALIDATION.md)。0.7.1 的原电话/短信管理、恢复测试及实际材料生成记录见 [STOCK_APPS.md](docs/STOCK_APPS.md#本次验证记录)，最终提交的 CI 与源码附件摘要见对应 Release。**父包安装成功不等于自动部署成功**，仍须核对 result 和 job 日志。本轮没有安装或操作手机，也没有新增全 11 项构建、native KernelSU、OverlayFS、真实 boot 或数据保留的设备证明。

参考私有1.7已验证原位安装、钱包单项勾选、三次重启、READY与在线首页。干净EEA系统首次TSM迁移及全组件从零首装尚未实机验证。钱包真实推送、支付和门卡未验收。该事实不自动转移为任何公开源码自行构建版本的手机验证结论。

[发布脱敏说明](docs/PRIVACY.md) · [贡献说明](CONTRIBUTING.md) · [安全报告](SECURITY.md) · [第三方声明](THIRD_PARTY_NOTICES.md)

## 许可

原创工具源码以Apache-2.0发布，见[LICENSE](LICENSE)。小米软件、固件及其他第三方材料不在本项目授权范围内。Xiaomi、HyperOS等名称归各权利人所有；本项目非官方项目。
