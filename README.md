# XiaomiLocalSuite

面向小米 HyperOS 的本地化适配工具源码：一个 modern API 102 LSPosed 插件、独立 Root 组件、按需勾选安装入口，以及电脑端 APK/固件兼容检查工具。

**电脑工具 0.6.0 预览版**：[下载 `XiaomiLocalSuite-Tool-0.6.0.zip`](https://github.com/skiyakubali0-cloud/XiaomiLocalSuite/releases/tag/tool-v0.6.0) · [中文使用教程](docs/USER_GUIDE.md) · [完整 1.7 原始材料路线](docs/FULL_RECIPE.md) · [发布说明](docs/RELEASE_TOOL.md)。需自备 Python/Tk、Java 和 SDK，不是独立 DMG/EXE 或手机模块。解压后运行 `python3 launch.py`，默认通用入口保留，无须旧 1.4。

默认 GUI 只生成目标已有、同签名、非 split 的普通系统 APK 受限候选包；不含统一 API102 插件、权限修复或 1.7 WebUI，不能从任意固件复原全部 1.7 功能。同一候选内多选 APK 作为一组恢复；静态通过不等于手机功能验证。含原厂材料的结果仅本地使用，不公开发布。Windows 原生完整流程未就绪，优先使用具备 GUI 的 WSL2。

0.6.0 新增「小米15 Ultra · OS4.0.0.6 完整1.7适配」：用精确 EEA `OS4.0.0.6.XOAEUXM`、同机型 CN `OS4.0.0.6.XOACNXM` 及锁定额外 APK，无需私有参考 ZIP，按需生成保留 1.7 WebUI、逐项 Root 恢复与 API102 的 parent。11 行默认全不选，电话依赖商店、小爱依赖智能助理，钱包只能单独手选。须提供当前公开源码自行签名的统一 APK 与配套 `.build-evidence.json`，也可在 GUI 本地构建；缺项报告路径、大小和 SHA，不回退私有 ZIP。完整操作、离线依赖、密钥和手机分批安装边界见[完整教程](docs/FULL_RECIPE.md)。已完成原始材料全量构建及 macOS GUI 生成验证，详见[验证与复用记录](docs/FULL_RECIPE_VALIDATION.md)；手机功能仍须单独验证。

当前参考实现为小米15 Ultra `xuanyuan`、EEA `OS4.0.0.6.XOAEUXM`、Android17/API37。它不是通用跨机型一键移植工具，未知机型、ROM、APK 或共享 UID 应停止安装并重新审查。

## 仓库包含什么

- `suite/unified-api102/`：统一插件源码、依赖哈希、构建入口与主机回归。modern API102，唯一入口，默认作用域为空。
- `suite/module/`：1.7父套件控制器、勾选计划、WebUI、旧插件迁移与钱包协作逻辑的文本模板。
- `native/assistant/`：自主编写的桌面路由原生代码参考；不附NDK、Zygisk头文件或原厂库。
- `components/`：商店、智能助理、小爱、电话/短信、相册、天气、预警和钱包组件的脚本及配置。
- `suite/multi-device/`：本地 GUI、固件/APK读取与兼容检查；保留 0.5 通用候选和历史 1.4 入口，0.6.0 增加独立的精确 1.7 原始材料模式。
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

以下为精确 1.7 路线的手机端步骤，不是默认通用候选的功能或安装承诺。电脑组件勾选仅决定 ZIP 内容，不在手机自动安装组件。通用候选的 KernelSU/OverlayFS 门禁、整组恢复和 OTA 前停用要求见[使用教程](docs/USER_GUIDE.md#7-候选安装与恢复边界)。

仅对已重新核对的精确系统：准备Root、Zygisk、支持modern API102的LSPosed及已启用并重启生效的OverlayFS MetaModule1.3.1；用户另行决定安装匹配 parent，由 parent 安装统一插件，手动重启后启用插件并核对/授权作用域，在手机组件配置中检查、勾选并应用，按依赖、分批与重启提示完成。只读能力 CSV 仅限制本包组件配置页的预设选择与安装，未打包项在该页不可选，包内默认选择仍不含钱包；检查只在内存中过滤选择，不清除旧偏好。省略组件不卸载已有组件，也不自动关闭其他页面的既有兼容开关或 hook；如需停用，须单独关闭相应兼容或恢复组件。

钱包默认不选。首次匹配EEA TSM迁移必须单次明确确认，会清旧小米TSM本地数据并可能使UID关联密钥/旧卡失效；私人备份不能保证恢复密钥。已有精确CN TSM重装不重复清除。取消勾选只跳过安装，钱包反向共享UID迁移不作为普通无损恢复。不要操作支付、卡片或报警接口来冒充安装验证。

不修改全局XMSF，不把它加入统一插件作用域；MiPush仅针对明确支持且用户选择的应用/精确SDK版本。真实通知送达、门卡、支付、电话及云端AI能力需要分别验证。

## 验证范围

参考私有1.7已验证原位安装、钱包单项勾选、三次重启、READY与在线首页。干净EEA系统首次TSM迁移及全组件从零首装尚未实机验证。钱包真实推送、支付和门卡未验收。该事实不自动转移为任何公开源码自行构建版本的手机验证结论。

[发布脱敏说明](docs/PRIVACY.md) · [贡献说明](CONTRIBUTING.md) · [安全报告](SECURITY.md) · [第三方声明](THIRD_PARTY_NOTICES.md)

## 许可

原创工具源码以Apache-2.0发布，见[LICENSE](LICENSE)。小米软件、固件及其他第三方材料不在本项目授权范围内。Xiaomi、HyperOS等名称归各权利人所有；本项目非官方项目。
