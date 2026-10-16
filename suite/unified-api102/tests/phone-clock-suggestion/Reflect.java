package local.xuanyuan.unified;

import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.HashMap;
import java.util.Map;

// Test-only implementation of the externally supplied helper contract.
public final class Reflect {
    static final Map<String, String> hashes = new HashMap<>();
    static final Map<String, Integer> hashReads = new HashMap<>();
    static String fail;

    private static void check(String operation) throws ReflectiveOperationException {
        if (operation.equals(fail)) throw new ReflectiveOperationException(operation);
    }

    public static Class<?> type(String name, ClassLoader loader) throws Throwable {
        check("type:" + name);
        return Class.forName(name, false, loader);
    }

    private static Field field(Class<?> type, String name) throws NoSuchFieldException {
        for (Class<?> c = type; c != null; c = c.getSuperclass()) {
            try {
                Field field = c.getDeclaredField(name);
                field.setAccessible(true);
                return field;
            } catch (NoSuchFieldException ignored) { }
        }
        throw new NoSuchFieldException(name);
    }

    public static Object get(Object target, String name) throws Throwable {
        check("get:" + name);
        return field(target instanceof Class ? (Class<?>) target : target.getClass(), name)
                .get(target instanceof Class ? null : target);
    }

    public static void set(Object target, String name, Object value) throws Throwable {
        check("set:" + name);
        field(target instanceof Class ? (Class<?>) target : target.getClass(), name)
                .set(target instanceof Class ? null : target, value);
    }

    public static void setStaticBoolean(Class<?> target,String name,boolean value) throws Throwable {
        set(target,name,value);
    }

    public static Object call(Object target, String name, Object... args) throws Throwable {
        check("call:" + name);
        Class<?> type = target instanceof Class ? (Class<?>) target : target.getClass();
        for (Class<?> c = type; c != null; c = c.getSuperclass()) {
            for (Method method : c.getDeclaredMethods()) {
                if (!method.getName().equals(name) || method.getParameterCount() != args.length
                        || (target instanceof Class && !Modifier.isStatic(method.getModifiers()))) continue;
                boolean matches = true;
                Class<?>[] params = method.getParameterTypes();
                for (int i = 0; i < args.length; i++) {
                    Class<?> param = params[i];
                    if (param == boolean.class) param = Boolean.class;
                    if (param == int.class) param = Integer.class;
                    if (args[i] != null && !param.isInstance(args[i])) matches = false;
                }
                if (!matches) continue;
                method.setAccessible(true);
                try {
                    return method.invoke(target instanceof Class ? null : target, args);
                } catch (InvocationTargetException e) {
                    throw e.getCause();
                }
            }
        }
        throw new NoSuchMethodException(name);
    }

    public static Object construct(Class<?> type, Object... args) throws Throwable {
        for (java.lang.reflect.Constructor<?> ctor : type.getDeclaredConstructors()) {
            if (ctor.getParameterCount() == args.length) return ctor.newInstance(args);
        }
        throw new NoSuchMethodException(type.getName());
    }

    public static String hashFile(String path) throws Throwable {
        check("hash:" + path);
        hashReads.put(path, hashReads.getOrDefault(path, 0) + 1);
        return hashes.get(path);
    }

    public static Method method(Class<?> type, String name, Class<?>... parameters) throws Throwable {
        Method method = type.getDeclaredMethod(name, parameters);
        method.setAccessible(true);
        return method;
    }
}
