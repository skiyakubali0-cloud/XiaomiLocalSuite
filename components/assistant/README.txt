小米智能助理 25.40.31.00
Source: xuanyuan CN OS4.0.0.6 Android 17
Target: xuanyuan EEA OS4.0.0.6 Android 17
No boot/vendor replacement. No data clearing.
A same-version /data/app update is installed so Root hiding does not hide app resources.
Disable module and reboot to remove its system overlay. The app update remains installed and can be removed in Android app settings.
Package registration and successful UI startup are separate validation steps.
Native launcher adaptation: a hash-pinned copy of the current EEA Rust runtime library is overlaid. A 380-byte process guard returns the domestic-build flag only for com.miui.home when its private opt-in marker exists. Every other process follows the original code. The ROM region remains EEA.
Only the opted-in launcher process enables Android Bionic property overrides. Four shadow properties provide xuanyuan, cn, CN, and tier2 to that process. Global region and search properties remain unchanged. Disable module and reboot restores the original library and property.
Use module WebUI to switch; each switch restarts the launcher but preserves layout. No Zygisk or LSPosed hook is required by this module.
