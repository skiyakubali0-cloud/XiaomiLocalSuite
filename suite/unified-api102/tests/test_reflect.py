from pathlib import Path
import subprocess,tempfile
p=Path(__file__).resolve().parents[1]
s='''import local.xuanyuan.unified.Reflect;
public class ReflectionTest {
 static int n;static void ok(boolean b){n++;if(!b)throw new AssertionError(n);}
 static class Flags {static boolean mutable;static final boolean fixed=Boolean.parseBoolean("false");static int number=7;boolean instance;}
 static class Parent {private int inherited=7;private String hidden(){return "parent";}}
 static class Child extends Parent {private String pick(Object x){return "object";}private String pick(String x){return "string";}private static String stat(int x){return "n"+x;}private String fail(){throw new IllegalStateException("same cause");}}
 static class Made {String kind;Made(Object x){kind="object";}Made(String x){kind="string";}}
 public static void main(String[] args)throws Exception {
  Child c=new Child();ok(Reflect.get(c,"inherited").equals(7));Reflect.set(c,"inherited",8);ok(Reflect.get(c,"inherited").equals(8));
  ok(Reflect.call(c,"hidden").equals("parent"));ok(Reflect.call(c,"pick","x").equals("string"));ok(Reflect.call(c,"pick",new Object()).equals("object"));
  ok(Reflect.call(Child.class,"stat",2).equals("n2"));ok(((Made)Reflect.construct(Made.class,"x")).kind.equals("string"));
  try{Reflect.call(Child.class,"pick","x");throw new AssertionError();}catch(NoSuchMethodException expected){ok(true);}
  try{Reflect.call(c,"fail");throw new AssertionError();}catch(java.lang.reflect.InvocationTargetException expected){ok(expected.getCause() instanceof IllegalStateException);}
  ok(Reflect.method(Child.class,"hidden").getDeclaringClass()==Parent.class);
  Reflect.setStaticBoolean(Flags.class,"mutable",true);ok(Reflect.get(Flags.class,"mutable").equals(true));
  Reflect.setStaticBoolean(Flags.class,"mutable",false);ok(Reflect.get(Flags.class,"mutable").equals(false));
  try{Reflect.set(Flags.class,"fixed",true);throw new AssertionError();}catch(IllegalAccessException expected){ok(true);}
  Reflect.setStaticBoolean(Flags.class,"fixed",true);ok(Reflect.get(Flags.class,"fixed").equals(true));
  Reflect.setStaticBoolean(Flags.class,"fixed",false);ok(Reflect.get(Flags.class,"fixed").equals(false));
  try{Reflect.setStaticBoolean(Flags.class,"number",true);throw new AssertionError();}catch(IllegalArgumentException expected){ok(Flags.number==7);}
  try{Reflect.setStaticBoolean(Flags.class,"instance",true);throw new AssertionError();}catch(IllegalArgumentException expected){ok(!new Flags().instance);}
  try{Reflect.setStaticBoolean(Flags.class,"absent",true);throw new AssertionError();}catch(NoSuchFieldException expected){ok(true);}
  System.out.println("PASS "+n+" production reflection assertions");
 }
}'''
with tempfile.TemporaryDirectory(prefix='reflect-') as d:
 t=Path(d);(t/'ReflectionTest.java').write_text(s)
 subprocess.run(['javac','-d',str(t),str(p/'src/local/xuanyuan/unified/Reflect.java'),str(t/'ReflectionTest.java')],check=True)
 subprocess.run(['java','--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','-cp',str(t),'ReflectionTest'],check=True)
