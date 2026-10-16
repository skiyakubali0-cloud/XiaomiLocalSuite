#include "zygisk.hpp"
#include <android/log.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <stdint.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/system_properties.h>
#include <unistd.h>

// HyperOS 4's launcher uses Rust FFI, so the old Java route hook cannot run.
// Zygisk invokes this after fork. Only this child's private code pages change.
class AssistantRoute : public zygisk::ModuleBase {
    zygisk::Api *api = nullptr;
    JNIEnv *env = nullptr;
    void log(const char *message) {
        __android_log_write(ANDROID_LOG_INFO, "XuanyuanOS4Assistant", message);
    }
public:
    void onLoad(zygisk::Api *a, JNIEnv *e) override { api = a; env = e; }
    void preAppSpecialize(zygisk::AppSpecializeArgs *args) override {
        const char *name = env->GetStringUTFChars(args->nice_name, nullptr);
        const bool home = name && strcmp(name, "com.miui.home") == 0;
        if (name) env->ReleaseStringUTFChars(args->nice_name, name);
        if (!home) {
            api->setOption(zygisk::Option::DLCLOSE_MODULE_LIBRARY);
            return;
        }
        char value[PROP_VALUE_MAX] = {};
        __system_property_get("ro.build.version.incremental", value);
        if (strcmp(value, "OS4.0.0.6.XOAEUXM") != 0) {
            log("Skipped: firmware differs from tested EEA OS4.0.0.6");
            return;
        }
        const int dir = api->getModuleDir();
        const int flag = dir < 0 ? -1 : openat(dir, "use_china", O_RDONLY | O_CLOEXEC);
        if (dir >= 0) close(dir);
        if (flag < 0) { log("Original launcher route selected"); return; }
        close(flag);
        void *lib = dlopen("/system_ext/lib64/libhyper_os_core_system_private.dylib.so", RTLD_NOW | RTLD_LOCAL);
        if (!lib) { log(dlerror()); return; }
        auto *code = static_cast<uint32_t *>(dlsym(lib,
            "_RNvMs_NtCsc7SeBjxjCqd_28hyper_os_core_system_private5buildNtB4_11MiuiOsBuild22is_international_build"));
        const uint32_t expected[] = {0xd503245f, 0x900000a8, 0x91036108, 0x88dffd08};
        if (!code || memcmp(code, expected, sizeof(expected)) != 0) {
            log("Skipped: original Rust function does not match");
            return;
        }
        const long page_size = sysconf(_SC_PAGESIZE);
        if (page_size <= 0) return;
        void *page = reinterpret_cast<void *>(reinterpret_cast<uintptr_t>(code) & ~(static_cast<uintptr_t>(page_size) - 1));
        if (mprotect(page, page_size, PROT_READ | PROT_WRITE | PROT_EXEC) != 0) {
            log("Skipped: code page is not writable");
            return;
        }
        // Keep the BTI landing pad; return false without touching shared build flags.
        const uint32_t replacement[] = {0xd503245f, 0x2a1f03e0, 0xd65f03c0, 0xd503201f};
        memcpy(code, replacement, sizeof(replacement));
        __builtin___clear_cache(reinterpret_cast<char *>(code), reinterpret_cast<char *>(code) + sizeof(replacement));
        if (mprotect(page, page_size, PROT_READ | PROT_EXEC) != 0) {
            memcpy(code, expected, sizeof(expected));
            __builtin___clear_cache(reinterpret_cast<char *>(code), reinterpret_cast<char *>(code) + sizeof(expected));
            mprotect(page, page_size, PROT_READ | PROT_EXEC);
            log("Restored original code: cannot restore page protection");
            return;
        }
        log("China assistant route enabled only inside com.miui.home");
    }
    void preServerSpecialize(zygisk::ServerSpecializeArgs *) override {
        api->setOption(zygisk::Option::DLCLOSE_MODULE_LIBRARY);
    }
};
REGISTER_ZYGISK_MODULE(AssistantRoute)
