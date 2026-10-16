# XiaomiLocalSuite

面向小米 HyperOS 的本地化适配工具源码：一个 modern API 102 LSPosed 插件、独立 Root 组件、按需勾选安装入口，以及电脑端 APK/固件兼容检查工具。

**电脑工具 0.5.0 预览版**：[下载 `XiaomiLocalSuite-Tool-0.5.0.zip`](https://github.com/skiyakubali0-cloud/XiaomiLocalSuite/releases/tag/tool-v0.5.0) · [中文使用教程](docs/USER_GUIDE.md) · [发布说明](docs/RELEASE_TOOL.md)。需自备 Python/Tk、Java 和 SDK，不是独立 DMG/EXE 或手机模块。解压后运行 `python3 launch.py`，默认从目标固件识别，无须旧 1.4。

默认 GUI 只生成目标已有、同签名、非 split 的普通系统 APK 受限候选包；不含统一 API102 插件、权限修复或 1.7 WebUI，不能从任意固件复原全部 1.7 功能。同一候选内多选 APK 作为一组恢复；静态通过不等于手机功能验证。含原厂材料的结果仅本地使用，不公开发布。Windows 原生完整流程未就绪，优先使用具备 GUI 的 WSL2。

当前参考实现为小米15 Ultra `xuanyuan`、EEA `OS4.0.0.6.XOAEUXM`、Android17/API37。它不是通用跨机型一键移植工具，未知机型、ROM、APK 或共享 UID 应停止安装并重新审查。

## 仓库包含什么

- `suite/unified-api102/`：统一插件源码、依赖哈希、构建入口与主机回归。modern API102，唯一入口，默认作用域为空。
- `suite/module/`：1.7父套件控制器、勾选计划、WebUI、旧插件迁移与钱包协作逻辑的文本模板。
- `native/assistant/`：自主编写的桌面路由原生代码参考；不附NDK、Zygisk头文件或原厂库。
- `components/`：商店、智能助理、小爱、电话/短信、相册、天气、预警和钱包组件的脚本及配置。
- `suite/multi-device/`：0.5.0 本地 GUI、固件/APK读取与保守兼容检查，默认通用候选流程；1.4 入口标记为历史配方，不自动生成当前1.7或通用钱包移植。
- `materials.lock.json`：私有二进制材料的相对路径、字节数及精确SHA256；不包含这些材料本身。
- `tools/build_suite.py`：使用本地精确参考包和自行签名统一APK重建当前套件。
- 其余历史packager及fixture保留作回归参考；通用候选使用桌面工具入口，精确1.7重建使用 `tools/build_suite.py` 并自备私有材料。

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

插件签名方式见[suite/unified-api102/README.md](suite/unified-api102/README.md)，套件重建见[docs/BUILD_SUITE.md](docs/BUILD_SUITE.md)。本地构建产物默认属于私有材料，不自动上传或安装手机。

**自行签名APK无法直接覆盖此前私人签名的同包名插件。** 仓库不提供旧私钥，也不承诺重现旧APK哈希。签名、APK哈希与CLI校验必须成套生成；原已部署手机的升级需要原签名和重新验证，不要为绕过签名直接卸载旧插件或清数据。

## 私有 1.7 手机端参考安装流程

以下属于精确参考套件，不是默认通用候选的功能或安装承诺。通用候选的 KernelSU/OverlayFS 门禁、整组恢复和 OTA 前停用要求见[使用教程](docs/USER_GUIDE.md#7-候选安装与恢复边界)。

仅对已重新核对的精确系统：准备Root、Zygisk、支持modern API102的LSPosed及已启用并重启生效的OverlayFS MetaModule1.3.1；安装私有构建的匹配套件，重启后启用唯一统一插件，在组件配置中勾选并应用，按依赖、作用域与重启提示分批完成。

钱包默认不选。首次匹配EEA TSM迁移必须单次明确确认，会清旧小米TSM本地数据并可能使UID关联密钥/旧卡失效；私人备份不能保证恢复密钥。已有精确CN TSM重装不重复清除。取消勾选只跳过安装，钱包反向共享UID迁移不作为普通无损恢复。不要操作支付、卡片或报警接口来冒充安装验证。

不修改全局XMSF，不把它加入统一插件作用域；MiPush仅针对明确支持且用户选择的应用/精确SDK版本。真实通知送达、门卡、支付、电话及云端AI能力需要分别验证。

## 验证范围

参考私有1.7已验证原位安装、钱包单项勾选、三次重启、READY与在线首页。干净EEA系统首次TSM迁移及全组件从零首装尚未实机验证。钱包真实推送、支付和门卡未验收。该事实不自动转移为任何公开源码自行构建版本的手机验证结论。

[发布脱敏说明](docs/PRIVACY.md) · [贡献说明](CONTRIBUTING.md) · [安全报告](SECURITY.md) · [第三方声明](THIRD_PARTY_NOTICES.md)

## 许可

原创工具源码以Apache-2.0发布，见[LICENSE](LICENSE)。小米软件、固件及其他第三方材料不在本项目授权范围内。Xiaomi、HyperOS等名称归各权利人所有；本项目非官方项目。
