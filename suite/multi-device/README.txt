小米本地化套件多机型构建工具 0.4 · 图形界面


现有适配模块精选：刷入时自动安装（0.4 / 父模块1.5-selected）
选择“小米15 Ultra · 刷入自动安装精选（不含钱包）”，选择原始xuanyuan-os4-suite-1.4.zip。
按需勾选商店、智能助理、小爱；小爱依赖智能助理。GUI检查并生成新ZIP，生成过程不连接或安装手机。
真正刷入新ZIP时：统一预检→按商店、智能助理、小爱顺序同步交给KernelSU安装原子ZIP→记录结果，不需再进WebUI安装。
子模块ZIP和统一API102 APK保留原字节。只选择商店/助理不安装共享APK；含小爱才安装/保留该APK，不重置其数据。
仅限xuanyuan EEA OS4.0.0.6.XOAEUXM / Android17 API37 / 单用户0，需要已启用且重启生效的OverlayFS 1.3.1；小爱另需Zygisk/API102 LSPosed。
开始前检查ROM、运行库、桌面版本、AI引擎与框架、元模块、未完成任务/更新以及负载哈希。未知版本或待重启会阻止本轮安装。
中途失败停止后续步骤并使父安装报错；已完成的子模块或共享APK可能仍已安装/暂存，不自动删除数据或回滚成功步骤。
日志与逐项started/completed记录保留在/data/adb/xuanyuan-os4-suite-state/jobs/flash-*；失败后先核对记录，勿盲目重复安装。
成功后由用户手动重启以激活挂载；LSPosed插件、作用域、兼容开关、协议/登录仍需用户配置，不自动重启或接受协议。
钱包/TSM/eSE/NFC负载始终不在精选包中，不操作卡片/凭据、不改全局XMSF。未勾选的既有子模块不自动卸载。
WebUI继续支持以后单独恢复/重新安装；旧插件迁移/恢复写入仍拒绝，保留真实迁移状态检查。仍有旧插件时，先单独处理再刷本包。
原统一API102 APK保留完整设置入口；本精选包不保证其所有手动入口只影响三项功能。不要使用完整11项预设或迁移按钮。
本轮仅主机脚本/命令替身、原KSU安装器嵌套临时目录测试与源码核对；不宣称真实Android KSU、OverlayFS、重启或全新系统验收。
此前0.3/1.4-selected仍需进WebUI安装，其旧ZIP保持不变；0.4生成的1.5-selected才采用刷入时同步安装。


启动
Mac解压工具ZIP后，双击“启动图形界面.command”。当前电脑已准备可正常绘制窗口的Python3.13.13 + Tk9.1。
图形界面需要带Tk8.6+的Python3.9及以上。Mac自带旧Tk8.5会显示空白，因此启动器会跳过它。
新电脑若缺少环境，可安装Homebrew的python-tk@3.13后再次双击；工具本身不自动下载或接受许可。
其他已有Tk环境的系统可运行 python3 gui.py；本轮只验证Mac真实窗口，不宣称Windows/Linux图形实测。
命令行构建核心保持0.1及原校验规则，下面保留完整命令行说明。

界面操作
1. 机型配置：选择“小米15 Ultra · EEA OS4.0.0.6（完整1.4）”，或“其他机型 · 从目标固件识别”。
   也可“打开配置”载入之前保存的JSON；导入配置不会自动生成或安装。
2. 已验证1.4：选择原始xuanyuan-os4-suite-1.4.zip，点击检查兼容性，再导出完整包。
   完整1.4按原字节导出，电脑端不裁剪组件；组件与兼容功能安装后仍在手机中按需勾选。
3. 新机型：选择目标系统ZIP或已解包目录；选择同机型国行ZIP、APK目录，或“添加APK”选择多个文件。
   选择OTA后，先点击对应“解包OTA”，会显式检查工作目录空间，再创建新的解包目录。
   已解包目录和单APK无需重复解包。工作目录建议外接磁盘，完整解包可能需约46GB或更多。
4. 点击“分析材料”，读取真实机型、ROM、SDK、ABI和APK。新配置标识使用英文、数字、点或横线。
   新机型默认不勾选。点击列表第一列方框或选中行后按空格，按需选择组件。
   “选择可用项”跳过钱包锁定项；缺少新权限或依赖等问题仍需兼容检查，不能靠全选绕过。
5. 点击“检查兼容性”。通过后才可生成；新机型按钮标明“生成候选ZIP”，不冒充已实测安装包。
   修改材料、机型或组件会作废原检查。生成前仍从实际文件重新检查，不信任旧报告。
6. 选择一个新ZIP输出位置，不覆盖旧安装包。结果显示完整路径、大小、SHA及对应.build.json。
7. 可以“保存配置”和“保存报告”，下次重新打开配置后仍须检查当前文件。
   多APK的全部路径、已选组件和原1.4材料位置会保留，不保存钱包或推送凭据。

后台与钱包
扫描、解包和生成在后台运行，窗口显示进度；期间锁定输入，任务完成后再关闭，避免不完整输出。
钱包/TSM/eSE/NFC在新机型列表中固定为单独验证，不能通过全选、打开旧配置或手工勾选自动启用。
已验证1.4完整材料里的钱包继续沿用原单独验证门槛；不生成reset标记、不清数据、不重置Keystore，
不迁移私人凭据、不操作卡片或支付，也不改全局XMSF。没有连接或修改手机。
OTA前仍须先禁用候选模块并重启，不把post-fs-data调度检测当成严格挂载门禁。

测试与范围
通过原80项构建/导入测试、新增会话状态测试及真实Tk窗口控件流程测试。
真实签名测试APK已通过界面“分析→勾选→检查→生成”，文件选择返回值由夹具提供；可见窗口另用桌面截图核对。
已验证多输入配置加载、钱包锁定、旧报告失效、后台任务锁定与错误恢复。现有手机和1.4稳定包未改动。
完整国行功能或LSP钩子仍需对应机型单独适配，新机型包保持候选状态；没有第二种机型实机验证。

0.2.1 实际固件与原生界面验证（2026-10-15）
用现有xuanyuan EEA/CN OS4.0.0.6 OTA的原始分区文件和APK实际操作。
修复通用分区名miproduct/missi被误认为机型的问题：依据init属性加载与产品属性优先级识别xuanyuan，保留歧义拒绝。
Mac Tk9原生JSON筛选曾将JSON置灰；“打开配置”增加“所有文件”回退项，内容仍完整校验。
若JSON不可选，点击文件选择框“Show Options”，筛选切换“所有文件”，再选择JSON。
实际通过原生文件对话框打开材料配置，点击分析，以键盘勾选通知管理、检查并生成12,341,194字节候选ZIP，保存配置/通过与阻断报告。
通知管理CN与EEA APK完全相同，只证明流程，不增加国行功能，不建议为此单独安装。
常用语CN版本10270低于EEA10272，界面明确拒绝降级并禁用生成按钮；取消后重新检查通过。
悬浮球新增特权权限、日历新增50项请求权限，仍被静态规则拦截，不自动转为已验证移植。
116项回归通过。真实GUI操作使用原生键盘和文件选择框，无伪造路径返回或按钮invoke。
没有连接或修改手机；钱包数据、凭据及全局XMSF未动。候选包不替代完整1.4套件。

———————————————— 命令行核心与原安全规则 ————————————————

小米本地化套件多机型构建工具 0.1

这是电脑端离线导入、检查、生成工具，不是刷入手机的Root模块。
现有稳定1.4安装包及手机配置没有修改。一个配置精确对应一个机型、一个ROM；不通过通配符跨机型放行。

目前可用的两条路径
1. 已审阅完整套件：内置 xuanyuan / EEA OS4.0.0.6.XOAEUXM / API37 配置。
   校验原1.4 SHA与全部ZIP成员后按原字节导出，保留原一个API102 LSP入口、手机端勾选及组件独立恢复。
2. 新机型或新APK：导入目标系统和来源材料，生成独立配置，按包名选择，检查后生成APK挂载候选包。
   候选仅适用于目标固件中已存在、同签名、非分包的普通系统APK；不是全功能国行移植。
   新增权限/依赖、分包、降级、签名差异、电话底层/系统框架/手机管家/桌面等关键组件会被阻止。
   需要这些适配时须新增该机型的已审阅配方，不能只修改device、API102或SHA来绕过。
   新机型未做实机验收；--candidate仅表示明确生成静态检查候选，不会把它标为已验证。

环境
Python3.9及以上；Android SDK build-tools的aapt2、apksigner及其Java运行环境。
自动从ANDROID_SDK_ROOT、ANDROID_HOME、常见SDK位置及PATH查找工具；不自动下载或接受许可。
OTA完整解包另需本机payload-dumper-go和fsck.erofs（EROFS）。默认取product、system_ext、system。
支持单APK、APK目录、已解包固件目录、含payload.bin的OTA ZIP。
fastboot TGZ、增量OTA、ext4/sparse镜像、split APK整套安装不自动转换；无法判断时停止并报告缺项。
建议使用大容量外接磁盘：完整解包需容纳分区镜像与解包树，打包需约两倍输出空间；不要放在系统盘。
不读取手机ADB、不改变当前手机、不执行输入材料中的脚本、不打包个人目录或私钥。
APK证书验证不代表固件来源真实性；请使用可信来源固件。未验证来源会保留unknown说明。

使用（先在终端进入本工具目录；python3需为3.9+）

A. 复用当前已验证1.4
  python3 suite_builder.py check --profile profiles/xuanyuan-eea-os4.0.0.6.json --materials "/你的1.4安装包目录" --out "/工作目录/1.4检查.json"
  python3 suite_builder.py build --profile profiles/xuanyuan-eea-os4.0.0.6.json --materials "/你的1.4安装包目录" --out "/工作目录/小米15Ultra-1.4.zip"
原包名须为xuanyuan-os4-suite-1.4.zip。生成包SHA与原1.4完全一致；已经安装1.4不需要重复安装。
工具ZIP不内含约1.12GB原套件，需自行保留原套件及工具ZIP。

B. 查看固件/APK
  python3 suite_builder.py inspect "/材料/目标EEA固件.zip" --out "/工作目录/目标固件元数据.json"
  python3 suite_builder.py inspect "/材料/来源.apk" --out "/工作目录/APK分析.json"
OTA只检查元数据和文件SHA，尚未提取APK时不会声称APK兼容。

C. 必要时显式解包（新目录，不覆盖旧目录；可能需要数十GB空间）
  python3 suite_builder.py extract "/材料/目标EEA固件.zip" --out "/工作目录/target" --partitions product,system_ext,system
  python3 suite_builder.py extract "/材料/同机型国行固件.zip" --out "/工作目录/source" --partitions product,system_ext,system
已解包的目录可直接使用；source也可以直接使用单APK或APK目录，不必再放完整国行包。
目标固件目录必须含真实build.prop与原始APK，供核对机型/ROM/ABI、签名、路径和哈希。
不要混合不同版本的build.prop与APK；元数据冲突或缺失会阻止生成。

D. 新建配置、选择组件、检查
  python3 suite_builder.py init --id "exampledevice-os4-build1" --target "/工作目录/target" --source "/工作目录/source" --out "/工作目录/draft.json"
默认所有新组件关闭。draft.json列出发现的包名、原APK、目标位置、SHA及缺项。
  python3 suite_builder.py select --profile "/工作目录/draft.json" --packages "com.example.app,com.example.other" --out "/工作目录/selected.json"
--packages - 表示全部取消。使用真正的包名，以上com.example仅是示例。
  python3 suite_builder.py check --profile "/工作目录/selected.json" --out "/工作目录/check.json"
通过状态candidate-static-pass；阻止时state=blocked，errors说明原因，退出码2。元数据缺失不当成通过。

E. 生成候选包
  python3 suite_builder.py build --profile "/工作目录/selected.json" --candidate --out "/工作目录/机型-ROM-候选.zip"
输出ZIP及同名.build.json（目标范围、材料SHA、生成SHA、未实测状态）。不接受旧检查报告代替重读材料。
输出文件、已有配置和记录不覆盖；重跑用新文件名。
ZIP内APK保持原始签名与字节；只包含所选APK、安装检查、无私人路径的清单、校验和说明。
候选安装需KernelSU和已生效OverlayFS 1.3.1元模块（仅此版本已审阅）。安装前精确检查机型/ROM/单用户0、当前APK路径和SHA。
应用商店更新造成/data/app活动APK、分包或哈希不同会阻止安装，不自动卸载更新或清理数据。
OTA前必须先禁用候选模块并重启，升级后重新导入目标固件检查。
候选提供post-fs-data机型/ROM检测并请求禁用自身，但KSU共享35秒调度截止后可能异步执行；
这不是挂载路径上的强制拦截，不能代替OTA前停用，也不宣称可带着候选模块跨ROM升级。
不写权限、默认角色、LSPosed数据库或兼容开关，不自动重启。
重新生成同一配置的不同选择前，须先卸载原候选模块并重启；已有镜像内容会阻止覆盖，避免未选APK残留。
候选包内所选APK一起恢复：KernelSU禁用该模块，再重启。若需要逐项恢复，每次只选一个组件分别生成包。
完整手机端勾选及独立恢复目前仅在已验证1.4配方中提供，新机型候选不借用旧LSP钩子。

钱包边界
钱包/TSM/eSE/NFC不允许进入通用APK挂载配方。不会自动生成reset标记、pm clear、密钥清理或凭据迁移。
已审阅1.4仍保持原钱包单独验证：首次迁移待处理，不影响其他组件按规则继续。
不改全局XMSF，不迁移推送注册凭据，不自动接受应用协议，不做支付、卡片、呼叫或报警测试。
将来其他机型的钱包必须另行匹配硬件、vendor/NFC/TSM与凭据方案；APK导入成功不表示可用。
刷机本身若清除数据，可能影响钱包凭据；工具不重置不等于抹机保留卡片。

验证
单元测试、真实SDK签名APK的完整CLI导入/选择/检查/生成、真实国行OTA元数据、原1.4原字节导出分别记录。
未在另一机型安装，未抹机重装，未测试新钱包/支付/卡片。真实功能需在对应机型逐项验证。
运行测试：python3 -m unittest -v test_builder test_intake test_integration
测试签名私钥只在临时目录中生成并删除，不进入工具ZIP或手机候选ZIP。
