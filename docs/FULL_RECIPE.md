# 小米 15 Ultra · OS4.0.0.6 完整 1.7 原始材料路线

本文对应电脑工具 **0.7.0 prerelease**，tag 为 `tool-v0.7.0`。它用公开源码和用户自己的固件/APK 材料生成本地 1.7 parent ZIP，**不需要私有 1.7 参考 ZIP**。新版方案在用户另行刷入 ZIP 时部署电脑勾选的组件，保留数据和独立恢复；特殊的电话续装及首次钱包迁移见第 6 节。「完整」指精确配方能力，不表示全部功能已实机验收。

只支持小米 15 Ultra `xuanyuan`、EEA **`OS4.0.0.6.XOAEUXM`**、Android 17 / API 37 / `arm64-v8a`，配合同机型 CN **`OS4.0.0.6.XOACNXM`** 原始材料及配方锁定的额外 APK。不同 ROM、机型或同版本号但 SHA256 不符的材料不能替代。该路线不是通用移植器。

电脑端只读取材料、编译和生成文件，不连接手机，不调用 ADB，不安装、启用、重启或重置手机。自动部署仅由用户另行刷入生成的 parent 触发，不发生在电脑生成阶段。0.7.0 的原始材料、整包与 GUI 生成及主机执行验证见 [AUTOINSTALL_VALIDATION.md](AUTOINSTALL_VALIDATION.md)；0.6.0 的[材料与生成记录](FULL_RECIPE_VALIDATION.md)不能作为新版自动部署证明。生成成功也不证明电话、云端 AI、通知、报警定位、支付或门卡可用。

## 1. 准备环境和材料

从工具根目录运行，要求 Python 3.11+、GUI 所需的 Tk 8.6+、JDK 17+。自行安装 Android SDK `platforms;android-36` 和 `build-tools;36.0.0`，插件构建及 APK 检查会使用 `javac`、`d8`、`aapt2`、`zipalign`、`apksigner`。编译 SDK 36 不改变运行目标 API 37。工具不自动安装 SDK，也不接受其许可。

在 macOS/Linux/WSL2 的当前终端指定本机 SDK 根目录，供后续 APK 检查定位工具：

```sh
export ANDROID_SDK_ROOT="/local/android-sdk"
export PATH="$ANDROID_SDK_ROOT/build-tools/36.0.0:$PATH"
```

准备以下本地输入，原厂材料、密钥和最终 ZIP 放在源码目录外的私人工作目录：

| 输入 | 用途 |
| --- | --- |
| 精确 EEA 目标固件的已解包目录 | 必须包含真实、相互匹配的属性文件及配方需要的原始 APK/库；不能用单 APK 代替 |
| 同机型精确 CN 固件的已解包目录，或 APK 文件/目录 | `--source` 可重复，补充来自匹配材料的精确字节 |
| 额外锁定 APK | 两份 OTA 不保证已含配方的全部版本，按缺项清单补齐 |
| 当前公开源码编译并由自己签名的统一 APK及配套证据 | 见下文；不接受误用旧 APK 或缺少证据的文件 |
| 自己的 keystore、alias、密码 | 仅用于本地签名，不随工具提供或自动生成 |

完整 OTA ZIP 需先显式解包。已有目录不必再次解包；仅分析 OTA 元数据不能证明材料齐全。解包使用用户已安装的 `payload-dumper-go` 和 erofs-utils 的 `fsck.erofs`，示例见[使用教程](USER_GUIDE.md#8-cli-示例)：

```sh
python3 suite/multi-device/suite_builder.py extract "/local/materials/xuanyuan-eea-os4.0.0.6.zip" --out "/local/work/eea" --partitions product,system_ext,system
python3 suite/multi-device/suite_builder.py extract "/local/materials/xuanyuan-cn-os4.0.0.6.zip" --out "/local/work/cn" --partitions product,system_ext,system
```

使用新输出目录，预留足够磁盘空间。增量 OTA、fastboot TGZ、ext4/sparse 不会自动转换成受支持的完整 payload/EROFS 路线。

### 精确额外输入与缺项

[recipes/generated.json](../recipes/generated.json) 固定以下原始生成输入；仅在所选组件需要它们时补齐。文件名不决定身份，大小及 SHA256 必须匹配。天气配方保留两个版本的材料，因此选择天气可能同时需要天气 23 和 27。

| 所选组件 | 原始输入 | 字节数 | SHA256 |
| --- | --- | ---: | --- |
| `assistant` | EEA `system_ext/lib64/libhyper_os_core_system_private.dylib.so` | 318656 | `a7de453780f33d2dec0cfca8832d218ee798f3208df06af36744f416313afa1f` |
| `disaster` | 原签名 `com.miui.securitycenter`，`13.6.5-261003.0.1` / code `40001365` | 81091182 | `f3d338484cc5fd3f3fec9e8d9d0b4c6370923fba0f5e0d81975a45e914cbc776` |
| `weather` | 原签名 `com.miui.weather2`，`18.0.0.23-R` / code `180000230` | 63138625 | `2a8faed30ce5ffe4ae0229dce0d520d882dff990f6ef158e5fbb555153b7e887` |
| `weather` | 原签名 `com.miui.weather2`，`18.0.0.27-R` / code `180000270` | 41311702 | `017d613137c0512a937dc6b8565da856099e988feab47b9eabc5c3d0a13f06e6` |

这张表不是全部材料清单。其余 APK、库、DEX 等以 [materials.lock.json](../materials.lock.json) 和本次检查的 `missing` 为准，例如天气的 CN/global core、global 天气 APK，以及相册与编辑依赖。lock 共 **215 项**，包含旧统一 APK；原始材料路线只要求所选组件及依赖对应的条目，日历按需包含 parent 日历材料，旧 `payload/unified.apk` 由调用者的新 APK 替换，不要求取得旧私有插件。

检查输出逐项列出缺少材料的 `component`、`path`、`bytes`、`sha256` 和原因；32 种原始 APK 还显示包名和版本码，元数据见 [apk-materials.json](../recipes/apk-materials.json)。缺项不代表可用任意同名 APK 补齐；请补充精确材料，或取消相应组件。不会回退读取私有参考 ZIP，也不会通过更改 lock、SHA 或签名绕过。

智能助理和天气的原生补丁、预警 DEX 由公开配方从调用者的精确原始输入在本机生成，并核对生成结果的锁定哈希。相关配方见 `tools/recipe_generated.py`、`native/assistant/` 和 `recipes/generated.json`；仓库不包含生成所需的 OEM 二进制或 OEM 反编译代码。

### 当前材料验证范围

0.6.0 已从现有原始材料匹配 214/214 项，并完成全量 ZIP 和实际 GUI 部分包生成，记录见 [FULL_RECIPE_VALIDATION.md](FULL_RECIPE_VALIDATION.md)。该证据不覆盖 0.7.0 新增的刷入部署或重启续装。本轮没有重新解包全量 OTA，也不操作手机。CN 固件之外仍需配方锁定的更新 APK 和 EEA 恢复 APK，按缺项清单补齐。

0.7.0 已核对当前 APK 构建证据及 214/214 原始材料，生成全 11 项包 **1,101,469,378 字节**，并通过父子校验和、52 份 shell 及最终安装脚本核对；没有使用私有参考 ZIP。实际 GUI 生成商店/智能助理包 **68,561,763 字节**，固定自动部署计划正确。详细证据和未验证的设备范围见 [AUTOINSTALL_VALIDATION.md](AUTOINSTALL_VALIDATION.md)。

## 2. 显式准备依赖

统一插件需要 3 份 libxposed 102.0.0 AAR，预警 DEX 生成需要 4 份固定 JAR。优先使用自己准备的离线目录，从根目录执行：

```sh
python3 suite/unified-api102/fetch_dependencies.py --local-dir "/local/deps/libxposed"
python3 tools/recipe_tools.py --local-dir "/local/deps/warning"
```

第一条按 [deps.lock.json](../suite/unified-api102/deps.lock.json) 校验 `api-102.0.0.aar`、`service-102.0.0.aar`、`interface-102.0.0.aar`，缓存到 `suite/unified-api102/build/deps/`。第二条按 [generated.json](../recipes/generated.json) 校验下列 JAR，缓存到工具根目录的 **`build/recipe-tools/`**，原始材料解析器从该目录读取：

- `com.android.tools.smali:smali-dexlib2:3.0.9`
- `com.google.guava:guava:31.1-android`
- `com.google.guava:failureaccess:1.0.1`
- `com.google.code.findbugs:jsr305:3.0.2`

文件名、URL、大小和 SHA256 以两个公开 JSON 为准，勿改名或用任意 JAR 替换。只选择无需预警 DEX 的组件时，不必为其准备预警工具。

需要联网时，在 GUI「本地构建统一插件…」对话框中显式点击「联网准备依赖」；CLI 则分别显式执行：

```sh
python3 suite/unified-api102/fetch_dependencies.py --download
python3 tools/recipe_tools.py --download
```

这些动作只获取锁定的 3 份 AAR 和 4 份预警 JAR，不下载 OEM 材料、SDK 或接受许可。分析、检查、生成及插件编译本身不会自动联网补依赖。第三方坐标和来源记录不构成本项目对其许可的法律结论。

## 3. 准备自己的统一插件

可在 GUI 的「统一插件APK」一栏点击「选择APK…」选择自己已编译的统一 APK，或点击「本地构建统一插件…」。本地构建对话框要求自己的 keystore、alias、遮蔽显示的密码、已安装 SDK 路径和离线 AAR 目录。密码只通过子进程环境传给签名工具，不写入配置、报告或命令行；不会自动生成密钥，也不提供旧私人签名密钥。开始构建或联网准备后对话框关闭并清空输入；准备依赖后如需构建，重新打开填写。

如果尚无自己的签名密钥，可自行在源码目录外运行以下命令。`keytool` 会交互询问密码及证书信息，命令中不填密码：

```sh
keytool -genkeypair -keystore "/local/private/xls-signing.p12" -storetype PKCS12 -alias xls-local -keyalg RSA -keysize 3072 -validity 3650
```

保管好自己的密钥及密码，后续同签名升级需要它们；不要提交、分享或随产物发布。新自签名不能覆盖旧签名的同包名插件，不因 versionCode 相同就获得旧签名身份；不要为绕过签名校验卸载旧插件或清数据。

CLI 使用当前源码的 `build_apk.py --wallet-selectable`；该开关名称不表示默认安装钱包。下例通过不回显的交互输入，把两个密码仅交给构建子进程环境；按本机情况替换路径和 alias：

```sh
python3 - <<'PY'
import getpass, os, subprocess, sys
env = os.environ.copy()
env["SUITE_STORE_PASSWORD"] = getpass.getpass("Keystore 密码：")
env["SUITE_KEY_PASSWORD"] = getpass.getpass("Key 密码（即使相同也需输入）：")
subprocess.run([
    sys.executable, "suite/unified-api102/build_apk.py", "--wallet-selectable",
    "--sdk", "/local/android-sdk", "--deps-dir", "/local/deps/libxposed",
    "--keystore", "/local/private/xls-signing.p12", "--key-alias", "xls-local",
    "--output", "build/full17-local.apk",
], env=env, check=True)
PY
```

输出路径相对于 `suite/unified-api102/`，必须为其 `build/` 内的新 `.apk`，不覆盖已有 APK/证据。上例产出 `suite/unified-api102/build/full17-local.apk` 及同目录 **`full17-local.build-evidence.json`**，移动时必须成对保留。

配方入口核对 APK SHA256、依赖 SHA256，以及当前 manifest、Java 源码、构建/取依赖脚本、lock 和 Xposed 元数据的**完整文件集合及哈希**。缺少或不匹配时，重新从当前公开源码编译，不能用旧 code 17 APK 顶替，也不要手改证据。证据用于防止误用过期文件，**不是构建来源的可信证明或 attestation**。插件保留 `versionCode=17`；文件名里的旧 `1.6` 名称同样不能证明源码是否为当前版本。

一个新编译的通用 API102 APK 即可配合任意合规组件子集，不需要按选择重新编译，也不需要私有旧 APK。新 UI 要求 parent 实现只读 `preset.sh capabilities`；旧私有 1.7 parent 未实现时会禁止应用并提示升级。旧参考包开发路线见 [BUILD_SUITE.md](BUILD_SUITE.md)，其原有结构校验不替代新路线的源码证据核对或 parent 配套要求。

## 4. GUI 操作

1. 运行 `python3 launch.py`，选择 **「小米15 Ultra · OS4.0.0.6 完整1.7适配」**。
2. 选择精确 EEA 目标目录，导入精确 CN 来源目录及额外 APK。若输入完整 OTA，先明确执行对应的解包操作。
3. 选择自己的当前统一 APK 和配套证据；或使用「本地构建统一插件…」。缺依赖时自行离线准备，或显式点击「联网准备依赖」。
4. 分析材料。下列 11 行初始全部不选，按需勾选；`phone` 自动补齐 `market`，`xiaoai` 自动补齐 `assistant`。钱包只能单独手动勾选，不由批量全选加入。
5. 点「检查兼容性」，处理所有材料与证据阻断/缺项后，生成到源码目录外、尚不存在的新 ZIP。电脑选择同时确定生成包的部署计划：用户日后刷入时安装满足 guard 的所选组件。更改材料、插件或选择后重新检查，生成仍重读材料。实际 GUI 选择 market/assistant 已生成正确的自动部署计划，验证范围见 [AUTOINSTALL_VALIDATION.md](AUTOINSTALL_VALIDATION.md)。

| ID | 组件 |
| --- | --- |
| `market` | 小米应用商店 |
| `assistant` | 智能助理负一屏 |
| `xiaoai` | 超级小爱，依赖 `assistant` |
| `phone` | 电话、短信与录音，依赖 `market` |
| `gallery` | 相册与 AI 编辑 |
| `weather` | 天气与街道定位 |
| `disaster` | 自然灾害预警与报警定位 |
| `wallet` | 小米钱包与 NFC，必须单独手选 |
| `clock` | 时钟法定节假日 |
| `calendar` | 国行日历 |
| `mipush` | MiPush 推送配置 |

核对输出路径、大小、SHA256 和本次报告。配置、报告、原始验证日志及包含 OEM 材料的 ZIP 只留本地。公开发布的电脑源码 ZIP 不携带这些结果。

## 5. CLI 检查与生成

从工具根目录运行。以下选齐钱包以外的 10 项；这是显式的命令行选择，不是 GUI 默认值。可缩减组件列表，依赖自动补齐。`--source` 可重复指定已解包目录、APK 目录或单个 APK；文件输入不接受旧模块/参考 ZIP。

```sh
python3 tools/recipe_materials.py check \
  --target "/local/work/eea" \
  --source "/local/work/cn" \
  --source "/local/materials/weather-27.apk" \
  --source "/local/materials/securitycenter-13.6.5.apk" \
  --components market,assistant,xiaoai,phone,gallery,weather,disaster,clock,calendar,mipush \
  --unified-apk "suite/unified-api102/build/full17-local.apk"

python3 tools/recipe_materials.py build \
  --target "/local/work/eea" \
  --source "/local/work/cn" \
  --source "/local/materials/weather-27.apk" \
  --source "/local/materials/securitycenter-13.6.5.apk" \
  --components market,assistant,xiaoai,phone,gallery,weather,disaster,clock,calendar,mipush \
  --unified-apk "suite/unified-api102/build/full17-local.apk" \
  --output "/local/work/new-full17-nonwallet.zip"
```

示例额外 APK 仍须满足上面的精确 SHA；如果天气 23 或其他材料不在固件内，继续添加对应 `--source`。要包含钱包，须自己明确在 `--components` 中加入 `wallet`，例如放在 `disaster` 与 `clock` 之间。参数为空、重复或未知组件会拒绝。

检查结果 `state=blocked` 返回退出码 2，正常完成的材料检查为 `reviewed-raw-materials`；输入/工具错误返回 1。`check` 的 JSON 在标准输出，不因指定输出文件就自动保存报告。`build` 要求新 `--output`，成功 JSON 给出最终 ZIP 路径、字节数、SHA256、选择及 `device_tested=false` 等边界。该状态只说明材料与配方契约，不代表手机已安装或功能验收。

## 6. 手机安装与钱包边界

以下为 0.7.0 已通过核心 host 执行验证的部署契约，证据状态见 [AUTOINSTALL_VALIDATION.md](AUTOINSTALL_VALIDATION.md)。生成包保留 1.7 WebUI、各 Root 组件独立恢复入口与统一 API102 功能；catalog、能力列表及部署计划只覆盖电脑选定的组件和依赖。**电脑生成文件不操作手机；用户另行刷入 parent 才启动部署。**

1. 用户先核对精确 ROM、Root、Zygisk、modern API102 LSPosed、已启用并重启生效的 OverlayFS MetaModule 1.3.1，以及原有 APK/签名/哈希、用户及版本等 guard。安装不绕过这些门禁，不通过清应用数据或凭据来解决检查失败。
2. 刷入 parent 时安装统一插件，并同步安装电脑勾选且当前满足 guard 的组件。若电话依赖的商店需要先完成一次重启，先安装商店和其他当前可用的所选项，将电话留在该次固定部署计划中。
3. 用户**手动重启**后，有 pending 的 parent service 最多等待 `sys.boot_completed` 120 秒，再调用 `install-selected.sh resume`，仍由 resume 核对记录和 guard，仅针对该次固定计划续装电话；没有 pending 时只执行原有 reconcile。等待结束不等于真实启动行为已获设备验证。电话续装完成后还需再手动重启一次，使新挂载生效；首次从零部署可能需要两次手动重启。不自动重启，不建立持续重试的安装循环。
4. 被选项所需依赖未准备、guard 未通过或安装失败时停止并留日志，不自动反复重试。续装前发现手动 controller 任务已改变记录时，取消尚未完成的续装队列，避免稍后覆盖手动安装或恢复意图。helper 非零退出清 pending/ok 并持久记录失败；customize 会提示自动部署失败并保留 parent 供恢复，不 abort 父包安装。**父包安装成功不等于自动部署成功。**
5. Root 组件部署不写 `compat` 偏好，不代为启用 LSPosed 插件或授权作用域。用户仍须在 LSPosed 中启用统一插件并核对/授权作用域，按需在手机组件配置或兼容设置中明确应用配置。已安装不等于兼容开关已开启或业务功能可用。

原有数据和逐组件恢复入口保留；恢复仍遵循组件依赖和现有 guard，不能把逐项恢复理解为钱包、共享 UID 或密钥迁移的无损逆转。需要中断续装时，先按日志核对已完成项及待处理项，不能把停止当作整组回滚。

安装后须读取 parent 目录 `M/install-selected.result` 的 `state/selected/wallet/job`，有 job 时查看其日志。`M/install-selected.pending` 为包指纹、刷入 boot、上次 job、`phone` 四行记录；`M/install-selected.ok` 仅表示所选项部署完成且没有首次 EEA 钱包待确认。文件状态及失败含义见 [AUTOINSTALL_VALIDATION.md](AUTOINSTALL_VALIDATION.md#部署结果与恢复)。native KernelSU、真实 boot 续装及数据保留仍无本轮设备证明。

手机组件配置页仍通过只读能力 CSV 筛选包内组件与兼容预设选项，未打包项在该页不可选；该页默认选择包内钱包以外的组件和可用兼容，已有预设选择仅在内存中过滤。此默认值与电脑固定部署计划分别处理，不能把手机预设默认值当成续装指令。

capabilities 只限制本包的组件配置与安装，不是运行时 hook 门禁。省略某项不会卸载手机上已有的组件，也不会自动清除旧偏好或关闭其他页面的既有兼容开关。`UnifiedModule` 仍遵循已保存的 `compat` 配置，`SettingsActivity` 的独立开关仍可控制兼容；不能据此保证未打包项不运行。如需停用，须单独关闭相应兼容或恢复组件。

能力数据缺失、无效或依赖不完整时，组件配置页禁止应用及恢复默认，并提示检查 Root、完整性或升级 parent。新 parent 与新源码编译的插件必须配套。

钱包只有明确选择时才带 payload，批量全选不加入；桌面生成、刷入自动部署及电话续装都不创建首次 EEA 钱包 reset 授权。首次 EEA→CN TSM 迁移须延后到手机「组件配置」，由用户单独选择并作仅限一次安装任务的明确确认；不能把电脑勾选或重启当作确认。手机新配置仍默认不选钱包，先前保存的包内选择可沿用，但不会绕过本次确认。该迁移可能清除旧 TSM 数据及 UID 绑定密钥，旧卡可能失效。

若已有精确 CN TSM 就绪，明确选入的钱包可按原有 guard 自动安装，不重复清除数据或密钥；未知身份或不满足条件时停止，不改为自动 reset。保留普通 Root 恢复入口不保证能恢复卡片或凭据。

全局 XMSF 保持不变，不加入统一插件作用域。MiPush 路由/应用选择不自动开启；隐私协议、卡片、支付和真实业务验证需分别处理。本次文档与电脑构建工作不安排任何手机操作。

## 7. 与保留路线的区别

- 默认「其他机型 · 从目标固件识别」保留 0.5 通用受限候选能力：普通系统 APK、整组恢复，不自动获得完整 1.7 权限修复、WebUI 或逐项恢复，见 [USER_GUIDE.md](USER_GUIDE.md)。
- 标注「历史配方」的 1.4/精选入口仍要求精确旧材料，不用任意固件代替。
- `tools/build_suite.py` 与 [BUILD_SUITE.md](BUILD_SUITE.md) 保留作持有精确私有参考 ZIP 的开发路线。本文原始材料路线无需该 ZIP；不要把两条路线的输入、证据或安装兼容性混用。

公开产物仅为 **`XiaomiLocalSuite-Tool-0.7.0.zip`** 源码包；不携带 OEM APK/库/DEX、第三方 AAR/JAR、SDK、签名密钥或本地生成的手机安装 ZIP。发布和验证边界见 [RELEASE_TOOL.md](RELEASE_TOOL.md)。
