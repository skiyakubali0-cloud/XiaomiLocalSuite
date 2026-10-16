package local.xuanyuan.disastercompat;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.content.Intent;
import android.widget.Toast;

public final class EntryActivity extends Activity {
    public void onCreate(Bundle state) {
        super.onCreate(state);
        new AlertDialog.Builder(this)
            .setTitle("预警与报警定位")
            .setItems(new String[]{"自然灾害与地震预警", "报警定位"}, (dialog, which) -> open(which))
            .setNegativeButton("取消", (dialog, which) -> finish())
            .setOnCancelListener(dialog -> finish())
            .show();
    }
    private void open(int which) {
        try {
            startActivity(new Intent().setClassName("com.miui.securitycenter", which == 0
                ? "com.miui.warningcenter.WarningCenterMainActivity"
                : "com.miui.warningcenter.policeassist.PaSettingActivity"));
        } catch (Exception e) {
            Toast.makeText(this, "请安装自然灾害预警模块，启用对应 LSPosed 模块并重启", Toast.LENGTH_LONG).show();
        }
        finish();
    }
}
