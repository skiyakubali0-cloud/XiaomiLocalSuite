#!/usr/bin/env python3
"""Compile only, then exercise the real API102 hook registrations on a host JVM.

Android/OEM fixtures and the supplied Reflect contract are test-only. No replacement
libxposed API, APK packaging, shared source edits, or device commands are used.
"""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile

# Preserve the logical workspace path: suite can be a symlink to external storage.
HERE = Path(__file__).absolute().parent
PROJECT = HERE.parents[1]
WORKSPACE = PROJECT.parents[1]
API = PROJECT / "deps/api.jar"
ANDROID = Path(os.environ.get("ANDROID_JAR", "/opt/homebrew/share/android-commandlinetools/platforms/android-36/android.jar"))
SOURCES = [PROJECT / "src/local/xuanyuan/unified" / (name + ".java")
           for name in ("PhoneHooks", "ClockHooks", "SuggestionHooks")]

# Check the guard literals against the originals as well as exercising them below.
for migrated, legacy in zip(SOURCES, (
        "phone/sms-hook/src/local/xuanyuan/smscompat/SmsHook.java",
        "clock/hook/src/local/xuanyuan/clockcompat/ClockHook.java",
        "xiaoai-suggestions/hook/src/local/xuanyuan/suggestioncompat/SuggestionHook.java")):
    text = migrated.read_text()
    assert set(re.findall(r'"([a-f0-9]{64})"', text)) == set(re.findall(
        r'"([a-f0-9]{64})"', (WORKSPACE / legacy).read_text())), migrated
    assert "de.robv.android.xposed" not in text and "invokeOriginalMethod" not in text

FIXTURES = {
    "android/os/Build.java": '''package android.os;
public class Build { public static String DEVICE="xuanyuan";
 public static class VERSION { public static int SDK_INT=37;
 public static String INCREMENTAL="OS4.0.0.6.XOAEUXM"; } }''',
    "android/os/Bundle.java": '''package android.os;
public class Bundle extends java.util.HashMap<String,Object> {
 public Bundle() {} public Bundle(Bundle b) { super(b); }
 public void putBoolean(String k,boolean v) { put(k,v); }
 public boolean getBoolean(String k) { return Boolean.TRUE.equals(get(k)); } }''',
    "android/os/ParcelFileDescriptor.java": "package android.os; public class ParcelFileDescriptor {}",
    "android/util/Log.java": "package android.util; public class Log { public static final int INFO=4; }",
    "android/content/SharedPreferences.java": "package android.content; public interface SharedPreferences {}",
    "android/content/ComponentName.java": '''package android.content;
public class ComponentName { public final String pkg,name;
 public ComponentName(String p,String n) {pkg=p;name=n;} }''',
    "android/content/pm/ApplicationInfo.java": '''package android.content.pm;
public class ApplicationInfo { public String sourceDir; public android.os.Bundle metaData;
 public ApplicationInfo() {} public ApplicationInfo(ApplicationInfo a) {sourceDir=a.sourceDir;metaData=a.metaData;} }''',
    "android/content/pm/PackageManager.java": '''package android.content.pm;
public class PackageManager {
 public java.util.Set<String> installed=new java.util.HashSet<>(); public boolean fail;
 public Object resolveActivity(android.content.Intent i,int flags) {
 if(fail) throw new IllegalStateException("resolve"); return installed.contains(i.getPackage())?new Object():null; } }''',
    "android/content/Context.java": '''package android.content;
public class Context { public android.content.pm.PackageManager pm=new android.content.pm.PackageManager();
 public android.content.pm.PackageManager getPackageManager() {return pm;} }''',
    "android/content/Intent.java": '''package android.content;
public class Intent {
 public static final String ACTION_SEARCH="android.intent.action.SEARCH";
 private String action,pkg; private ComponentName component;
 public int flags; public String data; public android.os.Bundle extras=new android.os.Bundle();
 public Intent(String a) {action=a;} public Intent(Intent i) {action=i.action;pkg=i.pkg;
 component=i.component;flags=i.flags;data=i.data;extras=new android.os.Bundle(i.extras);}
 public String getAction(){return action;} public String getPackage(){return pkg;}
 public ComponentName getComponent(){return component;}
 public Intent setPackage(String p){pkg=p;return this;}
 public Intent setClassName(String p,String c){pkg=p;component=new ComponentName(p,c);return this;}
 public ComponentName resolveActivity(android.content.pm.PackageManager pm){
 return pm.resolveActivity(this,0)==null?null:new ComponentName(pkg,"Resolved");} }''',
    "android/app/AppComponentFactory.java": "package android.app; public class AppComponentFactory {}",
    "android/app/Application.java": '''package android.app;
public class Application extends android.content.Context { protected void attach(android.content.Context c) {} }''',
    "android/app/Activity.java": '''package android.app;
public class Activity extends android.content.Context {
 public void startActivityForResult(android.content.Intent i,int r,android.os.Bundle b) {} }''',
    "android/app/ApplicationPackageManager.java": '''package android.app;
public class ApplicationPackageManager { public android.content.pm.ApplicationInfo getApplicationInfo(String p,int f){return null;} }''',
    "android/database/sqlite/SQLiteDatabase.java": '''package android.database.sqlite;
public class SQLiteDatabase { public long count; public boolean fail; }''',
    "android/database/DatabaseUtils.java": '''package android.database;
public class DatabaseUtils { public static long longForQuery(android.database.sqlite.SQLiteDatabase db,String q,String[] a) {
 if(!q.equals("SELECT count(*) FROM antispam_category") || a!=null) throw new AssertionError("query scope");
 if(db.fail) throw new IllegalStateException("query"); return db.count;} }''',
    "com/android/providers/telephony/MmsSmsUtils.java": '''package com.android.providers.telephony;
public class MmsSmsUtils {public static boolean HAS_VERIFICATION_CODE_CATEGORY;}''',
    "miui/os/Build.java": '''package miui.os;
public class Build {public static boolean IS_INTERNATIONAL_BUILD=true,IS_GLOBAL_BUILD=true;
 public static String getRegion(){return "SG";} }''',
    "gn/b.java": "package gn; public class b {public static boolean a=true;}",
    "g5/f3.java": '''package g5; public class f3 {public static boolean a;
 public static boolean allowed; public static boolean b(android.content.Context c){return allowed;} }''',
    "com/miui/smsextra/util/UpdateVerificationCodeUtils.java": '''package com.miui.smsextra.util;
public class UpdateVerificationCodeUtils { public static boolean isVerificationCodeCategoryEnabled(android.content.Context c){return false;} }''',
    "com/miui/smsextra/understand/UnderstandFactory.java": '''package com.miui.smsextra.understand;
public class UnderstandFactory {
 public static Json e; public static int inits; public static boolean fail,missing;
 public static Object getMmsConfigWithKey(String key){return e==null?null:e.values.get(key);}
 public static void initMmsConfigJson(){inits++;if(fail)throw new IllegalStateException("init");
 e=new Json();if(!missing)e.values.put("recognition_partner_url","https://oem.invalid/partner");}
 public static class Json {public java.util.Map<String,Object> values=new java.util.HashMap<>();
 public boolean has(String key){return values.containsKey(key);}public Object get(String key){return values.get(key);} } }''',
    "com/miui/smsextra/sdk/SDKManager.java": '''package com.miui.smsextra.sdk;
public class SDKManager { public void init(){} public boolean isXiaomiSdk(){return true;}
 public boolean canClassify(){return false;} }''',
    "ef/d.java": "package ef; public class d {public static void b(String s){} }",
    "com/miui/yellowpage/utils/l1.java": "package com.miui.yellowpage.utils; public class l1 {public void e(java.util.Map<?,?> m){} }",
    "com/miui/yellowpage/utils/j0.java": "package com.miui.yellowpage.utils; public class j0 {public int w(){return 0;} }",
    "n1/a.java": "package n1; public enum a {ANTISPAM, ANTISPAM_SYNC, OTHER}",
    "n1/b.java": "package n1; public class b {public static boolean e(android.content.Context c,a f){return false;} }",
    "com/miui/yellowpage/providers/yellowpage/YellowPageDatabaseHelper.java": '''package com.miui.yellowpage.providers.yellowpage;
public class YellowPageDatabaseHelper {public int imports;public boolean fail;
 public local.xuanyuan.unified.Harness.Work callback;
 public android.database.sqlite.SQLiteDatabase getReadableDatabase(){return null;}
 public void o(android.database.sqlite.SQLiteDatabase db) throws Throwable {imports++;
 if(callback!=null)callback.run(new Object[0]);if(fail)throw new IllegalStateException("import");} }''',
    "com/android/soundrecorder/SoundRecorderSettings.java": '''package com.android.soundrecorder;
public class SoundRecorderSettings {public static class a {
 public android.content.Context context=new android.content.Context();
 public Row category=new Row(),entry=new Row(); public void K0(String key){}
 public android.content.Context getContext(){return context;}
 public Object I0(String key){return key.equals("pref_category_key_other_caller")?category:entry;}
 } public static class Row {public boolean visible;public Object f,m;public void H(boolean v){visible=v;} } }''',
    "miuix/core/util/SystemProperties.java": '''package miuix.core.util;
public class SystemProperties {public static String get(String k,String d){return d;} }''',
    "com/miui/audiomonitor/voiprecord/utils/CloudControlUtil.java": '''package com.miui.audiomonitor.voiprecord.utils;
public class CloudControlUtil {public static boolean useLocalConfig(){return false;} }''',
    "com/miui/audiomonitor/VoipRecordSettingsActivity.java": '''package com.miui.audiomonitor;
public class VoipRecordSettingsActivity extends android.app.Activity {
 public String mRequestPackage;public void checkPrivacy(int code,Boolean accepted){} }''',
    "ws1.java": "public class ws1 {public static boolean b(){return false;} }",
    "zs1.java": "public class zs1 {public static boolean lite;public static boolean m(){return lite;} }",
    "fs1.java": "public class fs1 {public static boolean f;public static int e=2,g=8,tier=3;public static int b(){return tier;} }",
    "com/android/deskclock/util/Util.java": '''package com.android.deskclock.util;
public class Util {public static boolean isInternational(){return true;} }''',
    "com/android/deskclock/settings/SettingsFragment.java": '''package com.android.deskclock.settings;
public class SettingsFragment {public Group mOtherPreferenceCategory=new Group();
 public Row mValueHolidayPreference=new Row();public void onCreatePreferences(android.os.Bundle b,String s){}
 public static class Row {public boolean visible=true; public void setVisible(boolean v){visible=v;} }
 public static class Group extends Row {public java.util.List<Row> rows=new java.util.ArrayList<>();
 public boolean isVisible(){return visible;}public int getPreferenceCount(){return rows.size();}
 public Row getPreference(int i){return rows.get(i);}public boolean addPreference(Row row){
 if(!rows.contains(row))rows.add(row);return true;} } }''',
    "com/android/deskclock/alarm/AlarmRepeatAdapter.java": '''package com.android.deskclock.alarm;
public class AlarmRepeatAdapter {
 public static Object setData() throws Throwable{return local.xuanyuan.unified.Harness.clock();}
 public static Object setRepeatItemChecked() throws Throwable{return local.xuanyuan.unified.Harness.clock();}
 public static Object unrelated() throws Throwable{return local.xuanyuan.unified.Harness.clock();} }''',
    "com/android/deskclock/alarm/RepeatAlarmController.java": '''package com.android.deskclock.alarm;
public class RepeatAlarmController {public static Object initRepeatAlarmAdapterData() throws Throwable {
 return local.xuanyuan.unified.Harness.clock();} }''',
    "com/android/deskclock/alarm/bedtime/BedtimeGuideActivity.java": '''package com.android.deskclock.alarm.bedtime;
public class BedtimeGuideActivity {public static Object initData() throws Throwable {
 return local.xuanyuan.unified.Harness.clock();} }''',
    "com/android/deskclock/addition/holiday/HolidayUpdateScheduler.java": '''package com.android.deskclock.addition.holiday;
public class HolidayUpdateScheduler {public static Object checkAndUpdate() throws Throwable {
 return local.xuanyuan.unified.Harness.clock();} }''',
    "com/android/deskclock/DeskClockApp.java": '''package com.android.deskclock;
public class DeskClockApp {public static boolean nested;
 public static Object onCreate() throws Throwable {return nested
 ?com.android.deskclock.alarm.AlarmRepeatAdapter.unrelated():local.xuanyuan.unified.Harness.clock();} }''',
}

with tempfile.TemporaryDirectory(prefix="host-", dir=HERE) as temporary:
    temp = Path(temporary)
    fixtures = temp / "fixtures"
    for name, text in FIXTURES.items():
        path = fixtures / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n")
    reflect = HERE / "Reflect.java"
    # Use the supplied shared helper when available; otherwise compile its contract.
    shared_reflect = PROJECT / "src/local/xuanyuan/unified/Reflect.java"
    compile_reflect = shared_reflect if shared_reflect.is_file() else reflect
    compile_dir = temp / "compile-only"
    compile_dir.mkdir()
    subprocess.run(["javac", "-encoding", "UTF-8", "-source", "8", "-target", "8",
                    "-cp", os.pathsep.join(map(str, [API, ANDROID])), "-d", str(compile_dir),
                    str(compile_reflect), *map(str, SOURCES)], check=True)
    classes = temp / "classes"
    classes.mkdir()
    subprocess.run(["javac", "-encoding", "UTF-8", "-source", "8", "-target", "8",
                    "-cp", str(API), "-d", str(classes), *[str(fixtures / name) for name in FIXTURES],
                    str(reflect), str(HERE / "Harness.java"), *map(str, SOURCES)], check=True)
    subprocess.run(["java", "-ea", "-cp", os.pathsep.join(map(str, [classes, API])),
                    "local.xuanyuan.unified.Harness"], check=True)

print("PASS: original guard parity; real Android/API102 compile-only; host regressions")
print("API102 jar SHA256:", hashlib.sha256(API.read_bytes()).hexdigest())
