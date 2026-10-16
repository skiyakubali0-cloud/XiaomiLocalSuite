package local.xuanyuan.unified;

import java.util.*;

/** Immutable whitelist and dependency closure shared by preset policy and command arguments. */
public final class PresetSelection {
    public static final List<String> COMPONENTS=Collections.unmodifiableList(Arrays.asList(
        "market","assistant","xiaoai","phone","gallery","weather","disaster","wallet","clock","calendar","mipush"));
    public static final List<String> FEATURES=Collections.unmodifiableList(Arrays.asList("phone","privacy","suggestions","warning","clock"));
    public final Set<String> components,features;

    public PresetSelection(Collection<String> components,Collection<String> features){
        Set<String> selected=canonical(components,COMPONENTS);
        this.features=Collections.unmodifiableSet(canonical(features,FEATURES));
        for(String feature:this.features)selected.add(componentFor(feature));
        if(selected.contains("phone"))selected.add("market");
        if(selected.contains("xiaoai"))selected.add("assistant");
        this.components=Collections.unmodifiableSet(canonical(selected,COMPONENTS));
    }
    public static PresetSelection all(){return new PresetSelection(COMPONENTS,FEATURES);}
    public static PresetSelection defaults(){
        List<String> components=new ArrayList<>(COMPONENTS);components.remove("wallet");
        return new PresetSelection(components,FEATURES);
    }
    public static PresetSelection parse(String components,String features){return new PresetSelection(csv(components),csv(features));}
    private static List<String> csv(String value){
        if(value==null||value.isEmpty())throw new IllegalArgumentException("空选择必须使用 -");
        return "-".equals(value)?Collections.emptyList():Arrays.asList(value.split(",",-1));
    }
    private static LinkedHashSet<String> canonical(Collection<String> values,List<String> whitelist){
        if(values==null)throw new IllegalArgumentException("缺少预设选择");
        Set<String> unique=new HashSet<>();
        for(String value:values)if(!whitelist.contains(value)||!unique.add(value))throw new IllegalArgumentException("无效或重复的预设项："+value);
        LinkedHashSet<String> result=new LinkedHashSet<>();
        for(String value:whitelist)if(unique.contains(value))result.add(value);
        return result;
    }
    private static String componentFor(String feature){
        switch(feature){
            case "privacy":case "suggestions":return "xiaoai";
            case "warning":return "disaster";
            default:return feature;
        }
    }
    /** Dependencies cannot be unchecked until the features/components requiring them are cleared. */
    public Set<String> requiredComponents(){
        Set<String> required=new LinkedHashSet<>();
        for(String feature:features)required.add(componentFor(feature));
        if(components.contains("phone"))required.add("market");
        if(components.contains("xiaoai"))required.add("assistant");
        return Collections.unmodifiableSet(canonical(required,COMPONENTS));
    }
    public String componentCsv(){return components.isEmpty()?"-":String.join(",",components);}
    public String featureCsv(){return features.isEmpty()?"-":String.join(",",features);}
    public String arguments(String action){
        if(!Arrays.asList("plan","apply","apply-wallet","migrate","reboot","lsp").contains(action))throw new IllegalArgumentException("未知固定命令");
        return action+" "+componentCsv()+" "+featureCsv();
    }
    @Override public boolean equals(Object other){
        if(!(other instanceof PresetSelection))return false;
        PresetSelection value=(PresetSelection)other;return components.equals(value.components)&&features.equals(value.features);
    }
    @Override public int hashCode(){return Objects.hash(components,features);}
}
