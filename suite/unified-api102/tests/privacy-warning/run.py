#!/usr/bin/env python3
"""Compile real API102/Reflect and execute host interceptors; never contacts a device."""
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
ANDROID = Path(os.environ.get("ANDROID_SDK_ROOT", "/opt/homebrew/share/android-commandlinetools")) / "platforms/android-36/android.jar"
API = PROJECT / "deps/api.jar"
SOURCES = PROJECT / "src/local/xuanyuan/unified"
PINS = {
    "services": "cef17afe99cfa6396922e2fe1dce6642ec86ddcf141589b8ef4d007d6920ecdb",
    "framework": "55f69e60be40e1daf88fed21d4bb21cc82410497af329c61ea65df469dbaca30",
    "apk": "f3d338484cc5fd3f3fec9e8d9d0b4c6370923fba0f5e0d81975a45e914cbc776",
    "dex": "bd7b96b1aa2d3fa7b5f3a5200f39e16077636b0081f6df2c7201db47948d8d46",
}

# Only host framework fixtures. No replacement Xposed API or production Reflect.
FIXTURES = {
    "android/os/Build.java": '''package android.os;
public class Build { public static String DEVICE="xuanyuan";
 public static class VERSION { public static int SDK_INT=37; public static String INCREMENTAL="OS4.0.0.6.XOAEUXM"; } }''',
    "android/os/Binder.java": '''package android.os;
public class Binder { public static int uid; public static int getCallingUid() { return uid; } }''',
    "android/os/ParcelFileDescriptor.java": "package android.os; public class ParcelFileDescriptor {}",
    "android/util/Log.java": "package android.util; public class Log { public static final int INFO=4, WARN=5; }",
    "android/content/SharedPreferences.java": "package android.content; public interface SharedPreferences {}",
    "android/content/pm/ApplicationInfo.java": '''package android.content.pm;
public class ApplicationInfo { public int uid; public String sourceDir; }''',
    "android/content/pm/PackageManager.java": '''package android.content.pm;
public class PackageManager {
 public static boolean missing; public static String requested;
 public ApplicationInfo getApplicationInfo(String name, int flags) throws Exception {
  requested=name; if (missing) throw new Exception("not installed");
  ApplicationInfo info=new ApplicationInfo(); info.uid=10123; return info;
 } }''',
    "android/content/Context.java": '''package android.content;
public class Context { public android.content.pm.PackageManager getPackageManager() {
 return new android.content.pm.PackageManager(); } }''',
    "android/app/ActivityThread.java": '''package android.app;
public class ActivityThread {
 public static String process="com.miui.securitycenter"; public static boolean fail;
 public static String currentProcessName() { if(fail) throw new IllegalStateException("unavailable"); return process; }
}''',
    "miui/os/Build.java": "package miui.os; public class Build { public static boolean IS_INTERNATIONAL_BUILD=true; }",
    "com/miui/server/SecurityManagerService.java": '''package com.miui.server;
public class SecurityManagerService {
 public android.content.Context mContext=new android.content.Context();
 public Object mAiPrivacy, mSecurityWriteHandler=new Object();
 public SecurityManagerService() {} public SecurityManagerService(int ignored) {}
 public boolean accessAppsContentEnable(String pkg,int uid) { return false; }
 public boolean accessAppsContentEnable(String pkg,int uid,int extra) { return false; }
 public boolean accessAppsControlEnable(String pkg,int uid) { return false; }
 public void updateAppContentEnable(int uid,boolean enable) {}
 public void updateAppControlEnable(int uid,boolean enable) {}
 public boolean shouldDisplayInAISetting(String pkg,int uid) { return false; }
 public void enforceNotInternationalBuild() {}
 public void checkGrantPermissionPkg(String pkg) {}
 public void enforcePackage(String pkg) {}
 public static class LocalService {
  public boolean accessAppContentEnable(int uid) { return false; }
  public boolean accessAppControlEnable(int uid) { return false; }
 } }''',
    "com/miui/server/security/AgentPrivacyService.java": '''package com.miui.server.security;
public class AgentPrivacyService {
 public static int calls; public static boolean fail;
 public AgentPrivacyService(android.content.Context context,Object handler) {
  calls++; if(fail) throw new IllegalStateException("optional init");
 } }''',
    "com/miui/server/security/AgentPrivacyUtils.java": '''package com.miui.server.security;
public class AgentPrivacyUtils { public static boolean shouldSkipAIPermissionCheck(android.content.Context c,int uid) { return true; } }''',
    "com/android/server/input/InputManagerServiceStubImpl.java": '''package com.android.server.input;
public class InputManagerServiceStubImpl { public boolean shouldCheckPermission(int uid) { return false; } }''',
    "dalvik/system/InMemoryDexClassLoader.java": '''package dalvik.system;
public class InMemoryDexClassLoader extends ClassLoader {
 public static int calls; public final PathList pathList=new PathList();
 public InMemoryDexClassLoader(java.nio.ByteBuffer dex,ClassLoader parent) { super(parent); calls++; }
 public static class PathList { public Object[] dexElements={"donor-first","donor-second"}; }
}''',
}


def rewrite_utf8(path, replacements):
    """Redirect fixture paths/pins in compiled host copies, never the source/build."""
    data = path.read_bytes()
    out = bytearray(data[:10])
    count = struct.unpack_from(">H", data, 8)[0]
    offset, index = 10, 1
    sizes = {3: 4, 4: 4, 5: 8, 6: 8, 7: 2, 8: 2, 9: 4, 10: 4,
             11: 4, 12: 4, 15: 3, 16: 2, 17: 4, 18: 4, 19: 2, 20: 2}
    while index < count:
        tag = data[offset]
        out.append(tag)
        offset += 1
        if tag == 1:
            size = struct.unpack_from(">H", data, offset)[0]
            offset += 2
            value = data[offset:offset + size]
            value = replacements.get(value, value)
            out.extend(struct.pack(">H", len(value)))
            out.extend(value)
        else:
            size = sizes[tag]
            out.extend(data[offset:offset + size])
        offset += size
        index += 2 if tag in (5, 6) else 1
    out.extend(data[offset:])
    path.write_bytes(out)


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True)


privacy = (SOURCES / "PrivacyHooks.java").read_text()
warning = (SOURCES / "WarningHooks.java").read_text()
payload = PROJECT / "src/local/xuanyuan/disastercompat/Payload.java"
for pin in (PINS["services"], PINS["framework"]):
    assert pin in privacy
assert PINS["apk"] in warning and PINS["dex"] in payload.read_text()
for source in (privacy, warning):
    assert "de.robv.android.xposed" not in source and "XC_MethodHook" not in source

with tempfile.TemporaryDirectory(prefix="host-", dir=HERE) as directory:
    temp = Path(directory)
    classes, boot, mounts = temp / "classes", temp / "boot", temp / "mounts"
    for path in (classes, boot, mounts):
        path.mkdir()
    fixture_paths = []
    for name, content in FIXTURES.items():
        path = temp / "fixtures" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        fixture_paths.append(path)
    run("javac", "-encoding", "UTF-8", "-d", boot, *fixture_paths)
    # Exact class-name fixtures with one required method name removed per attempt.
    missing = temp / "missing"
    missing.mkdir()
    required = {
        "com/miui/server/SecurityManagerService": ["accessAppsContentEnable", "accessAppsControlEnable",
            "updateAppContentEnable", "updateAppControlEnable", "shouldDisplayInAISetting",
            "enforceNotInternationalBuild", "checkGrantPermissionPkg", "enforcePackage"],
        "com/miui/server/SecurityManagerService$LocalService": ["accessAppContentEnable", "accessAppControlEnable"],
        "com/miui/server/security/AgentPrivacyUtils": ["shouldSkipAIPermissionCheck"],
        "com/android/server/input/InputManagerServiceStubImpl": ["shouldCheckPermission"],
    }
    for owner, methods in required.items():
        for method in methods:
            path = missing / (method + ".class")
            path.write_bytes((boot / (owner + ".class")).read_bytes())
            rewrite_utf8(path, {method.encode(): b"missingExpectedMethod"})
    # First compile untouched production sources against actual Android/API102.
    run("javac", "-encoding", "UTF-8", "-source", "8", "-target", "8",
        "-classpath", os.pathsep.join(map(str, (ANDROID, API))), "-d", classes,
        SOURCES / "Reflect.java", SOURCES / "PrivacyHooks.java", SOURCES / "WarningHooks.java", payload)
    # Public host tests use synthetic bytes; OEM DEX is never distributed.
    dex = temp / "fixture-warning.dex"
    dex.write_bytes(b"synthetic warning payload for hash-gate tests")
    replacements = {
        "/product/etc/xuanyuan-ai-privacy.enabled": str(mounts / "privacy.enabled"),
        "/product/etc/xuanyuan-warning.enabled": str(mounts / "warning.enabled"),
        "/product/framework/xuanyuan-warning.dex": str(mounts / "warning.dex"),
        "/system_ext/framework/miui-services.jar": str(mounts / "services"),
        "/system_ext/framework/miui-framework.jar": str(mounts / "framework"),
    }
    replacements[PINS["dex"]] = hashlib.sha256(dex.read_bytes()).hexdigest()
    for name in ("services", "framework", "apk"):
        value = ("host fixture " + name).encode()
        (mounts / name).write_bytes(value)
        replacements[PINS[name]] = hashlib.sha256(value).hexdigest()
    (mounts / "warning.dex").write_bytes(dex.read_bytes())
    rewrite_utf8(classes / "local/xuanyuan/disastercompat/Payload.class",
                 {PINS["dex"].encode(): hashlib.sha256(dex.read_bytes()).hexdigest().encode()})
    for name in ("PrivacyHooks", "WarningHooks"):
        rewrite_utf8(classes / ("local/xuanyuan/unified/" + name + ".class"),
                     {k.encode(): v.encode() for k, v in replacements.items()})
    run("javac", "-encoding", "UTF-8", "-classpath", os.pathsep.join(map(str, (classes, boot, API))),
        "-d", classes, HERE / "SecurityTests.java")
    run("java", "-ea", "-Xbootclasspath/a:" + str(boot), "-classpath",
        os.pathsep.join(map(str, (classes, API))), "SecurityTests", mounts)
