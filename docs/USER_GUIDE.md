# 电脑工具 0.5.0 使用教程（预览版）

本工具在电脑上读取本地固件/APK、检查兼容性并生成候选 ZIP。默认入口「其他机型 · 从目标固件识别」**不需要原 1.4 套件**。工具不使用 ADB，不连接、安装或重启手机，不自动下载依赖或接受许可。

**默认流程只生成普通系统 APK 的受限挂载候选包。** 不包含统一 API102 插件、权限修复或已有 1.7 的 WebUI，不会根据任意固件重建全部 1.7 功能。静态检查通过不等于国行功能移植成功，也不等于手机实测通过。

## 1. 下载与产物区分

在 [tool-v0.5.0 预览版发布页](https://github.com/skiyakubali0-cloud/XiaomiLocalSuite/releases/tag/tool-v0.5.0) 下载 `XiaomiLocalSuite-Tool-0.5.0.zip`，完整解压，进入 `XiaomiLocalSuite-Tool-0.5.0` 文件夹。不要在压缩软件中直接运行。

| 文件/产物 | 用途 | 边界 |
| --- | --- | --- |
| `XiaomiLocalSuite-Tool-0.5.0.zip` | 电脑端源码、启动器、教程 | 需要本机运行环境，不是签名独立 DMG/EXE，不是手机模块 |
| 用户生成的候选 `.zip` 与 `.build.json` | 精确机型、ROM、APK 的候选与构建记录 | 含原厂材料，只留本地，不公开上传 |
| 私有 1.7 套件 | 另一条精确参考系统重建路线 | 需私有参考包和自签名 APK，非默认流程 |

工具包不含小米固件、原厂 APK、签名私钥或第三方工具二进制。版本 **0.5.0** 指电脑工具，不是手机套件 **1.7** 或历史配方 **1.4** 的版本号。

## 2. 准备环境

| 环境 | 要求 | 自检 |
| --- | --- | --- |
| Python/Tk | Python 3.11+，GUI 需 Tk 8.6+ | `python3 --version`、`python3 -m tkinter` |
| Java | JDK 17+，`java` 可执行 | `java -version` |
| Android SDK | build-tools 36.0.0 的 `aapt2`、`apksigner` | GUI「环境检查」 |
| 完整 OTA 解包（可选） | `payload-dumper-go`、erofs-utils 的 `fsck.erofs` | GUI「环境检查」；只用已解包目录/APK 时无需这两项 |

自行安装依赖并决定是否接受其许可。推荐在 Android Studio 的 SDK Manager 中选择 Android SDK Build-Tools **36.0.0**；`ANDROID_SDK_ROOT` 指 SDK 根目录，不能指向 build-tools 子目录。[Android 官方工具说明](https://developer.android.com/tools/sdkmanager) 可供核对环境。工具不执行 SDK 下载或许可接受。

macOS：使用带 Tk 的 Python。Homebrew 用户可按 [python-tk@3.13 官方配方](https://formulae.brew.sh/formula/python-tk@3.13) 执行 `brew install python-tk@3.13`，再使用对应 `python3.13`。旧 Tk 8.5 可能显示空白窗口，应先更换环境。

Linux：自行安装发行版的 Python、匹配的 Tk、JDK 与桌面显示环境。先确认 `python3 -m tkinter` 能显示窗口。无显示的 SSH/CI 会话可用 CLI；Linux CI 通过不表示所有 Linux 桌面均已实测。

Windows：原生 Windows 当前**未达到完整流程就绪条件**。`windows.cmd` 是便捷入口，不构成原生兼容证明。建议使用具备 GUI 显示能力的 WSL2，在 WSL2 内安装 Linux 版 Python/Tk、Java、SDK 与可选解包工具，并先验证 Tk 窗口。不要混用 Windows 与 Linux 工具路径；没有原生 Windows 完整流程实测结论。

完整 OTA 解包工具从 [payload-dumper-go 上游](https://github.com/ssut/payload-dumper-go) 和 [erofs-utils 官方源码](https://git.kernel.org/pub/scm/linux/kernel/git/xiang/erofs-utils.git) 自行准备，避免来源不明的二进制。只支持相应完整 `payload.bin` / EROFS 路径；增量 OTA、fastboot TGZ、ext4/sparse 镜像不自动转换。

macOS/Linux/WSL2 在当前终端指定已安装的 SDK，替换示例路径：

```sh
export ANDROID_SDK_ROOT="/local/android-sdk"
export PATH="$ANDROID_SDK_ROOT/build-tools/36.0.0:$PATH"
```

## 3. 启动与环境检查

从工具根目录运行：

```sh
python3 launch.py --check
python3 launch.py
```

`--check` 检查 Python/Tk 运行时及核心导入，不打开 Tk 窗口、不运行外部程序；它不替代 GUI 对 Java、SDK 和可选解包工具的「环境检查」。进入 GUI 后先点「环境检查」，按缺项补齐工具；检查不下载依赖，也不改变组件选择。

| 系统 | 启动器 |
| --- | --- |
| macOS | 双击 `launchers/macOS.command`；终端回退为 `sh launchers/macOS.command` |
| Linux / WSL2 | `sh launchers/linux.sh` |
| Windows 原生诊断入口 | `launchers\windows.cmd`；完整流程优先 WSL2 |

`XLS_PYTHON` 可指定一个 Python 可执行文件路径，不是一串带参数的命令。macOS 安装上述 Tk 后也可直接运行 `python3.13 launch.py`。GUI「使用教程」在只读窗口中打开本离线文档。

## 4. 材料与外接磁盘

目标指手机实际要运行的**目标 EEA 固件版本**。可先选择该版本完整 OTA ZIP，再显式解包；也可直接选已解包目录。最终检查需要同版本、真实且相互匹配的 `build.prop` 和目标原始 APK；只给一个来源 APK 不能省略目标固件目录。

来源可以是同机型国行固件、其解包目录、APK 目录或多个单独 APK。使用可信、合法持有的材料，不混用不同机型/ROM 的属性和 APK。APK 签名检查不证明固件来源真实性。

把工作目录设置在容量足够的外接磁盘上，材料、解包目录、配置和结果放到仓库外。完整解包可能占用数十 GiB 或更多；工具按 payload、镜像、解包树和预留空间估算，空间不足停止，不把固定容量当作保证。

## 5. GUI：分析 → 勾选 → 检查 → 生成

1. 保持默认「其他机型 · 从目标固件识别」。配置标识仅用英文字母、数字、点或横线，例如 `exampledevice-os4-build1`。
2. 在「目标系统」选 EEA OTA/解包目录；在「来源材料」选同机型国行 OTA/目录，或点「添加APK」一次选择多个 APK。
3. 若选 OTA，先确认外接磁盘工作目录，再点对应「解包OTA」，目标与来源分别解包到新目录。「分析材料」不自动解包，已有解包目录不用重复操作。
4. 点「分析材料」，核对机型、ROM、SDK、ABI 和 APK。缺失、冲突或误识别时停止并检查材料。
5. 新组件默认全不选。点列表第一列方框或选中行后按空格勾选；钱包锁定项不能通过全选或旧配置解锁。
6. 点「检查兼容性」，先处理阻断项。不要手工删规则、改机型、SHA、签名或共享 UID 来绕过。
7. 静态通过后点「生成候选ZIP」，使用尚不存在的新文件名。生成前仍重读材料；更改材料或选择后必须重新检查。
8. 核对输出 ZIP、大小、SHA256 和同名 `.build.json`。可另存配置/报告；重新打开配置后仍要检查当前材料。

分析、解包和生成在后台运行，等待任务结束再关闭窗口。配置/报告可能包含材料绝对路径和诊断；这些文件、原厂材料、候选与原始验证日志都留在本地，不上传 Issues、PR、仓库或 Releases。

## 6. 允许与拒绝范围

通用路线只接受目标已有、同签名、非 split 的普通系统 APK，不向系统任意新增特权应用，不推断权限补丁、SELinux 规则、依赖或 LSP 钩子。

新增权限/库依赖、新增特权应用、共享 UID 不匹配、签名差异、分包、降级、ABI/SDK 不兼容、元数据不全等需要单独审阅配方。系统框架、电话底层、手机管家/securitycenter、桌面/launcher、钱包/TSM/eSE/NFC、全局 XMSF 等关键内容不走这条路线。

`candidate-static-pass` 只表示当前材料满足静态规则。登录、通知、云端 AI、后台行为与实机运行仍需分别验证。导入原始材料不会自动获得全部 1.7 功能。

## 7. 候选安装与恢复边界

工具不执行手机操作。用户若另行决定评估候选，需要 KernelSU 和**已启用且重启生效的 OverlayFS 1.3.1**，并满足精确机型、ROM、单用户 0、当前 APK 路径和 SHA 等门禁。不要把电脑工具 ZIP 交给 KernelSU 安装。

活动 APK 位于 `/data/app`、应用商店更新、分包或哈希变化可能阻断安装。不要通过自动清数据、卸载更新、重置密钥或改校验值绕过；先重新评估系统与材料。

**一个候选 ZIP 内多选的 APK 是同一恢复组。** 在 KernelSU 禁用该候选模块并手动重启，会一起恢复其覆盖的 APK；通用路线没有既有 1.7 的逐项 WebUI 恢复。要分别恢复，从一开始每次只选一个 APK，用不同配置标识分别生成、安装候选模块。不要用同一配置标识覆盖不同选择；变更既有候选前先卸载该候选并重启，避免未选 APK 残留。

OTA 前必须先禁用候选并重启，升级后重读目标固件再检查。启动阶段版本检测不能替代 OTA 前停用，不保证带候选跨 ROM 升级安全。工具不自动清数据、不生成钱包 reset、不迁移凭据、不改全局 XMSF，不自动接受协议、安装或重启。

## 8. CLI 示例

从工具根目录运行。`/local/materials`、`/local/work` 是需替换的示例路径，输出名必须未占用。macOS/Linux/WSL2 使用对应 Python 3.11+，命令不连接手机。

先看元数据；必要时显式解包两个完整 OTA 到新目录：

```sh
mkdir -p /local/work
python3 suite/multi-device/suite_builder.py inspect "/local/materials/target-eea.zip" --out "/local/work/target-info.json"
python3 suite/multi-device/suite_builder.py extract "/local/materials/target-eea.zip" --out "/local/work/target" --partitions product,system_ext,system
python3 suite/multi-device/suite_builder.py extract "/local/materials/source-cn.zip" --out "/local/work/source" --partitions product,system_ext,system
```

已有解包目录可跳过 `extract`；只查看 OTA 元数据不证明 APK 兼容。来源仅有 APK 时，把下一条 `--source` 换成 APK 文件或 APK 目录，`--target` 仍须为目标固件目录。GUI 支持多文件选择；CLI `init` 接受一个来源路径，可用目录容纳多个来源 APK。

```sh
python3 suite/multi-device/suite_builder.py init --id "exampledevice-os4-build1" --target "/local/work/target" --source "/local/work/source" --out "/local/work/draft.json"
python3 suite/multi-device/suite_builder.py select --profile "/local/work/draft.json" --packages "com.example.app" --out "/local/work/selected.json"
python3 suite/multi-device/suite_builder.py check --profile "/local/work/selected.json" --out "/local/work/check.json"
python3 suite/multi-device/suite_builder.py build --profile "/local/work/selected.json" --candidate --out "/local/work/exampledevice-candidate.zip"
```

`com.example.app` 是虚构示例，换成 draft 中实际存在、符合规则的包名。逗号分隔可选多个，`--packages -` 表示全部取消；没有选择时不能生成。阻断为 `state=blocked`、退出码 2。生成重新验证材料，不信任旧报告；输出 ZIP 与同名 `.build.json`，不覆盖已有文件。

WSL2 下 Windows 盘可通过实际挂载访问，例如把工作目录换成 `/mnt/d/XiaomiWork`，先核对权限与空间。Windows PowerShell 仅启动诊断示例：

```powershell
py -3 launch.py --check
```

完整 OTA/APK 流程在具备 GUI 的 WSL2 中运行上面的 Linux 命令。不要把 Windows SDK 二进制当作 WSL2 的 Linux 工具；PowerShell 也不使用 POSIX 反斜杠续行。

## 9. 常见问题

| 现象 | 处理 |
| --- | --- |
| 启动器闪退、Python 太旧 | 终端运行 `python3 launch.py --check`；选择 Python 3.11+，或用 `XLS_PYTHON` 指定解释器 |
| 缺 tkinter、窗口空白 | 安装匹配当前 Python 的 Tk 8.6+；同一解释器运行 `-m tkinter` 验证，停用旧 Tk 8.5 |
| Linux/WSL2 没有 display | 准备桌面/WSL2 GUI，或用 CLI；启动诊断不证明窗口可显示 |
| 缺 Java/SDK | 补齐 JDK 17+ 与 build-tools 36.0.0，核对 SDK 根目录、PATH、工具执行权限，再点环境检查 |
| 缺 payload/EROFS 工具 | 自行安装，或提供已解包且含真实属性、原始 APK 的固件目录 |
| OTA 分析后没 APK | 先显式解包，不能把 OTA 元数据扫描当作 APK 已验证 |
| 解包/生成空间不足 | 换外接磁盘与新输出目录，不覆盖旧材料或中断后残留目录 |
| 目标属性冲突/未知机型 | 检查是否混入不同 ROM，补齐同一目标版本材料再分析 |
| 签名/降级/权限/依赖阻断 | 取消该组件或请求精确配方审阅；不通过重签、清数据、改 SHA 绕过 |
| 输出文件已存在 | 换新文件名；工具故意不覆盖已有配置、报告、安装包 |
| macOS 的 JSON 被置灰 | 文件选择框切换「所有文件」，内容仍会校验 |
| 想分别恢复多个 APK | 每次单选一个，用不同配置标识生成；同一候选多选只支持整组禁用并重启恢复 |

## 10. 历史配方与精确 1.7

带「历史配方」的完整 1.4/精选入口只供合法持有精确原 1.4 套件的用户；只有这些入口要求旧包，不随工具分发。原机型、ROM、SHA 和依赖规则继续适用，不能用任意固件代替。

可选精确 1.7 开发路线见 [BUILD_SUITE.md](BUILD_SUITE.md)，需要本地私有 1.7 参考包与用户自行签名的统一 APK。它不是默认 GUI 模式，也不会由通用 APK 候选自动生成。

本预览版 macOS GUI 与 Linux CI 的验证范围不能扩展成原生 Windows、新机型实机、完整功能移植或钱包/支付/卡片证明。0.5 验证记录见 [TOOL_VALIDATION.md](TOOL_VALIDATION.md)，发布范围见 [RELEASE_TOOL.md](RELEASE_TOOL.md)。
