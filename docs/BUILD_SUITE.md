# 离线重建 1.7 Root suite

`tools/build_suite.py` 只重建 `materials.lock.json` 对应的单一参考 release：
小米 15 Ultra / `xuanyuan`、EEA `OS4.0.0.6.XOAEUXM`、Android 17 / SDK 37。
它使用 `suite/module` 和 `components/*` 的公开文本模板，生成包含 8 个子模块的 Root suite。
GUI 的多机型 0.4 流程不在此构建器范围内。

## 准备本地输入

- Python **3.11 或更高版本**，仅用标准库。
- 用户自行核对并合法持有的本地 `xuanyuan-os4-suite-1.7-wallet-selectable.zip`。
  整包 SHA256 必须等于 lock 的 `reference_suite.sha256`；文件名不参与身份判断。
- 用户自行构建和签名的统一兼容 APK。必须通过本地 Android SDK `apksigner verify`，
  编译后的 manifest 必须为包名 `local.xuanyuan.mipushcompat`、`versionCode=17`。
  构建来源和业务逻辑仍需用户核对；签名校验与这些结构检查不能证明任意 APK 的代码行为。
- 已安装的 Android SDK `apksigner`、`aapt2` 及其本地运行依赖（包括 Java）。
  可放在 PATH，也可通过 CLI 显式指定；构建器不会安装工具或下载依赖。

APK 必须包含唯一 modern Java 入口 `local.xuanyuan.unified.UnifiedModule`，
`META-INF/xposed/module.prop` 为 `minApiVersion=102`、`targetApiVersion=102`、
`staticScope=false`，且 `META-INF/xposed/scope.list` 为零字节。
禁止 legacy `assets/xposed_init` 或 native 入口。

**CLEAN-INSTALL ONLY：自签名可以不同，但不同签名不能覆盖升级原签名 APK。**
Android 会拒绝这类升级；构建器不会修改安装器来绕过签名检查，也不会卸载应用或清除数据。
已有安装、钱包凭据及数据迁移须由用户另行核对，本工具不执行这些操作。

## 运行

从公开源码根目录执行；所有材料和输出路径均由用户指定，无硬编码私人路径：

```sh
python3.11 -B tools/build_suite.py \
  --reference-suite "/local/private/reference-1.7.zip" \
  --unified-apk "/local/private/caller-signed-code17.apk" \
  --apksigner "/local/android-sdk/build-tools/36.0.0/apksigner" \
  --aapt2 "/local/android-sdk/build-tools/36.0.0/aapt2" \
  --output "/local/private/new-suite-1.7.zip"
```

Windows 使用本机等价路径、`apksigner.bat`、`aapt2.exe` 和 Python 3.11+；
上述多行示例的反斜杠是 POSIX shell 续行符，PowerShell 中请改为单行命令。
CLI 支持带空格的路径，内部通过参数数组调用工具，不拼接 shell 命令。
可用 `--source-root "/local/public-source"` 指定包含 lock 和模板的源码目录；
默认使用脚本所在仓库，不依赖运行时工作目录。

`--output` 必须是尚不存在的新 `.zip` 路径；不会覆盖现有文件或 symlink。
成功后输出产物路径和整包 SHA256。校验或打包失败时不创建最终输出。
构建使用系统临时目录暂存参考包、材料和生成文件，需要数 GiB 空闲空间；
正常退出及异常处理结束后自动清理临时目录，强制终止进程后的残留由用户清理。

## 材料与 hash 更新规则

1. 对指定参考 ZIP 创建临时快照，校验整包 SHA256 后才使用内容。
2. 检查父 ZIP、逐个读取的 8 个子 ZIP 和新 APK 的所有成员，包括不会复制的成员：
   拒绝重复成员（含大小写别名）、绝对路径、`..`、反斜杠/驱动器路径、
   Windows 保留设备名及尾随点/空格、symlink、特殊文件和文件/目录冲突。
   子 ZIP 逐个复制到临时文件后读取；不把所有组件 ZIP 同时加载到内存，也不直接 `extractall`。
3. 仅复制 lock 明确列出的缺失材料，逐项核对 `component`、`path`、`bytes`、`sha256`。
   当前 lock 共 215 项，包含原统一 APK；原 APK 同样校验后，再用调用者指定的 APK 替换。
   其他所有锁定二进制逐字节保留，参考 ZIP 中的旧文本脚本和额外材料不复制。
4. 只更新父 `shared.sh` 的当前 `UNIFIED_SHA`、`migrate-legacy.sh` 的 `SELF_SHA`，
   以及 `catalog.sh` / `webroot/catalog.json` 对应条目的 SHA 和 bytes。
   `shared.sh` 保留全部历史 APK allowlist，并将原当前 APK hash 留在 allowlist 中。
   不对整个模板做 hash 全局替换，不改 `sourceSha256` 等来源记录。
5. 小爱 `privacy.sh` 保留历史 allowlist 并追加新 APK hash；计算其新 hash，更新父
   `customize.sh` 的精确配套分支。旧 `2026101603` privacy 也进入配套更新，
   新 privacy 精确匹配后无需再次配套。原 `2026101602` 配套分支保留。
6. 重建 8 个子包及其 `checksums.sha256`；父 catalog 更新实际子 ZIP 的 SHA 和 bytes。
   父 `control.sha256` 覆盖除 `customize.sh` 外的控制文本文件，
   父 `checksums.sha256` 覆盖其他所有最终文件，包含 `control.sha256`。
7. 输出固定时间戳的 DEFLATE ZIP，使用经典 local header，禁用 ZIP64/forceZIP64，
   每个子 ZIP 与最终父 ZIP 均小于 2 GiB。文件布局直接以 `module.prop`、`customize.sh`
   为根，不套额外目录。源码和输入文件均不修改。

原机型/ROM/单用户/Root guard 保留。钱包单次确认、boot + hash 授权、
已有 CN 数据不 clear、XMSF 不修改的脚本逻辑均原样保留。
构建器不运行手机脚本，不扫描手机，不调用 ADB，不访问网络。
公开模板作者或个人路径脱敏可以保留；兼容性 hash 字段必须继续与 lock 契约一致。

## 本地测试与发布边界

```sh
python3.11 -B -m unittest discover -s tools -p test_build_suite.py -v
```

测试使用公开文本模板、synthetic ZIP/二进制和注入的 APK checker，
不需要真实 OEM、SDK、手机或网络。SDK checker 的签名失败和包名/版本拒绝另以 mock 验证。
测试检查危险父/子 ZIP、整包 SHA、材料 SHA/大小/缺失、模板覆盖冲突、旧输出保护、
精确二进制保留、hash 配套、完整 checksums 和实际 ZIP local header。
synthetic 测试成功不代表真实 APK 签名验证、完整私有构建或设备安装已通过。

生成 ZIP 包含用户私有材料，**仅供本地使用，不发布、不上传到仓库或 release**。
仓库维护者须确保 `.gitignore` 包含 `*.zip`；建议输出到仓库外的私有目录。
本工具只生成用户指定的本地 ZIP，不执行 git、推送、上传或发布。
