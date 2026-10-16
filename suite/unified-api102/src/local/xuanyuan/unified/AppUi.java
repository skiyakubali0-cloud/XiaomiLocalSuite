package local.xuanyuan.unified;

import android.app.Activity;
import android.content.Context;
import android.content.res.ColorStateList;
import android.content.res.Configuration;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.graphics.drawable.StateListDrawable;
import android.text.SpannableString;
import android.text.Spanned;
import android.text.style.ForegroundColorSpan;
import android.text.style.RelativeSizeSpan;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.widget.*;

/** Presentation only; no preferences, framework calls or Root operations. */
final class AppUi {
    static final int ACCENT=0xffff6b35;
    private AppUi() { }
    static boolean dark(Context c){return (c.getResources().getConfiguration().uiMode&Configuration.UI_MODE_NIGHT_MASK)==Configuration.UI_MODE_NIGHT_YES;}
    static int ink(Context c){return dark(c)?0xfff1f2f5:0xff202832;}
    static int muted(Context c){return dark(c)?0xff9fa7b5:0xff838b97;}
    static int surface(Context c){return dark(c)?0xff1d222b:0xffffffff;}
    static int background(Context c){return dark(c)?0xff10141b:0xfff5f7fa;}
    static int dp(Context c,int n){return Math.round(n*c.getResources().getDisplayMetrics().density);}
    static void theme(Activity a){a.setTheme(dark(a)?android.R.style.Theme_Material_NoActionBar:android.R.style.Theme_Material_Light_NoActionBar);}
    private static GradientDrawable shape(int color,int radius){GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(radius);return d;}
    static LinearLayout page(Activity a,String title,String subtitle){
        LinearLayout box=new LinearLayout(a);box.setOrientation(1);box.setBackgroundColor(background(a));
        box.setPadding(dp(a,20),dp(a,10),dp(a,20),dp(a,24));
        LinearLayout frame=new LinearLayout(a);frame.setOrientation(1);frame.setBackgroundColor(background(a));
        frame.setOnApplyWindowInsetsListener((v,insets)->{
            android.graphics.Insets b=insets.getInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.displayCutout());
            v.setPadding(b.left,b.top,b.right,b.bottom);
            WindowInsetsController controller=a.getWindow().getInsetsController();
            int flags=WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS|WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
            if(controller!=null)controller.setSystemBarsAppearance(dark(a)?0:flags,flags);
            return insets;
        });
        ScrollView scroll=new ScrollView(a);scroll.setFillViewport(true);scroll.setVerticalScrollBarEnabled(false);scroll.setBackgroundColor(background(a));scroll.addView(box);frame.addView(scroll,new LinearLayout.LayoutParams(-1,-1));a.setContentView(frame);
        LinearLayout masthead=new LinearLayout(a);masthead.setGravity(Gravity.CENTER_VERTICAL);
        ImageView logo=new ImageView(a);logo.setImageDrawable(new UiIcon(0,ACCENT,dark(a)?0xff3c2a24:0xffffece3,dp(a,28)));masthead.addView(logo,new LinearLayout.LayoutParams(dp(a,28),dp(a,28)));
        TextView brand=text(a,"  LOCAL SUITE",10,muted(a));brand.setLetterSpacing(.12f);brand.setTypeface(null,Typeface.BOLD);masthead.addView(brand,new LinearLayout.LayoutParams(0,-2,1));
        TextView tag=text(a,"本地工具",10,muted(a));tag.setPadding(dp(a,10),dp(a,5),dp(a,10),dp(a,5));tag.setBackground(shape(surface(a),dp(a,20)));masthead.addView(tag);box.addView(masthead);
        TextView heading=text(a,title,28,ink(a));heading.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));space(box,heading,14,0);
        space(box,text(a,subtitle,12,muted(a)),4,16);
        return box;
    }
    static TextView text(Context c,String value,int size,int color){TextView v=new TextView(c);v.setText(value);v.setTextSize(size);v.setTextColor(color);v.setLineSpacing(dp(c,3),1);return v;}
    static void space(LinearLayout box,View child,int top,int bottom){LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.topMargin=dp(box.getContext(),top);p.bottomMargin=dp(box.getContext(),bottom);box.addView(child,p);}
    static LinearLayout card(LinearLayout box){Context c=box.getContext();LinearLayout card=new LinearLayout(c);card.setOrientation(1);card.setPadding(dp(c,14),dp(c,8),dp(c,14),dp(c,8));card.setBackground(shape(surface(c),dp(c,20)));space(box,card,0,10);return card;}
    static LinearLayout hero(LinearLayout box){Context c=box.getContext();LinearLayout card=card(box);GradientDrawable bg=new GradientDrawable(GradientDrawable.Orientation.TL_BR,new int[]{0xff283441,0xff18232f});bg.setCornerRadius(dp(c,22));card.setBackground(bg);card.setPadding(dp(c,18),dp(c,16),dp(c,18),dp(c,16));LinearLayout line=new LinearLayout(c);line.setGravity(Gravity.CENTER_VERTICAL);TextView title=text(c,"运行状态",11,0xffb9c5d2);line.addView(title,new LinearLayout.LayoutParams(0,-2,1));TextView api=text(c,"API 102",10,0xfff9bd93);api.setPadding(dp(c,8),dp(c,3),dp(c,8),dp(c,3));api.setBackground(shape(0xff3c4248,dp(c,8)));line.addView(api);card.addView(line);return card;}
    static void section(LinearLayout box,String title){TextView label=text(box.getContext(),title,14,ink(box.getContext()));label.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));space(box,label,12,10);}
    static void divider(LinearLayout box){Context c=box.getContext();View line=new View(c);line.setBackgroundColor(dark(c)?0xff2b313b:0xfff0f2f5);LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,dp(c,1));p.leftMargin=dp(c,48);box.addView(line,p);}
    static ColorStateList tint(Context c){return new ColorStateList(new int[][]{new int[]{-android.R.attr.state_enabled},new int[]{android.R.attr.state_checked},new int[]{}},new int[]{dark(c)?0xff515158:0xffd8d8df,ACCENT,muted(c)});}
    static Switch toggle(LinearLayout box,String title,String detail,int kind){
        Context c=box.getContext();int[] colors={0xffea8651,0xff5b91df,0xff54a38e,0xffd67d8d,0xff9184cf};int color=colors[kind-1];
        LinearLayout row=new LinearLayout(c);row.setGravity(Gravity.CENTER_VERTICAL);row.setMinimumHeight(dp(c,66));row.setPadding(0,dp(c,7),0,dp(c,7));
        ImageView icon=new ImageView(c);icon.setImageDrawable(new UiIcon(kind,color,(dark(c)?0x25:0x12)<<24|(color&0xffffff),dp(c,36)));LinearLayout.LayoutParams ip=new LinearLayout.LayoutParams(dp(c,36),dp(c,36));ip.rightMargin=dp(c,12);row.addView(icon,ip);
        LinearLayout labels=new LinearLayout(c);labels.setOrientation(1);TextView name=text(c,title,15,ink(c));name.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));labels.addView(name);space(labels,text(c,detail,11,muted(c)),3,0);row.addView(labels,new LinearLayout.LayoutParams(0,-2,1));
        Switch v=new Switch(c);v.setShowText(false);v.setContentDescription(title+"，"+detail);v.setMinHeight(dp(c,48));v.setMinWidth(dp(c,48));v.setSwitchMinWidth(dp(c,40));v.setSplitTrack(false);
        GradientDrawable thumb=shape(0xffffffff,dp(c,11));thumb.setSize(dp(c,22),dp(c,22));thumb.setStroke(dp(c,1),0x0a000000);v.setThumbDrawable(thumb);
        StateListDrawable track=new StateListDrawable();GradientDrawable on=shape(ACCENT,dp(c,14));on.setSize(dp(c,42),dp(c,26));GradientDrawable off=shape(dark(c)?0xff46505e:0xffe4e8ee,dp(c,14));off.setSize(dp(c,42),dp(c,26));track.addState(new int[]{android.R.attr.state_checked},on);track.addState(new int[]{},off);v.setTrackDrawable(track);
        LinearLayout.LayoutParams sp=new LinearLayout.LayoutParams(dp(c,48),dp(c,48));sp.leftMargin=dp(c,8);row.addView(v,sp);row.setOnClickListener(view->v.performClick());box.addView(row,new LinearLayout.LayoutParams(-1,-2));return v;
    }
    static void choice(LinearLayout box,CheckBox v){Context c=box.getContext();v.setTextSize(15);v.setTextColor(ink(c));v.setButtonTintList(tint(c));v.setMinHeight(dp(c,58));v.setPadding(0,dp(c,7),0,dp(c,7));box.addView(v,new LinearLayout.LayoutParams(-1,-2));}
    static Button button(LinearLayout box,String title,boolean primary,Runnable action){
        Context c=box.getContext();Button v=new Button(c);v.setText(title);v.setTextSize(15);v.setAllCaps(false);v.setTypeface(null,primary?Typeface.BOLD:Typeface.NORMAL);v.setMinHeight(dp(c,52));v.setMinimumHeight(dp(c,52));
        v.setGravity(primary?Gravity.CENTER:Gravity.CENTER_VERTICAL|Gravity.START);v.setPadding(dp(c,18),dp(c,12),dp(c,18),dp(c,12));v.setStateListAnimator(null);
        v.setTextColor(new ColorStateList(new int[][]{new int[]{-android.R.attr.state_enabled},new int[]{}},new int[]{muted(c),primary?0xffffffff:ink(c)}));
        StateListDrawable states=new StateListDrawable();states.addState(new int[]{-android.R.attr.state_enabled},shape(primary?(dark(c)?0xff303137:0xffe8e8ed):surface(c),dp(c,17)));states.addState(new int[]{},shape(primary?ACCENT:surface(c),dp(c,17)));
        v.setBackground(new RippleDrawable(ColorStateList.valueOf(dark(c)?0x33ffffff:0x16000000),states,null));v.setOnClickListener(view->action.run());space(box,v,0,10);return v;
    }
    static Button shortcut(LinearLayout row,String title,String detail,int icon,Runnable action){Context c=row.getContext();Button b=button(row,title+"\n"+detail,false,action);SpannableString label=new SpannableString(title+"\n"+detail);label.setSpan(new RelativeSizeSpan(.73f),title.length()+1,label.length(),Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);label.setSpan(new ForegroundColorSpan(muted(c)),title.length()+1,label.length(),Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);b.setText(label);b.setTextSize(14);b.setPadding(dp(c,12),dp(c,15),dp(c,10),dp(c,15));b.setMinHeight(dp(c,80));b.setCompoundDrawables(new UiIcon(icon,ACCENT,dark(c)?0xff3c2a24:0xfffff0e8,dp(c,28)),null,null,null);b.setCompoundDrawablePadding(dp(c,8));LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,-2,1);if(row.getChildCount()>1)lp.leftMargin=dp(c,10);lp.bottomMargin=dp(c,10);b.setLayoutParams(lp);return b;}
    static LinearLayout details(LinearLayout box,String title){
        LinearLayout card=card(box),content=new LinearLayout(box.getContext());content.setOrientation(1);content.setVisibility(View.GONE);
        TextView label=text(box.getContext(),title+"  ＋",15,ink(box.getContext()));label.setMinHeight(dp(box.getContext(),36));label.setGravity(Gravity.CENTER_VERTICAL);label.setContentDescription(title+"，点击展开");label.setClickable(true);label.setFocusable(true);label.setOnClickListener(v->{boolean show=content.getVisibility()!=View.VISIBLE;content.setVisibility(show?View.VISIBLE:View.GONE);label.setText(title+(show?"  −":"  ＋"));label.setContentDescription(title+(show?"，点击收起":"，点击展开"));});
        card.addView(label);card.addView(content);return content;
    }
}
