"""Run actual capability/selection UI code with host doubles, without Root or a device."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_preset_wallet import HARNESS, SOURCE, method, packaged_class


def read_method(source):
    start = source.index("    private PackagedComponents readPackaged()")
    return source[start:source.index("    private void setPackaged(", start)]


CASES = r'''
    static final class Capture {
        final String out,err;final int exit;
        static Capture response;static Exception failure;
        static List<String> command;static int timeout;
        Capture(String out,String err,int exit){this.out=out;this.err=err;this.exit=exit;}
        static Capture run(List<String> cmd,int seconds) throws Exception {
            command=cmd;timeout=seconds;if(failure!=null)throw failure;return response;
        }
    }
    static final String HELPER="sh /data/adb/modules/xuanyuan-os4-suite/preset.sh ";
    static void rejected(String text){
        boolean rejected=false;try{PackagedComponents.parse(text);}catch(IllegalArgumentException expected){rejected=true;}
        check(rejected);
    }
    public static void main(String[] args) throws Exception {
        String full=String.join(",",PresetSelection.COMPONENTS);
        switch(args[0]){
        case "malformed":
            for(String text:new String[]{null,"","\n","-","market\n\n","market\r\n"," market","market ",
                "market\nphone","market,,phone","market,","market,unknown","market,market",",market",
                "phone,market","assistant,market","Market","market;id","market\u0000",full+","+full})rejected(text);
            check(PackagedComponents.parse(full+"\n").components.size()==11);
            check(PackagedComponents.parse("market").features.isEmpty());
            break;
        case "dependencies":
            for(String text:new String[]{"phone","xiaoai","assistant,xiaoai,phone","market,xiaoai",
                "market,phone,privacy","clock,warning"})rejected(text);
            PackagedComponents phone=PackagedComponents.parse("market,phone");
            check(phone.features.equals(Collections.singleton("phone")));
            PackagedComponents ai=PackagedComponents.parse("assistant,xiaoai");
            check(ai.features.equals(new LinkedHashSet<>(Arrays.asList("privacy","suggestions"))));
            check(PackagedComponents.parse("assistant").features.isEmpty());
            check(PackagedComponents.parse("disaster,clock").features.equals(new LinkedHashSet<>(Arrays.asList("warning","clock"))));
            check(PackagedComponents.parse(full).features.equals(new LinkedHashSet<>(PresetSelection.FEATURES)));
            break;
        case "defaults":
            for(String text:new String[]{"wallet","market,phone,wallet","assistant,xiaoai,wallet",full}){
                PackagedComponents cap=PackagedComponents.parse(text);PresetSelection defaults=cap.defaults();
                check(!defaults.components.contains("wallet"));
                check(cap.components.containsAll(defaults.components)&&cap.features.equals(defaults.features));
                check(cap.filter(PresetSelection.all()).components.contains("wallet"));
            }
            Page old=new Page();old.metadata.values.put("selected_component_wallet",true);old.load();
            old.setPackaged(PackagedComponents.parse("wallet"));
            check(old.config.selection.components.equals(Collections.singleton("wallet"))&&old.config.selection.features.isEmpty());
            old.chooseSelection(old.packaged.defaults());check(old.config.selection.components.isEmpty());
            break;
        case "inspection":
            Page p=new Page();p.metadata.values.put("selected_component_wallet",true);
            p.metadata.values.put("selected_feature_clock",false);p.load();
            Map<String,Boolean> before=new LinkedHashMap<>(p.metadata.values);
            p.confirm();PresetConfig.ApprovalSession approval=p.approval;
            p.setPackaged(PackagedComponents.parse("market,phone,clock"));p.updateChoices();
            check(p.metadata.values.equals(before)&&p.metadata.writes.isEmpty());
            check(p.config.selection.componentCsv().equals("market,phone,clock"));
            check(p.config.selection.featureCsv().equals("phone"));
            check(!p.componentChoices.get("wallet").enabled&&!p.componentChoices.get("wallet").checked);
            check(!p.featureChoices.get("privacy").enabled&&!p.featureChoices.get("privacy").checked);
            check(p.featureChoices.get("clock").enabled&&!p.featureChoices.get("clock").checked);
            check(!p.componentChoices.get("market").enabled&&p.componentChoices.get("clock").enabled);
            check(p.walletDialog==null&&p.approval==null&&p.submits==0);
            boolean expired=false;try{approval.requireActive();}catch(IllegalStateException expected){expired=true;}check(expired);
            p.chooseSelection(PresetSelection.all());
            check(p.config.selection.componentCsv().equals("market,phone,clock"));
            check(p.config.selection.featureCsv().equals("phone,clock"));
            p.componentChoices.get("xiaoai").checked=true;p.featureChoices.get("privacy").checked=true;p.selectionChanged();
            check(!p.config.selection.components.contains("xiaoai")&&!p.config.selection.features.contains("privacy"));
            p.setButtons(true);check(p.apply.enabled&&p.defaults.enabled);
            p.setPackaged(null);p.setButtons(true);
            check(!p.apply.enabled&&!p.defaults.enabled&&!p.reboot.enabled&&!p.lsp.enabled&&p.recheck.enabled);
            for(CheckBox c:p.componentChoices.values())check(!c.enabled&&!c.checked);
            for(CheckBox c:p.featureChoices.values())check(!c.enabled&&!c.checked);
            PresetSelection previous=p.config.selection;
            p.chooseSelection(PresetSelection.all());check(previous.equals(p.config.selection));
            p.componentChoices.get("wallet").checked=true;p.selectionChanged();check(previous.equals(p.config.selection));
            break;
        case "root":
            Page page=new Page();page.load();
            Capture.response=new Capture("market,phone\n","",0);
            check(page.readPackaged().features.equals(Collections.singleton("phone")));
            check(Capture.command.equals(Arrays.asList("su","-c",HELPER+"capabilities"))&&Capture.timeout==30);
            for(Capture response:new Capture[]{new Capture(full,"permission denied",1),new Capture("","",0),
                new Capture("{\"components\":\"market\"}","",0),new Capture("log\nmarket","",0),new Capture("phone","",0)}){
                Capture.response=response;boolean blocked=false;
                try{page.readPackaged();}catch(IOException expected){blocked=expected.getMessage().contains("升级")&&expected.getMessage().contains("禁止应用");}
                check(blocked);
            }
            Capture.failure=new IOException("timeout or incomplete capture");boolean blocked=false;
            try{page.readPackaged();}catch(IOException expected){blocked=true;}check(blocked);
            check(page.metadata.writes.isEmpty()&&page.submits==0);
            break;
        default:throw new AssertionError(args[0]);
        }
    }
}
'''


class PackagedComponentsUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="preset-packaged-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.work = Path(cls.temp.name)
        activity = (SOURCE / "PresetActivity.java").read_text()
        start = activity.index("        Set<String> components=new LinkedHashSet<>(),features=new LinkedHashSet<>();")
        end = activity.index("        LinearLayout box=", start)
        title_start = activity.index("private static final String[] TITLES=")
        titles = activity[title_start:activity.index(";", title_start) + 1]
        harness = HARNESS[:HARNESS.index("    public static void main(String[] args){")]
        harness = harness.replace("import java.util.*;", "import java.util.*;\nimport java.io.*;")
        harness = harness.replace("TITLES\n", titles + "\n").replace("LOAD", activity[start:end])
        harness = harness.replace("PACKAGED_CLASS", packaged_class(activity))
        methods = "\n".join(method(activity, name) for name in (
            "updateChoices", "selectionChanged", "chooseSelection", "showWalletConfirmation", "setPackaged", "setButtons"))
        harness = harness.replace("METHODS", methods + read_method(activity))
        harness = harness.replace("        String scopeFailure;", """
        final CheckBox apply=new CheckBox(),recheck=new CheckBox(),reboot=new CheckBox(),lsp=new CheckBox(),defaults=new CheckBox();
        void appendDiagnostics(String text){}
        String scopeFailure;""")
        stub = cls.work / "android/content/SharedPreferences.java"
        stub.parent.mkdir(parents=True)
        stub.write_text("package android.content; public interface SharedPreferences {boolean getBoolean(String k,boolean d);}")
        source = cls.work / "PresetWalletUiTest.java"
        source.write_text(harness + CASES)
        result = subprocess.run(["javac", "-encoding", "UTF-8", "-d", str(cls.work), str(stub),
                                 *[str(SOURCE / name) for name in ("Features.java", "PresetSelection.java", "PresetConfig.java")],
                                 str(source)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)

    def run_case(self, case):
        result = subprocess.run(["java", "-cp", str(self.work), "local.xuanyuan.unified.PresetWalletUiTest", case],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_unknown_duplicate_and_malformed_csv(self):
        self.run_case("malformed")

    def test_dependencies_and_feature_availability(self):
        self.run_case("dependencies")

    def test_wallet_defaults_and_saved_choice(self):
        self.run_case("defaults")

    def test_inspection_preserves_preferences_and_filters_ui(self):
        self.run_case("inspection")

    def test_read_only_bounded_root_capabilities_fail_closed(self):
        self.run_case("root")


if __name__ == "__main__":
    unittest.main(verbosity=2)
