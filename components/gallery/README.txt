独立国行相册模块 1.1
仅支持 xuanyuan EEA OS4.0.0.6.XOAEUXM / API37，依赖 KernelSU 与 meta-overlayfs。
原始来源同型号 CN OS4.0.0.6.XOACNXM。相册5.4.2.4-0818-cn、插件5.4.2.3、编辑器2.10.40.3.1、特效2.2.1.0.1；全部保留OEM原签名。国行版本低于当前EEA，安装前自动备份四应用CE/DE目录并检查现有APK哈希与路径；仅放行包名匹配标准/data/app路径且SHA-256精确匹配的两个已验证更新；允许安装随机目录变化。其他更新或split APK仍停止，不强行降级。底层系统APK仍须匹配原EEA或CN哈希。
系统覆盖现有四个APK及私有native库，不修改全局地区、AI引擎、云账号或协议；不清照片、相册数据库、不修改MediaStore。不会安装持久/data/app更新。四应用的KernelSU配置设为不卸载模块挂载（allow_su仍false），防止国际版代码与国行资源混用；保存原配置，停用/移除后仅在配置未被用户更改时恢复。停用/移除模块并重启仅撤销模块挂载；保留现有 /data/app 相册及编辑器更新，不等于恢复完整国际版程序。不卸载更新、不覆盖数据库或照片。 备份数据恢复需单独评估，不能自动清数据。
AI消除、扩图、增强等以实机验证记录为准；功能入口不等于模型/云服务可用。需要下载的模型、联网协议、账号由用户处理。
执行按钮打开相册。测试只使用单独准备的测试图片，不覆盖原照片。
私有备份在/data/adb/xuanyuan-os4-gallery-state，不要随ZIP分享。

保留的更新（不包含在ZIP中；签名已由restore-round2记录验证）：
com.miui.gallery 5.4.2.10-0907-cn
SHA-256: 6a9c9677a6a6ef398c3d60dad58c71942adab010b8e4e7727b2c028063c3fd9d
com.miui.mediaeditor 2.10.40.4.8
SHA-256: e7c37c8ee2e10e8e45b60ad3ff293ad8a0b1c702f9e79aaa8df97ecfbcf4f699
OEM signer SHA-256: c9009d01ebf9f5d0302bc71b2fe9aa9a47a432bba17308a3111b75d7b2149025
