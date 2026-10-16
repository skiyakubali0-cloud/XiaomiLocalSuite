package local.xuanyuan.mipushcompat;

import android.app.Activity;
import android.content.SharedPreferences;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.os.Bundle;
import android.graphics.Insets;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.widget.BaseAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;
import io.github.libxposed.service.XposedService;
import io.github.libxposed.service.XposedServiceHelper;
import java.lang.ref.WeakReference;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Explicit per-app China adapters and separate native diagnostics. */
public final class Manager extends Activity {
    private static volatile XposedService service;
    private static boolean listenerRegistered;
    private static WeakReference<Manager> current = new WeakReference<>(null);
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final List<Candidate> candidates = new ArrayList<>(), visible = new ArrayList<>();
    private SharedPreferences prefs;
    private Set<String> selected;
    private Set<String> chinaApps;
    private int listMode;
    private Button supportedTab, candidatesTab;
    private TextView status;
    private EditText search;
    private CheckBox enabled;
    private boolean hasScanResults;
    private boolean scanning;
    private final Rows rows = new Rows();
    private final SharedPreferences.OnSharedPreferenceChangeListener preferenceListener = (p, key) -> runOnUiThread(this::filter);

    private static final class Candidate {
        ApplicationInfo app;
        String label;
        SdkScanner.Result scan;
        long updated;
        String sourceIdentity;
        boolean system;
        boolean mihomeVerified;
        boolean coolapkVerified;
        boolean chinaVerified;
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        current = new WeakReference<>(this);
        prefs = getSharedPreferences("selection", 0);
        ChinaApps.migrate(prefs);
        chinaApps = ChinaApps.requested(prefs);
        selected = new HashSet<>(prefs.getStringSet("selected", Collections.emptySet()));
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(20, 16, 20, 16);
        layout.setOnApplyWindowInsetsListener((view, insets) -> {
            Insets bars = insets.getInsets(WindowInsets.Type.systemBars());
            view.setPadding(20, 16 + bars.top, 20, 16 + bars.bottom);
            return insets;
        });
        TextView title = new TextView(this);
        title.setText("MiPush · 0.8.2 钱包心跳候选");
        title.setTextSize(21);
        layout.addView(title);
        TextView explanation = new TextView(this);
        explanation.setText("按应用开启独立中国区，不改全局XMSF。仅已适配版本可开启；检测到SDK只算候选。注册成功不等于通知送达。修改中国区开关后，需在系统应用详情强行停止并重开该应用。");
        layout.addView(explanation);
        enabled = new CheckBox(this);
        enabled.setText("诊断日志（可选，不控制中国区开关）");
        enabled.setChecked(prefs.getBoolean("enabled", false));
        enabled.setOnCheckedChangeListener((button, checked) -> {
            prefs.edit().putBoolean("enabled", checked).apply();
            publish();
        });
        layout.addView(enabled);
        LinearLayout actions = new LinearLayout(this);
        Button scan = new Button(this); scan.setText("扫描应用"); scan.setOnClickListener(v -> scan()); actions.addView(scan);
        Button scope = new Button(this); scope.setText("请求作用域"); scope.setOnClickListener(v -> requestScope()); actions.addView(scope);
        Button clear = new Button(this); clear.setText("清空"); clear.setOnClickListener(v -> {
            clear.setEnabled(false);
            worker.submit(()->{try{WalletRecovery.restore(Manager.this);runOnUiThread(()->{
                selected.clear();chinaApps.clear();
                prefs.edit().clear().putStringSet("selected",new HashSet<>(selected)).putStringSet(ChinaApps.KEY,new HashSet<>(chinaApps)).putBoolean("enabled",false).apply();
                saveProfileEvidence(candidates);enabled.setChecked(false);publish();filter();clear.setEnabled(true);
            });}catch(Exception e){runOnUiThread(()->{clear.setEnabled(true);status.setText("清空未完成，钱包后台设置仍保留："+e.getClass().getSimpleName());});}});
        }); actions.addView(clear);
        layout.addView(actions);
        LinearLayout tabs = new LinearLayout(this);
        supportedTab = new Button(this); supportedTab.setText("可开启");
        supportedTab.setOnClickListener(v -> { listMode = 0; filter(); }); tabs.addView(supportedTab, new LinearLayout.LayoutParams(0, -2, 1));
        candidatesTab = new Button(this); candidatesTab.setText("待适配");
        candidatesTab.setOnClickListener(v -> { listMode = 1; filter(); }); tabs.addView(candidatesTab, new LinearLayout.LayoutParams(0, -2, 1));
        Button all = new Button(this); all.setText("全部应用");
        all.setOnClickListener(v -> { listMode = 2; filter(); }); tabs.addView(all, new LinearLayout.LayoutParams(0, -2, 1));
        layout.addView(tabs);
        status = new TextView(this);
        layout.addView(status);
        search = new EditText(this);
        search.setSingleLine(true); search.setHint("搜索应用名或包名");
        search.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int start, int count, int after) { }
            public void onTextChanged(CharSequence s, int start, int before, int count) { filter(); }
            public void afterTextChanged(Editable text) { }
        });
        layout.addView(search);
        ListView list = new ListView(this);
        list.setAdapter(rows);
        layout.addView(list, new LinearLayout.LayoutParams(-1, 0, 1));
        setContentView(layout);
        layout.requestApplyInsets();
        if (!listenerRegistered) {
            listenerRegistered = true;
            local.xuanyuan.unified.FrameworkService.addListener(new XposedServiceHelper.OnServiceListener() {
                public void onServiceBind(XposedService connected) {
                    service = connected;
                    Manager manager = current.get();
                    if (manager != null) manager.runOnUiThread(manager::publish);
                }
                public void onServiceDied(XposedService disconnected) {
                    if (service == disconnected) service = null;
                    Manager manager = current.get();
                    if (manager != null) manager.runOnUiThread(manager::frameworkStatus);
                }
            });
        }
        frameworkStatus();
        scan();
    }

    @Override public void onResume() {
        super.onResume(); prefs.registerOnSharedPreferenceChangeListener(preferenceListener); filter();
    }
    @Override public void onPause() {
        prefs.unregisterOnSharedPreferenceChangeListener(preferenceListener); super.onPause();
    }
    @Override public void onDestroy() {
        if (current.get() == this) current.clear();
        worker.shutdownNow(); super.onDestroy();
    }

    private void frameworkStatus() {
        if (scanning) {
            status.setText("正在扫描应用；保留上次校验配置。开关配置仍可同步。扫描后再开启新应用；改变中国区开关后须强行停止并重开目标应用。");
            return;
        }
        XposedService connected = service;
        if (connected == null) {
            status.setText("框架服务未连接，所选配置尚未同步。手动步骤：在 LSPosed / 框架管理器启用本模块，只勾选所选应用；再打开本页面同步应用开关，重启目标应用。作用域默认空；勾选作用域不等于已验证推送。");
            return;
        }
        try {
            status.setText("框架 API " + connected.getApiVersion() + " · 中国区已选 " + chinaApps.size() + " · 诊断已选 " + selected.size()
                    + " 个 · 框架报告范围项 " + connected.getScope().size() + " 个\n模块启用与作用域以 LSPosed 管理器为准；数量不证明实际注入。中国区开关独立于诊断；更换应用版本后须重新核验。");
        } catch (RuntimeException error) { status.setText("框架状态不可用；未验证配置同步。"); }
    }

    private boolean publish() {
        prefs.edit().putBoolean("wallet_boot_synced", false).commit();
        if (service == null) { frameworkStatus(); return false; }
        try {
            SharedPreferences.Editor editor = service.getRemotePreferences("selection").edit();
            if (hasScanResults) editor.clear();
            editor.putBoolean("wallet_background_ready", WalletRecovery.ready(this));
            editor.remove("coolapk_china").putStringSet(ChinaApps.KEY, new HashSet<>(chinaApps))
                    .putBoolean("enabled", prefs.getBoolean("enabled", false))
                    .putStringSet("selected", new HashSet<>(selected));
            boolean walletVerified = false;
            for (Candidate candidate : candidates) {
                String pkg = candidate.app.packageName;
                if ((selected.contains(pkg) || chinaApps.contains(pkg)) && (!candidate.system || (WalletRecovery.PACKAGE.equals(pkg) && candidate.chinaVerified)) && (candidate.scan.errors.isEmpty() || candidate.coolapkVerified)
                        && !candidate.sourceIdentity.isEmpty()) {
                    if (WalletRecovery.PACKAGE.equals(pkg) && candidate.chinaVerified && currentChina(candidate)) {
                        walletVerified = true;
                        prefs.edit().putLong("wallet_boot_updated",candidate.updated).putString("wallet_boot_identity",candidate.sourceIdentity).commit();
                    }
                    editor.putStringSet(pkg + ".guards", new HashSet<>(candidate.scan.guardClasses))
                            .putString(pkg + ".sourceIdentity", candidate.sourceIdentity)
                            .putLong(pkg + ".updated", candidate.updated)
                            .putBoolean(pkg + ".mh_verified", candidate.mihomeVerified)
                            .putBoolean(pkg + ".cp_verified", candidate.coolapkVerified)
                            .putBoolean(pkg + ".cn_verified", candidate.chinaVerified);
                }
            }
            boolean saved = editor.commit();
            prefs.edit().putBoolean("wallet_boot_synced", saved && walletVerified && chinaApps.contains(WalletRecovery.PACKAGE) && WalletRecovery.ready(this)).commit();
            frameworkStatus();
            if (!saved) status.setText("配置未同步成功；不要将本地开关视为目标进程状态。");
            return saved;
        } catch (RuntimeException error) { status.setText("框架拒绝配置同步；应用开关状态未确认。"); return false; }
    }

    private void requestScope() {
        Set<String> requestedScope = new HashSet<>(selected); requestedScope.addAll(chinaApps);
        if (requestedScope.isEmpty()) { status.setText("尚未选择应用；作用域请求未发送。"); return; }
        if (!publish()) return;
        try {
            service.requestScope(new ArrayList<>(requestedScope), new XposedService.OnScopeEventListener() {
                public void onScopeRequestApproved(List<String> approved) {
                    runOnUiThread(() -> status.setText("框架批准回调报告 " + approved.size() + " 个范围项；实际启用与作用域以 LSPosed 管理器为准。请自行重启目标应用；此回调不证明实际注入或收到通知。"));
                }
                public void onScopeRequestFailed(String message) {
                    runOnUiThread(() -> status.setText("作用域未获批准：" + message + "\n可在框架管理器手动勾选所选应用。"));
                }
            });
        } catch (RuntimeException error) { status.setText("框架不支持此次请求；请在框架管理器手动设置所选作用域。"); }
    }

    private void scan() {
        if (scanning) return;
        scanning = true;
        status.setText("正在本地扫描 APK 与所有已安装 splits…");
        worker.execute(() -> {
            List<Candidate> found = new ArrayList<>();
            for (ApplicationInfo app : getPackageManager().getInstalledApplications(0)) {
                if (Thread.currentThread().isInterrupted()) return;
                if (app.packageName.equals(getPackageName()) || app.packageName.equals("com.xiaomi.xmsf") || app.uid < 10000) continue;
                Candidate candidate = new Candidate(); candidate.app = app;
                candidate.label = String.valueOf(app.loadLabel(getPackageManager()));
                candidate.system = (app.flags & ApplicationInfo.FLAG_SYSTEM) != 0;
                PackageInfo before;
                try { before = getPackageManager().getPackageInfo(app.packageName, 0); }
                catch (android.content.pm.PackageManager.NameNotFoundException error) { continue; }
                List<String> paths = new ArrayList<>(); paths.add(app.sourceDir);
                if (app.splitSourceDirs != null) paths.addAll(Arrays.asList(app.splitSourceDirs));
                candidate.sourceIdentity = SdkScanner.sourceIdentity(paths);
                candidate.scan = SdkScanner.scan(paths);
                candidate.coolapkVerified = !candidate.system && CoolapkProfile.verify(app.packageName, before.getLongVersionCode(), paths);
                candidate.mihomeVerified = !candidate.system && candidate.scan.errors.isEmpty()
                        && MihomeProfile.verify(app.packageName, before.versionName, before.getLongVersionCode(), paths);
                if (!candidate.sourceIdentity.equals(SdkScanner.sourceIdentity(paths))) {
                    candidate.scan.errors.add("APK identity changed during scan");
                }
                try {
                    candidate.updated = getPackageManager().getPackageInfo(app.packageName, 0).lastUpdateTime;
                    if (candidate.updated != before.lastUpdateTime) candidate.scan.errors.add("Package changed during scan");
                }
                catch (android.content.pm.PackageManager.NameNotFoundException error) { candidate.scan.errors.add("Package removed during scan"); }
                candidate.mihomeVerified &= candidate.scan.errors.isEmpty();
                candidate.chinaVerified = (!candidate.system || WalletRecovery.PACKAGE.equals(app.packageName)) && candidate.scan.errors.isEmpty()
                        && candidate.updated == before.lastUpdateTime
                        && ExactChinaProfile.verify(app.packageName, before.getLongVersionCode(), paths)
                        && candidate.sourceIdentity.equals(SdkScanner.sourceIdentity(paths));
                candidate.coolapkVerified &= candidate.updated == before.lastUpdateTime && candidate.sourceIdentity.equals(SdkScanner.sourceIdentity(paths));
                found.add(candidate);
            }
            found.sort(Comparator.comparing((Candidate c) -> !c.scan.status().equals("sdk_detected"))
                    .thenComparing(c -> c.label));
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) return;
                saveProfileEvidence(found);
                hasScanResults = true; scanning = false;
                candidates.clear(); candidates.addAll(found); filter(); publish();
            });
        });
    }

    private void saveProfileEvidence(List<Candidate> verified) {
        SharedPreferences.Editor local = prefs.edit().putBoolean(MihomeProfile.PACKAGE + ".mh_verified", false)
                .putBoolean(CoolapkProfile.PACKAGE + ".cp_verified", false);
        for (Candidate candidate : verified) {
            if (MihomeProfile.PACKAGE.equals(candidate.app.packageName)) {
                local.putBoolean(MihomeProfile.PACKAGE + ".mh_verified", candidate.mihomeVerified)
                        .putLong(MihomeProfile.PACKAGE + ".mh_updated", candidate.updated)
                        .putString(MihomeProfile.PACKAGE + ".mh_identity", candidate.sourceIdentity);
            }
        }
        for (Candidate candidate : verified) {
            if (CoolapkProfile.PACKAGE.equals(candidate.app.packageName)) {
                local.putBoolean(CoolapkProfile.PACKAGE + ".cp_verified", candidate.coolapkVerified)
                    .putLong(CoolapkProfile.PACKAGE + ".cp_updated", candidate.updated)
                    .putString(CoolapkProfile.PACKAGE + ".cp_identity", candidate.sourceIdentity);
            }
        }
        local.apply();
    }

    private void filter() {
        if (search == null) return;
        String query = search.getText().toString().toLowerCase(Locale.ROOT);
        visible.clear();
        int supportedCount = 0, pendingCount = 0;
        for (Candidate candidate : candidates) {
            boolean supported = currentChina(candidate);
            boolean pending = !candidate.system && !supported && candidate.scan.status().equals("sdk_detected");
            if (supported) supportedCount++;
            if (pending) pendingCount++;
            boolean inCategory = listMode == 2 || (listMode == 0 && (supported || chinaApps.contains(candidate.app.packageName)))
                    || (listMode == 1 && pending);
            if (inCategory && (candidate.label + " " + candidate.app.packageName).toLowerCase(Locale.ROOT).contains(query)) visible.add(candidate);
        }
        supportedTab.setText("可开启 (" + supportedCount + ")");
        candidatesTab.setText("待适配 (" + pendingCount + ")");
        rows.notifyDataSetChanged();
    }

    private boolean currentMiHome(Candidate candidate) {
        if (!candidate.mihomeVerified) return false;
        try {
            PackageInfo info = getPackageManager().getPackageInfo(MihomeProfile.PACKAGE, 0);
            List<String> paths = new ArrayList<>(); paths.add(info.applicationInfo.sourceDir);
            if (info.applicationInfo.splitSourceDirs != null) paths.addAll(Arrays.asList(info.applicationInfo.splitSourceDirs));
            return info.lastUpdateTime == candidate.updated && info.getLongVersionCode() == MihomeProfile.VERSION_CODE
                    && MihomeProfile.VERSION_NAME.equals(info.versionName)
                    && candidate.sourceIdentity.equals(SdkScanner.sourceIdentity(paths));
        } catch (android.content.pm.PackageManager.NameNotFoundException error) { return false; }
    }

    private boolean currentCoolapk(Candidate candidate) {
        if (!CoolapkProfile.PACKAGE.equals(candidate.app.packageName) || !candidate.coolapkVerified) return false;
        try {
            PackageInfo info = getPackageManager().getPackageInfo(CoolapkProfile.PACKAGE, 0);
            List<String> paths = new ArrayList<>(); paths.add(info.applicationInfo.sourceDir);
            if (info.applicationInfo.splitSourceDirs != null) paths.addAll(Arrays.asList(info.applicationInfo.splitSourceDirs));
            return info.lastUpdateTime == candidate.updated && info.getLongVersionCode() == CoolapkProfile.VERSION_CODE
                    && candidate.sourceIdentity.equals(SdkScanner.sourceIdentity(paths));
        } catch (android.content.pm.PackageManager.NameNotFoundException error) { return false; }
    }

    private boolean currentChina(Candidate candidate) {
        if (currentCoolapk(candidate)) return true;
        ExactChinaProfile profile = ExactChinaProfile.find(candidate.app.packageName);
        if (profile == null || !candidate.chinaVerified) return false;
        try {
            PackageInfo info = getPackageManager().getPackageInfo(profile.pkg, 0);
            List<String> paths = new ArrayList<>(); paths.add(info.applicationInfo.sourceDir);
            if (info.applicationInfo.splitSourceDirs != null) paths.addAll(Arrays.asList(info.applicationInfo.splitSourceDirs));
            return info.applicationInfo.enabled && info.lastUpdateTime == candidate.updated
                    && info.getLongVersionCode() == profile.version
                    && candidate.sourceIdentity.equals(SdkScanner.sourceIdentity(paths));
        } catch (android.content.pm.PackageManager.NameNotFoundException error) { return false; }
    }

    private final class Rows extends BaseAdapter {
        public int getCount() { return visible.size(); }
        public Object getItem(int position) { return visible.get(position); }
        public long getItemId(int position) { return position; }
        public View getView(int position, View old, ViewGroup parent) {
            Candidate candidate = visible.get(position);
            String pkg = candidate.app.packageName;
            LinearLayout row = new LinearLayout(Manager.this); row.setPadding(0, 12, 0, 12); row.setOrientation(LinearLayout.VERTICAL);
            CheckBox choice = new CheckBox(Manager.this);
            choice.setText("诊断此应用");
            choice.setChecked(selected.contains(pkg));
            choice.setEnabled(selected.contains(pkg) || (!candidate.system && (candidate.scan.status().equals("sdk_detected") || candidate.coolapkVerified)));
            choice.setOnCheckedChangeListener((button, checked) -> {
                if (checked) selected.add(pkg); else selected.remove(pkg);
                prefs.edit().putStringSet("selected", new HashSet<>(selected)).remove(pkg + ".observed").apply();
                publish();
            });
            TextView text = new TextView(Manager.this);
            String detection = candidate.scan.status().equals("sdk_detected") ? "已检测 MiPush SDK（待适配候选）"
                    : candidate.scan.status().equals("unverified") ? "未验证（扫描失败）" : "未检测到已知 MiPush SDK";
            String diagnostic = candidate.system ? "系统应用不提供中国区切换" : "独立中国区尚未适配；不能仅凭SDK启用";
            if (prefs.getLong(pkg + ".observed", 0) > 0 && prefs.getLong(pkg + ".updated", -1) == candidate.updated) {
                diagnostic = prefs.getBoolean(pkg + ".original", false)
                        ? "SDK 判断可用；实际路由/投递未验证"
                        : "原始 SDK 判断：未选择原生 MiPush · 原因待适配";
                diagnostic += "\n上次观察：" + new java.util.Date(prefs.getLong(pkg + ".observed", 0));
            }
            if (MihomeProfile.PACKAGE.equals(pkg)) {
                boolean mihomeCurrent = currentMiHome(candidate);
                diagnostic = mihomeCurrent ? "米家精确版本/SHA 已匹配 · 原生逻辑观察"
                        : "米家精确版本/SHA 未匹配 · 专用观察关闭";
                String[] labels = {"SDK 内部原始判断", "原生组件选路", "服务派发尝试", "注册结果回调（含本地缓存）", "通知到达回调", "透传回调", "通知点击（不算新收到）"};
                for (int i = 0; i < MihomeProfile.EVENTS.size(); i++) {
                    String event = MihomeProfile.EVENTS.get(i), key = pkg + ".mh." + event;
                    long at = prefs.getLong(pkg + ".mh_history_updated", -1) == candidate.updated
                            && mihomeCurrent ? prefs.getLong(key + ".at", 0) : 0;
                    diagnostic += "\n" + labels[i] + "：";
                    if (at == 0) diagnostic += "未观察 / 未验证";
                    else {
                        if (event.equals("decision")) diagnostic += prefs.getLong(key + ".code", 0) == 1 ? "原始 true" : "原始 false";
                        else if (event.equals("route") || event.equals("dispatch")) {
                            String route = prefs.getString(key + ".route", "other");
                            diagnostic += route.equals("xmsf") ? "XMSF" : route.equals("app_local") ? "应用自身服务" : "其他 / 未确认";
                        } else if (event.equals("registration")) diagnostic += "原始 code=" + prefs.getLong(key + ".code", 0);
                        else diagnostic += "已观察原始调用";
                        diagnostic += " · " + new java.util.Date(at);
                    }
                }
                diagnostic += "\n已分析的 11.7.704 使用国际 SDK 5_1_8-G，地区枚举无 China；尚不支持独立中国区，保留原生通道。注册≠收到；到达回调不证明通知栏展示。";
            }
            if (CoolapkProfile.PACKAGE.equals(pkg)) {
                boolean coolapkCurrent = currentCoolapk(candidate);
                if (coolapkCurrent) detection = "精确应用版本已校验";
                diagnostic = coolapkCurrent ? "可开启独立中国区 · 此版本注册已验证，真实通知待验证" : "酷安版本未匹配 · 中国区适配未生效";
                long at = coolapkCurrent && prefs.getLong(pkg + ".cp_result_updated", -1) == candidate.updated ? prefs.getLong(pkg + ".cp_at", 0) : 0;
                if (at > 0) {
                    long code = prefs.getLong(pkg + ".cp_code", -1);
                    diagnostic += "\n上次注册回调 code=" + code + " · " + new java.util.Date(at);
                    if (code == 22022) diagnostic += "\n注册失败；本机共享XMSF路径曾返回此码。该历史记录不代表当前中国区开关结果。";
                }
                else diagnostic += "\n注册回调未观察；不代表已经注册或收到通知";
            }
            if (ExactChinaProfile.find(pkg) != null) {
                if (currentChina(candidate)) detection = "精确应用版本已校验 · 独立中国区实验适配";
                diagnostic = !candidate.chinaVerified ? "独立中国区精确版本未匹配；不执行适配"
                        : !currentChina(candidate) ? "应用已停用或安装状态已变化；不自动启用，请重新扫描。独立中国区尚未完成实机验证。"
                        : "精确中国版 SDK 选路适配（实验）· 仅本应用独立连接；注册与真实通知须分别验证。不会自动登录、同意协议或改全局 XMSF。";
            }
            if ("com.mipay.wallet".equals(pkg)) {
                diagnostic = "6.115.1.5775.2754 精确版本：独立保存中国区推送凭据，关闭后恢复原生存储。需配置后台和开机恢复；仅验证连接与服务器往返，真实通知仍待验证。";
            }
            text.setText(candidate.label + "\n" + pkg + "\n" + detection
                    + (candidate.scan.errors.isEmpty() || candidate.coolapkVerified ? "" : " · 部分扫描未完成")
                    + (candidate.system && !WalletRecovery.PACKAGE.equals(pkg) ? " · 系统应用仅展示" : "") + "\n" + diagnostic);
            row.addView(text);
            CheckBox china = new CheckBox(Manager.this);
            boolean supported = currentChina(candidate);
            china.setText(supported ? "独立中国区（需LSPosed作用域）" : "独立中国区：尚未适配 / 版本不匹配");
            china.setContentDescription(candidate.label + " 独立中国区");
            china.setChecked(chinaApps.contains(pkg));
            china.setEnabled(supported || chinaApps.contains(pkg));
            china.setOnCheckedChangeListener((button, checked) -> {
                if (checked && (!currentChina(candidate) || (WalletRecovery.PACKAGE.equals(pkg) && !WalletRecovery.ready(Manager.this)))) { china.setChecked(false); status.setText("请先完成钱包后台配置；版本不匹配时不能启用。"); return; }
                if(WalletRecovery.PACKAGE.equals(pkg)) {
                    china.setEnabled(false);
                    worker.submit(()->{try{WalletRecovery.stop(Manager.this);runOnUiThread(()->{
                        if(checked)chinaApps.add(pkg);else chinaApps.remove(pkg);
                        prefs.edit().putStringSet(ChinaApps.KEY,new HashSet<>(chinaApps)).apply();publish();filter();
                        status.setText("钱包已停止并切换配置，请重新打开钱包。开机恢复仅在中国区开关启用时执行。");
                    });}catch(Exception e){runOnUiThread(()->{filter();status.setText("钱包未切换："+e.getClass().getSimpleName());});}});
                    return;
                }
                if (checked) chinaApps.add(pkg); else chinaApps.remove(pkg);
                prefs.edit().putStringSet(ChinaApps.KEY, new HashSet<>(chinaApps)).apply();
                publish();
            });
            row.addView(china);
            if (WalletRecovery.PACKAGE.equals(pkg)) {
                TextView recovery = new TextView(Manager.this);
                recovery.setText("钱包独立推送需要后台电池豁免。配置后需授予本插件Root权限以开机恢复；保留原推送凭据。首次启用仍须打开钱包一次。卸载前用下方恢复按钮撤销本插件添加的豁免。");
                row.addView(recovery);
                Button setup = new Button(Manager.this);
                setup.setText(WalletRecovery.ready(Manager.this) ? "钱包后台恢复已配置" : "配置钱包后台及开机恢复（Root）");
                setup.setEnabled(candidate.chinaVerified);
                setup.setOnClickListener(v -> { setup.setEnabled(false); worker.submit(() -> {
                    String message;
                    try { WalletRecovery.prepare(Manager.this); message="后台电池豁免已配置；请勾选钱包中国区并请求作用域。"; }
                    catch(Exception e){message="配置未完成："+e.getClass().getSimpleName();}
                    final String result=message;
                    runOnUiThread(()->{publish();filter();status.setText(result);});
                }); }); row.addView(setup);
                Button restore = new Button(Manager.this); restore.setText("恢复钱包后台设置（保留数据）");
                restore.setOnClickListener(v -> { restore.setEnabled(false); worker.submit(() -> {
                    try { WalletRecovery.restore(Manager.this); runOnUiThread(()->{
                        chinaApps.remove(pkg);prefs.edit().putStringSet(ChinaApps.KEY,new HashSet<>(chinaApps)).apply();
                        publish();filter();status.setText("钱包已停止，已恢复本插件添加的电池设置；数据和原凭据保留。");
                    }); } catch(Exception e){runOnUiThread(()->{filter();status.setText("恢复未完成："+e.getClass().getSimpleName());});}
                }); }); row.addView(restore);
            }
            row.addView(choice);
            return row;
        }
    }
}
