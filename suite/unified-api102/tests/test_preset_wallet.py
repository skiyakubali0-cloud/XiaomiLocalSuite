"""Execute preset UI selection methods with host doubles; no Android runtime/device."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/local/xuanyuan/unified"


def method(source, name):
    start = source.index("    private void " + name + "(")
    opening = source.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


HARNESS = r'''
package local.xuanyuan.unified;
import java.util.*;

public final class PresetWalletUiTest {
    static void check(boolean value){if(!value)throw new AssertionError();}
    static final class CheckBox {
        boolean checked,enabled;String text="";
        boolean isChecked(){return checked;}
        void setChecked(boolean value){checked=value;}
        void setEnabled(boolean value){enabled=value;}
        void setText(String value){text=value;}
    }
    static final class Label {void setText(String value){}}
    static final class Handler {void removeCallbacks(Object value){}}
    static final class Toast {
        static final int LENGTH_LONG=1;
        static Toast makeText(Object owner,String text,int length){throw new AssertionError(text);}
        void show(){}
    }
    static final class SharedPreferences {
        final Map<String,Boolean> values=new LinkedHashMap<>();
        final Set<String> reads=new HashSet<>(),writes=new HashSet<>();
        boolean getBoolean(String key,boolean fallback){reads.add(key);return values.getOrDefault(key,fallback);}
        Editor edit(){return new Editor();}
        final class Editor {
            Editor putBoolean(String key,boolean value){writes.add(key);values.put(key,value);return this;}
            Editor remove(String key){values.remove(key);return this;}
            boolean commit(){return true;}
        }
    }
    static final class XposedService {}
    static final class AlertDialog {
        interface Click {void onClick(AlertDialog dialog,int which);}
        interface Event {void run(AlertDialog dialog);}
        Click positive,negative;Event cancel,dismiss;String title,message;boolean shown;
        void show(){shown=true;}
        void dismiss(){shown=false;if(dismiss!=null)dismiss.run(this);}
        void setOnDismissListener(Event event){dismiss=event;}
        static final class Builder {
            final AlertDialog dialog=new AlertDialog();
            Builder(Object owner){}
            Builder setTitle(String text){dialog.title=text;return this;}
            Builder setMessage(String text){dialog.message=text;return this;}
            Builder setPositiveButton(String text,Click click){dialog.positive=click;return this;}
            Builder setNegativeButton(String text,Click click){dialog.negative=click;return this;}
            Builder setOnCancelListener(Event event){dialog.cancel=event;return this;}
            AlertDialog create(){return dialog;}
        }
    }
    static final class Page {
        TITLES
        final SharedPreferences metadata=new SharedPreferences();
        final Map<String,CheckBox> componentChoices=new LinkedHashMap<>(),featureChoices=new LinkedHashMap<>();
        boolean updatingChoices,busy;int generation;
        PresetConfig config,approvalConfig;
        PresetConfig.ApprovalSession approval,approved;
        XposedService approvedService,service=new XposedService();
        Object lastPlan,poll;
        boolean active=true;
        PresetConfig.ApprovalSession walletConfirmation;
        AlertDialog walletDialog;
        interface Work {String run(PresetConfig selected,PresetConfig.Adapter a) throws Exception;}
        int submits;
        void submit(Work work){submits++;}
        void confirm(){approval=new PresetConfig.ApprovalSession();approvalConfig=config;walletConfirmation=approval;showWalletConfirmation();}
        String scopeFailure;
        final Handler handler=new Handler();
        final Label scopeReview=new Label(),status=new Label();
        Page(){
            for(String id:PresetSelection.COMPONENTS)componentChoices.put(id,new CheckBox());
            for(String id:PresetSelection.FEATURES)featureChoices.put(id,new CheckBox());
        }
        PresetConfig configuration(PresetSelection value){return new PresetConfig(value,Collections.emptySet(),"fixture");}
        void load(){LOAD updateChoices();}
        METHODS
    }
    public static void main(String[] args){
        final String wallet="selected_component_wallet";
        Page fresh=new Page();fresh.load();
        check(fresh.config.selection.equals(PresetSelection.defaults()));
        check(fresh.config.selection.components.size()==10&&fresh.config.selection.features.size()==5);
        check(fresh.metadata.reads.contains(wallet)&&!fresh.componentChoices.get("wallet").checked&&fresh.componentChoices.get("wallet").enabled);
        Page old=new Page();old.metadata.values.put(wallet,true);old.load();
        check(old.metadata.reads.contains(wallet)&&old.config.selection.components.contains("wallet"));
        CheckBox row=old.componentChoices.get("wallet");
        check(row.checked&&row.enabled&&row.text.contains("首次 TSM 迁移须单独确认"));
        check(old.componentChoices.size()==11&&old.featureChoices.size()==5);
        for(String id:PresetSelection.COMPONENTS)check(old.componentChoices.get(id).checked);
        check(!old.componentChoices.get("market").enabled&&!old.componentChoices.get("assistant").enabled);
        old.chooseSelection(PresetSelection.parse("-","-"));
        check(old.metadata.writes.contains(wallet)&&!old.metadata.values.get(wallet));
        old.componentChoices.get("wallet").checked=true;old.selectionChanged();
        check(old.config.selection.componentCsv().equals("wallet")&&row.checked&&row.enabled&&old.metadata.values.get(wallet));
        check(old.config.selection.arguments("apply-wallet").equals("apply-wallet wallet -"));
        old.componentChoices.get("phone").checked=true;old.selectionChanged();
        check(old.config.selection.componentCsv().equals("market,phone,wallet"));
        check(!old.componentChoices.get("market").enabled&&old.componentChoices.get("assistant").enabled);
        Page reopened=new Page();reopened.metadata.values.putAll(old.metadata.values);reopened.load();
        check(reopened.config.selection.equals(old.config.selection)&&reopened.componentChoices.get("wallet").checked);
        old.chooseSelection(PresetSelection.defaults());
        check(old.config.selection.equals(fresh.config.selection)&&!row.checked&&row.enabled);
        check(!old.metadata.values.get(wallet));
        Page off=new Page();off.metadata.values.putAll(old.metadata.values);off.load();
        check(off.config.selection.equals(PresetSelection.defaults())&&off.metadata.reads.contains(wallet));
        off.busy=true;off.updateChoices();check(!off.componentChoices.get("wallet").enabled);
        off.componentChoices.get("wallet").checked=true;off.selectionChanged();
        check(!off.config.selection.components.contains("wallet")&&!off.componentChoices.get("wallet").checked);
        off.busy=false;off.updateChoices();check(off.componentChoices.get("wallet").enabled);
        Page accepted=new Page();accepted.load();accepted.confirm();
        AlertDialog yes=accepted.walletDialog;
        check(yes.shown&&yes.message.contains("清除旧小米 TSM 本地数据")&&yes.message.contains("Keystore")&&yes.message.contains("现有卡可能失效"));
        yes.positive.onClick(yes,1);check(accepted.submits==1);
        Page cancelled=new Page();cancelled.load();cancelled.confirm();
        AlertDialog no=cancelled.walletDialog;no.negative.onClick(no,0);no.dismiss();
        check(cancelled.submits==0&&cancelled.walletDialog==null);
        boolean expired=false;try{cancelled.approval.requireActive();}catch(IllegalStateException expected){expired=true;}check(expired);
        Page backed=new Page();backed.load();backed.confirm();backed.walletDialog.cancel.run(backed.walletDialog);
        expired=false;try{backed.approval.requireActive();}catch(IllegalStateException expected){expired=true;}check(expired&&backed.submits==0);
        for(int change=0;change<5;change++){
            Page stale=new Page();stale.load();stale.confirm();AlertDialog dialog=stale.walletDialog;
            if(change==0)stale.active=false;
            if(change==1)stale.busy=true;
            if(change==2)stale.config=stale.configuration(PresetSelection.all());
            if(change==3)stale.service=new XposedService();
            if(change==4)stale.approval=new PresetConfig.ApprovalSession();
            dialog.positive.onClick(dialog,1);check(stale.submits==0);
        }
        Page changed=new Page();changed.load();changed.confirm();PresetConfig.ApprovalSession before=changed.approval;
        AlertDialog previous=changed.walletDialog;changed.chooseSelection(PresetSelection.all());
        check(!previous.shown&&changed.walletConfirmation==null&&changed.approval==null&&changed.metadata.values.get(wallet));
        previous.positive.onClick(previous,1);check(changed.submits==0);
        Set<String> expectedWrites=new HashSet<>();
        for(String id:PresetSelection.COMPONENTS)expectedWrites.add("selected_component_"+id);
        for(String id:PresetSelection.FEATURES)expectedWrites.add("selected_feature_"+id);
        check(changed.metadata.writes.equals(expectedWrites));
        System.out.println("PASS wallet defaults, old true/false, toggle/save/reopen, dependencies, busy UI, explicit dialog and stale/cancelled confirmation");
    }
}
'''


class WalletPresetUi(unittest.TestCase):
    def test_actual_ui_selection_and_confirmation_methods(self):
        activity = (SOURCE / "PresetActivity.java").read_text()
        start = activity.index("        Set<String> components=new LinkedHashSet<>(),features=new LinkedHashSet<>();")
        end = activity.index("        LinearLayout box=", start)
        title_start = activity.index("private static final String[] TITLES=")
        titles = activity[title_start:activity.index(";", title_start) + 1]
        harness = HARNESS.replace("TITLES\n", titles + "\n").replace("LOAD", activity[start:end])
        harness = harness.replace("METHODS", "\n".join(method(activity, name) for name in
                                  ("updateChoices", "selectionChanged", "chooseSelection", "showWalletConfirmation")))
        self.assertIn("()->chooseSelection(PresetSelection.defaults())", activity)
        with tempfile.TemporaryDirectory(prefix="preset-wallet-ui-") as temp:
            work = Path(temp)
            stub = work / "android/content/SharedPreferences.java"
            stub.parent.mkdir(parents=True)
            stub.write_text("package android.content; public interface SharedPreferences {boolean getBoolean(String k,boolean d);}")
            test = work / "PresetWalletUiTest.java"
            test.write_text(harness)
            result = subprocess.run(["javac", "-encoding", "UTF-8", "-d", str(work), str(stub),
                                     *[str(SOURCE / name) for name in ("Features.java", "PresetSelection.java", "PresetConfig.java")],
                                     str(test)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run(["java", "-cp", str(work), "local.xuanyuan.unified.PresetWalletUiTest"],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
