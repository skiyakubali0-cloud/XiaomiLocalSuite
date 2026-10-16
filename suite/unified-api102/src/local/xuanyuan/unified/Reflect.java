package local.xuanyuan.unified;

import java.io.FileInputStream;
import java.lang.reflect.*;
import java.security.MessageDigest;
import java.util.*;

/** Reflection for the exact OEM classes; no legacy Xposed dependency. */
public final class Reflect {
    private Reflect() { }
    public static Class<?> type(String name, ClassLoader loader) throws ClassNotFoundException {
        return Class.forName(name, false, loader);
    }
    private static Class<?> owner(Object object) { return object instanceof Class ? (Class<?>)object : object.getClass(); }
    private static Object receiver(Object object) { return object instanceof Class ? null : object; }
    private static Field field(Class<?> owner, String name) throws NoSuchFieldException {
        for (Class<?> c=owner;c!=null;c=c.getSuperclass()) {
            try { Field f=c.getDeclaredField(name);f.setAccessible(true);return f; }
            catch (NoSuchFieldException ignored) { }
        }
        throw new NoSuchFieldException(owner.getName()+"."+name);
    }
    public static Object get(Object object, String name) throws ReflectiveOperationException { return field(owner(object),name).get(receiver(object)); }
    public static void set(Object object, String name, Object value) throws ReflectiveOperationException { field(owner(object),name).set(receiver(object),value); }
    public static void setStaticBoolean(Class<?> owner,String name,boolean value) throws ReflectiveOperationException {
        Field f=field(owner,name);
        if(f.getType()!=boolean.class||!Modifier.isStatic(f.getModifiers()))throw new IllegalArgumentException("static boolean required");
        Class.forName(owner.getName(),true,owner.getClassLoader());
        try{f.setBoolean(null,value);}
        catch(IllegalAccessException denied){
            if(!Modifier.isFinal(f.getModifiers()))throw denied;
            // Android17 target37 forbids reflective final-field writes. Exact OEM
            // callers use this only before Application/provider initialization.
            Class<?> type=Class.forName("jdk.internal.misc.Unsafe");
            Object unsafe=field(type,"theUnsafe").get(null);
            Object base=type.getMethod("staticFieldBase",Field.class).invoke(unsafe,f);
            long offset=(Long)type.getMethod("staticFieldOffset",Field.class).invoke(unsafe,f);
            type.getMethod("putBooleanVolatile",Object.class,long.class,boolean.class).invoke(unsafe,base,offset,value);
        }
        if(f.getBoolean(null)!=value)throw new IllegalAccessException("static boolean readback failed");
    }
    public static Method method(Class<?> owner,String name,Class<?>... types) throws NoSuchMethodException {
        for(Class<?> c=owner;c!=null;c=c.getSuperclass()) {
            try { Method m=c.getDeclaredMethod(name,types);m.setAccessible(true);return m; }
            catch(NoSuchMethodException ignored) { }
        }
        throw new NoSuchMethodException(owner.getName()+"."+name);
    }
    private static Class<?> boxed(Class<?> c) {
        if(!c.isPrimitive())return c;
        if(c==int.class)return Integer.class;if(c==boolean.class)return Boolean.class;
        if(c==long.class)return Long.class;if(c==byte.class)return Byte.class;
        if(c==short.class)return Short.class;if(c==char.class)return Character.class;
        if(c==float.class)return Float.class;if(c==double.class)return Double.class;
        return Void.class;
    }
    private static boolean matches(Class<?>[] types,Object[] args) {
        if(types.length!=args.length)return false;
        for(int i=0;i<types.length;i++)if(args[i]==null?types[i].isPrimitive():!boxed(types[i]).isInstance(args[i]))return false;
        return true;
    }
    private static boolean moreSpecific(Class<?>[] a,Class<?>[] b) {
        for(int i=0;i<a.length;i++)if(!boxed(b[i]).isAssignableFrom(boxed(a[i])))return false;
        return true;
    }
    private static <T extends Executable> T choose(List<T> options) throws NoSuchMethodException {
        T result=null;
        for(T a:options) {
            boolean best=true;
            for(T b:options)if(a!=b&&!moreSpecific(a.getParameterTypes(),b.getParameterTypes())){best=false;break;}
            if(best){if(result!=null)throw new NoSuchMethodException("Ambiguous exact OEM reflection");result=a;}
        }
        if(result==null)throw new NoSuchMethodException("No exact compatible OEM member");
        result.setAccessible(true);return result;
    }
    public static Object call(Object object,String name,Object...args) throws ReflectiveOperationException {
        for(Class<?> c=owner(object);c!=null;c=c.getSuperclass()) {
            List<Method> candidates=new ArrayList<>();
            for(Method m:c.getDeclaredMethods())if(m.getName().equals(name)&&!m.isBridge()&&matches(m.getParameterTypes(),args)
                    &&(!(object instanceof Class)||Modifier.isStatic(m.getModifiers())))candidates.add(m);
            if(!candidates.isEmpty())return choose(candidates).invoke(receiver(object),args);
        }
        throw new NoSuchMethodException(owner(object).getName()+"."+name);
    }
    public static Object construct(Class<?> owner,Object...args) throws ReflectiveOperationException {
        List<Constructor<?>> candidates=new ArrayList<>();
        for(Constructor<?> c:owner.getDeclaredConstructors())if(matches(c.getParameterTypes(),args))candidates.add(c);
        return choose(candidates).newInstance(args);
    }
    public static String hashFile(String path) throws Exception {
        MessageDigest hash=MessageDigest.getInstance("SHA-256");
        try(FileInputStream in=new FileInputStream(path)){byte[] b=new byte[65536];int n;while((n=in.read(b))>0)hash.update(b,0,n);}
        StringBuilder out=new StringBuilder();for(byte b:hash.digest())out.append(String.format("%02x",b&255));return out.toString();
    }
}
