package local.xuanyuan.mipushcompat;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/** Reads DEX definitions only: no foreign ClassLoader, DexFile or class execution. */
public final class SdkScanner {
    public static final class Result {
        public final Set<String> classes = new LinkedHashSet<>();
        public final Set<String> guardClasses = new LinkedHashSet<>();
        public final List<String> errors = new ArrayList<>();
        public String status() {
            return !classes.isEmpty() ? "sdk_detected" : !errors.isEmpty() ? "unverified" : "not_detected";
        }
    }

    /** Cheap metadata identity for startup; deliberately no APK reads or hashes. */
    public static String sourceIdentity(List<String> paths) {
        StringBuilder identity = new StringBuilder();
        for (String path : paths) {
            File file = new File(path);
            if (!file.isFile() || !file.canRead()) return "";
            identity.append(path.length()).append(':').append(path).append(':').append(file.length()).append(':')
                    .append(file.lastModified()).append(';');
        }
        return identity.toString();
    }

    public static Result scan(List<String> paths) {
        Result result = new Result();
        if (paths.isEmpty()) result.errors.add("No APK paths supplied");
        for (String path : paths) {
            try (ZipFile apk = new ZipFile(path)) {
                java.util.Enumeration<? extends ZipEntry> entries = apk.entries();
                while (entries.hasMoreElements()) {
                    ZipEntry entry = entries.nextElement();
                    if (!entry.getName().matches("classes(?:[2-9]|[1-9][0-9]+)?\\.dex")) continue;
                    try (InputStream input = apk.getInputStream(entry)) {
                        ByteArrayOutputStream output = new ByteArrayOutputStream();
                        byte[] buffer = new byte[8192];
                        int count;
                        while ((count = input.read(buffer)) != -1) {
                            if (output.size() + count > 64 * 1024 * 1024) throw new IOException("DEX exceeds scan limit");
                            output.write(buffer, 0, count);
                        }
                        Result dex = parse(output.toByteArray());
                        result.classes.addAll(dex.classes);
                        result.guardClasses.addAll(dex.guardClasses);
                    } catch (IOException | IllegalArgumentException | IndexOutOfBoundsException error) {
                        result.errors.add(entry.getName() + ": " + error.getClass().getSimpleName());
                    }
                }
            } catch (IOException error) {
                result.errors.add("APK unreadable: " + error.getClass().getSimpleName());
            }
        }
        return result;
    }

    public static Result parse(byte[] data) {
        Dex dex = new Dex(data);
        Result result = new Result();
        for (int i = 0; i < dex.classCount; i++) {
            int offset = dex.classes + i * 32;
            String descriptor = dex.type(dex.word(offset));
            if (!descriptor.startsWith("Lcom/xiaomi/mipush/sdk/")) continue;
            String name = descriptor.substring(1, descriptor.length() - 1).replace('/', '.');
            result.classes.add(name);
            int cursor = dex.word(offset + 24);
            if (cursor == 0) continue;
            int[] position = {cursor};
            int[] counts = new int[4];
            for (int j = 0; j < 4; j++) counts[j] = dex.uleb(position);
            for (int j = 0; j < counts[0] + counts[1]; j++) {
                dex.uleb(position); dex.uleb(position);
            }
            for (int j = 2; j < 4; j++) {
                int index = 0;
                for (int k = 0; k < counts[j]; k++) {
                    index += dex.uleb(position);
                    int flags = dex.uleb(position), code = dex.uleb(position);
                    if (index < 0 || index >= dex.methodCount) throw new IllegalArgumentException("method index");
                    int method = dex.methods + index * 8;
                    if (!dex.string(dex.word(method + 4)).equals("shouldUseMIUIPush")
                            || !dex.type(dex.half(method)).equals(descriptor)) continue;
                    int protoIndex = dex.half(method + 2);
                    if (protoIndex >= dex.protoCount) throw new IllegalArgumentException("proto index");
                    int proto = dex.protos + protoIndex * 12, params = dex.word(proto + 8);
                    if ((flags & 9) == 9 && code != 0 && dex.type(dex.word(proto + 4)).equals("Z")
                            && params != 0 && dex.word(params) == 1
                            && dex.type(dex.half(params + 4)).equals("Landroid/content/Context;")) {
                        result.guardClasses.add(name);
                    }
                }
            }
        }
        return result;
    }

    private static final class Dex {
        final byte[] data;
        final ByteBuffer buffer;
        final int strings, stringCount, types, typeCount, protos, protoCount, methods, methodCount, classes, classCount;
        Dex(byte[] data) {
            this.data = data;
            buffer = ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN);
            if (data.length < 112 || !new String(data, 0, 4, StandardCharsets.US_ASCII).equals("dex\n")
                    || data[7] != 0 || word(32) != data.length || word(36) != 112 || word(40) != 0x12345678)
                throw new IllegalArgumentException("unsupported DEX header");
            stringCount = word(56); strings = table(56, 4);
            typeCount = word(64); types = table(64, 4);
            protoCount = word(72); protos = table(72, 12);
            methodCount = word(88); methods = table(88, 8);
            classCount = word(96); classes = table(96, 32);
        }
        int table(int header, int width) {
            int size = word(header), offset = word(header + 4);
            if (size < 0 || offset < 0 || (long) offset + (long) size * width > data.length)
                throw new IllegalArgumentException("DEX table");
            return offset;
        }
        int word(int offset) { return buffer.getInt(offset); }
        int half(int offset) { return buffer.getShort(offset) & 65535; }
        int uleb(int[] position) {
            int value = 0;
            for (int shift = 0; shift < 35; shift += 7) {
                int b = data[position[0]++] & 255;
                value |= (b & 127) << shift;
                if ((b & 128) == 0 && value >= 0) return value;
            }
            throw new IllegalArgumentException("ULEB128");
        }
        String string(int index) {
            if (index < 0 || index >= stringCount) throw new IllegalArgumentException("string index");
            int[] position = {word(strings + index * 4)};
            uleb(position);
            int start = position[0], end = start;
            while (end < data.length && data[end] != 0) end++;
            if (end == data.length) throw new IllegalArgumentException("string end");
            return new String(data, start, end - start, StandardCharsets.UTF_8);
        }
        String type(int index) {
            if (index < 0 || index >= typeCount) throw new IllegalArgumentException("type index");
            return string(word(types + index * 4));
        }
    }

    /** Host verification entry point; never used to start Android services. */
    public static void main(String[] args) {
        Result result = scan(Arrays.asList(args));
        System.out.println(result.status());
        System.out.println("classes=" + result.classes.size() + " guards=" + result.guardClasses.size() + " errors=" + result.errors.size());
        for (String name : result.guardClasses) System.out.println(name);
    }
}
