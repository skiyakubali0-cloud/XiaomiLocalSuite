小米本地化电脑工具 0.7.0 · 预览版

完整中文GUI/CLI教程：解压包根目录 docs/USER_GUIDE.md。
发布与源码打包说明：docs/RELEASE_TOOL.md。
发布页：https://github.com/skiyakubali0-cloud/XiaomiLocalSuite/releases/tag/tool-v0.7.0
工具附件：XiaomiLocalSuite-Tool-0.7.0.zip，是电脑源码工具，不是手机模块、签名DMG或独立EXE。

启动（进入解压后的工具根目录）
  python3 launch.py --check
  python3 launch.py
启动器：launchers/macOS.command、launchers/linux.sh、launchers/windows.cmd。
需自行安装Python3.11+、Tk8.6+、JDK17+、Android SDK build-tools36.0.0的aapt2/apksigner。
--check只检查Python/Tk运行时与核心导入，不打开窗口、不运行外部程序；Java/SDK及可选解包工具用GUI“环境检查”核对。
GUI“使用教程”只读打开离线docs/USER_GUIDE.md。依赖仅由用户显式准备，不自动接受许可；电脑生成不使用ADB、安装或重启手机。
实际214/214材料、完整11组件ZIP、GUI部分包、52份脚本及父子校验和已通过核对；新增22项自动部署执行测试及现有回归通过。
完整包1,101,469,378字节，GUI商店/智能助理包68,561,763字节；无私有参考ZIP。
主机执行不代替native KSU、OverlayFS、真实boot/service和数据保留验证；本轮未安装手机。
详细验证及部署结果读取方法：docs/AUTOINSTALL_VALIDATION.md。最终CI和源码ZIP摘要核对对应Release。
原生Windows完整流程未就绪，建议WSL2配合GUI及Linux依赖。

默认：其他机型 · 从目标固件识别
1. 目标选EEA完整OTA或含同版本真实build.prop及原始APK的已解包固件目录。
2. 来源选同机型国行OTA/目录，或“添加APK”选择多个文件；来源只有APK时仍须目标固件目录。
3. 工作目录选大容量外接磁盘；OTA显式点击“解包OTA”，需payload-dumper-go及fsck.erofs。
   分析不会自动解包。完整payload/EROFS可能占数十GiB或更多，空间不足停止；不自动转换增量OTA/fastboot TGZ/ext4/sparse。
4. 分析材料→核对机型/ROM/SDK/ABI→勾选（默认全不选）→检查兼容性→生成候选ZIP。
5. 选择未占用的新输出名，核对ZIP与同名.build.json；更换材料/选择后重新检查，生成时仍重读实际材料。

默认流程不需要旧1.4，不从任意固件复原全部1.7功能。
只接受目标已有、同签名、非split的普通系统APK候选挂载，不任意新增特权应用。
不包含统一API102插件、权限修复或已有1.7 WebUI，不推断SELinux、依赖或LSP钩子。
新增权限/依赖、签名差异、共享UID不匹配、降级、ABI/SDK不兼容等会阻断。
关键框架、电话底层、securitycenter/手机管家、launcher/桌面、钱包/TSM/eSE/NFC、全局XMSF不走通用路线。
candidate-static-pass只表示静态通过，不是国行功能、手机运行、云端AI、通知送达或支付/门卡验收。

候选安装与恢复
用户若另行评估，需KernelSU、已启用且重启生效的OverlayFS1.3.1，以及精确机型/ROM/单用户0/当前APK路径及SHA guards。
一个候选内多选APK属于同一恢复组：在KernelSU禁用该模块并手动重启，一起恢复覆盖的APK。
要分别恢复，每次只选一个APK，用不同配置标识分别生成模块；通用候选没有1.7逐项WebUI恢复。
更改同一候选选择前先卸载原候选并重启，避免未选APK残留。
OTA前禁用候选并重启，升级后重读目标固件；启动版本检测不能代替OTA前停用。
不自动清数据/卸载更新来绕过检查，不生成钱包reset，不重置Keystore或迁移凭据，不改全局XMSF。

CLI（工具根目录；示例路径/虚构包名须替换）
  python3 suite/multi-device/suite_builder.py inspect "/local/materials/target-eea.zip"
  python3 suite/multi-device/suite_builder.py extract "/local/materials/target-eea.zip" --out "/local/work/target" --partitions product,system_ext,system
  python3 suite/multi-device/suite_builder.py init --id "exampledevice-os4-build1" --target "/local/work/target" --source "/local/work/source" --out "/local/work/draft.json"
  python3 suite/multi-device/suite_builder.py select --profile "/local/work/draft.json" --packages "com.example.app" --out "/local/work/selected.json"
  python3 suite/multi-device/suite_builder.py check --profile "/local/work/selected.json" --out "/local/work/check.json"
  python3 suite/multi-device/suite_builder.py build --profile "/local/work/selected.json" --candidate --out "/local/work/exampledevice-candidate.zip"
来源目录也要事先准备；可另行extract来源OTA，或用APK目录/单APK作为init的--source。
--packages逗号分隔；-表示全部取消。检查state=blocked时退出码2，不能生成候选。
已有解包目录不需extract，目标固件目录不能用来源APK替代。详细依赖、WSL2与排错见完整教程。

精确小米15 Ultra 完整1.7适配（新入口）
1. 选择“小米15 Ultra · OS4.0.0.6 完整1.7适配”，目标为xuanyuan EEA OS4.0.0.6.XOAEUXM、SDK37、arm64-v8a。
2. 导入同机型OS4.0.0.6.XOACNXM材料及配方锁定的额外APK；OTA先解包。无需私有参考ZIP。
3. 用当前公开源码、本机SDK和自己的密钥构建统一API102插件；GUI“本地构建统一插件”提供入口。
   缺依赖时显式准备锁定的AAR/JAR，不自动下载OEM材料、SDK或接受许可。
4. 分析后11种组件默认全不选，按需勾选；小爱自动补智能助理，电话自动补商店。批量全选跳过钱包，钱包须单独手选。
5. 检查材料/原生补丁/源码构建证据并生成本地精选1.7 ZIP；缺项显示APK包名、版本码和精确SHA。
6. 以下为0.7.0已通过核心host执行验证的部署方案：电脑只生成文件；用户另行刷parent时同步部署电脑固定选择中满足guard的组件及统一插件，保留数据与独立恢复。
   电话若需商店先重启，先装商店及其他可用项；用户手动重启后parent service仅续装该次固定计划的电话。
   依赖未准备、guard或安装失败时停止并留日志，不自动反复重试；用户启动手动controller任务时取消待续装队列。
   不自动重启、不写compat偏好、不代为启用LSPosed或授权作用域；安装后用户仍须单独配置兼容。
   父包安装成功不等于自动部署成功：helper失败清pending/ok并记录failed，customize提示失败但保留parent供恢复，不abort父包。
   查看parent目录install-selected.result的state/selected/wallet/job及job日志；ok仅在所选项完成且无EEA钱包待确认时写入。
   pending为指纹/boot/上次job/phone四行；service无pending仅reconcile，有pending等sys.boot_completed最多120秒后resume。
7. 首次EEA→CN TSM钱包迁移不随刷入或续装直接reset，须延后到手机“组件配置”单任务明确确认；确认可能清TSM数据及绑定密钥。
   已有精确CN TSM就绪时，明确选入的钱包可按guard自动安装，不重复清除；未知身份停止。
   能力CSV只限制本包配置/安装，不控制运行时hook；省略不卸载已有组件、不清偏好或关闭其他页面开关，停用须单独关闭或恢复。
   不改全局XMSF，不代操作支付或卡片。不能把“生成成功”当成功能或支付/门卡验收；本轮不安装手机。
本地自签名APK不能覆盖旧私人签名；当前手机升级不能直接刷新签名包。请先核对签名和数据迁移。
精确输入、离线/联网依赖准备与完整GUI/CLI教程：docs/FULL_RECIPE.md。

历史入口与1.7
“历史配方...”完整1.4/精选模式只供持有精确原1.4套件的用户；只有这些入口要求旧包。
历史精选保留商店/智能助理/小爱依赖和精确安装门禁，不能拿任意新机型材料代替。
旧参考包重建接口见docs/BUILD_SUITE.md；该旧接口需要私有1.7参考包，新完整适配入口不需要。
工具0.7.0、历史配方1.4、手机套件1.7是不同版本体系。

公开边界
公开工具ZIP不含OEM材料、第三方依赖二进制、密钥、用户数据、截图或原始验证日志。
生成的通用候选、完整或部分1.7 parent含OEM材料，只留私人工作目录，不上传GitHub仓库、Issues、PR、Releases。
配置、.build.json、诊断可能涉及本地路径，均留私有工作目录。
没有新机型实机或原生Windows完整流程兼容承诺，功能需在精确系统上逐项验证。
