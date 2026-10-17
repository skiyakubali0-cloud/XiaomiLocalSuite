"""Exact offline derivations for generated suite materials, never a reference ZIP.

INPUTS maps required input SHA-256 to byte length (stock plus public tool JARs).
STOCK_INPUTS and TOOL_INPUTS separate firmware/APK inputs from build dependencies.
INPUT_PROVENANCE records descriptions or official artifact coordinates/URLs.
lookup(sha256) must return bytes or None. Known recipes with missing/corrupt inputs
raise ValueError; unrelated component/path pairs return None without a lookup.
Warning generation requires JDK 17+ on PATH or JAVA_HOME. All tools are provided
through lookup; this module never downloads, installs, signs or resets anything.
"""
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RECIPES = json.loads((ROOT / "recipes/generated.json").read_text(encoding="utf-8"))
STOCK_INPUTS = {x["sha256"]: x["bytes"] for x in RECIPES["inputs"]}
TOOL_INPUTS = {x["sha256"]: x["bytes"] for x in RECIPES["tools"]}
INPUTS = {**STOCK_INPUTS, **TOOL_INPUTS}
INPUT_PROVENANCE = {x["sha256"]: dict(x) for x in [*RECIPES["inputs"], *RECIPES["tools"]]}

# Own transformation source only. OEM class/method bodies come from the caller APK.
WARNING_SOURCE = r'''
import java.io.File;
import java.util.*;
import com.android.tools.smali.dexlib2.*;
import com.android.tools.smali.dexlib2.iface.*;
import com.android.tools.smali.dexlib2.iface.instruction.*;
import com.android.tools.smali.dexlib2.iface.reference.FieldReference;
import com.android.tools.smali.dexlib2.immutable.*;
import com.android.tools.smali.dexlib2.immutable.instruction.ImmutableInstruction21s;
import com.android.tools.smali.dexlib2.rewriter.*;
import com.android.tools.smali.dexlib2.writer.pool.DexPool;

public class WarningRecipe {
    private static final Set<String> POLICE_METHODS = Set.of(
        "Loj/o;->i(Landroid/content/Context;)V",
        "Lkl/a;->onReceive(Landroid/content/Context;Landroid/content/Intent;)V",
        "Lcom/miui/warningcenter/policeassist/PaSettingActivity;->onCreate(Landroid/os/Bundle;)V",
        "Lcom/miui/policeassist/EPSManager;->postEPS(Landroid/location/Location;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;JLjava/lang/String;)V");
    static String signature(Method m) {
        return m.getDefiningClass() + "->" + m.getName() + "("
            + String.join("", m.getParameterTypes()) + ")" + m.getReturnType();
    }
    static boolean scoped(Method m) {
        String c = m.getDefiningClass();
        return c.startsWith("Lcom/miui/earthquakewarning/")
            || c.startsWith("Lcom/miui/warningcenter/disasterwarning/")
            || c.equals("Lcom/miui/warningcenter/WarningCenterMainActivity;")
            || POLICE_METHODS.contains(signature(m));
    }
    static boolean region(Instruction i) {
        if (i.getOpcode() != Opcode.SGET_BOOLEAN) return false;
        FieldReference f = (FieldReference) ((ReferenceInstruction) i).getReference();
        return f.getDefiningClass().equals("Lmiui/os/Build;")
            && f.getName().equals("IS_INTERNATIONAL_BUILD") && f.getType().equals("Z");
    }
    public static void main(String[] args) throws Exception {
        Opcodes ops = Opcodes.forDexVersion(39);
        var container = DexFileFactory.loadDexContainer(new File(args[0]), ops);
        List<ClassDef> patched = new ArrayList<>();
        DexRewriter rewrite = new DexRewriter(new RewriterModule() {
            public Rewriter<Method> getMethodRewriter(Rewriters r) {
                MethodRewriter selected = new MethodRewriter(r);
                return m -> scoped(m) ? selected.rewrite(m) : m;
            }
            public Rewriter<Instruction> getInstructionRewriter(Rewriters r) {
                return i -> region(i) ? new ImmutableInstruction21s(Opcode.CONST_16,
                    ((OneRegisterInstruction) i).getRegisterA(), 0) : i;
            }
        });
        int count = 0;
        Map<String, Integer> policeCounts = new TreeMap<>();
        for (String entry : container.getDexEntryNames()) {
            for (ClassDef c : container.getEntry(entry).getDexFile().getClasses()) {
                int changes = 0;
                for (Method m : c.getMethods()) {
                    if (!scoped(m) || m.getImplementation() == null) continue;
                    for (Instruction i : m.getImplementation().getInstructions()) {
                        if (!region(i)) continue;
                        if (POLICE_METHODS.contains(signature(m))) policeCounts.merge(signature(m), 1, Integer::sum);
                        changes++;
                    }
                }
                if (changes == 0) continue;
                patched.add(ImmutableClassDef.of(rewrite.getClassDefRewriter().rewrite(c)));
                count += changes;
            }
        }
        if (count != 21 || patched.size() != 18 || !policeCounts.keySet().equals(POLICE_METHODS)
                || policeCounts.values().stream().anyMatch(n -> n != 1))
            throw new IllegalStateException("Unexpected region gate/class count");
        DexPool.writeTo(args[1], new ImmutableDexFile(ops, patched));
    }
}
'''


def _identity(data, digest, size, label):
    if not isinstance(data, bytes) or len(data) != size or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(label + " identity mismatch: " + digest)
    return data


def _input(digest, lookup):
    data = lookup(digest)
    if data is None:
        raise ValueError("Missing recipe input: " + digest + " (" + str(INPUTS[digest]) + " bytes)")
    return _identity(data, digest, INPUTS[digest], "Recipe input")


def _assistant(stock):
    recipe = RECIPES["assistant"]
    route = bytes.fromhex(recipe["route_text_hex"])
    _identity(route, recipe["route_text_sha256"], 380, "Own route text")
    source = ROOT / recipe["assembly_source"]
    _identity(source.read_bytes(), recipe["assembly_sha256"], source.stat().st_size, "Assembly source")
    data = bytearray(stock)
    if data[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", data, 18)[0] != 183:
        raise ValueError("Assistant requires little-endian ELF64 AArch64")
    start, branch = 0x44500, 0x38ed4
    end = start + len(route)
    if any(data[start:end]) or struct.unpack_from("<I", data, branch)[0] != 0x900000a8:
        raise ValueError("Assistant patch site is not stock")
    ph = struct.unpack_from("<Q", data, 32)[0]
    size, count = struct.unpack_from("<HH", data, 54)
    if size != 56 or ph + size * count > len(data):
        raise ValueError("Invalid assistant program headers")
    segments = [ph + i * size for i in range(count)
                if struct.unpack_from("<IIQ", data, ph + i * size) == (1, 5, 0)]
    if len(segments) != 1 or struct.unpack_from("<QQ", data, segments[0] + 32) != (0x44498, 0x44498):
        raise ValueError("Unexpected assistant executable segment")
    struct.pack_into("<I", data, branch, 0x14000000 + (start - branch) // 4)
    data[start:end] = route
    struct.pack_into("<QQ", data, segments[0] + 32, end, end)
    return bytes(data)



def _weather(apk, recipe):
    with zipfile.ZipFile(BytesIO(apk)) as archive:
        entries = [entry for entry in archive.infolist() if entry.filename == recipe["member"]]
        if len(entries) != 1:
            raise ValueError("Weather APK must contain exactly one original library")
        stock = archive.read(entries[0])
    _identity(stock, recipe["original_library_sha256"], recipe["original_library_bytes"], "Weather library")
    offset = recipe["offset"]
    before = bytes.fromhex(recipe["before_hex"])
    if len(before) != 16 or stock[offset:offset + 16] != before:
        raise ValueError("Weather PLT patch site is not stock")
    replacement = struct.pack("<IIII", 0x52800000, 0xd65f03c0, 0xd503201f, 0xd503201f)
    return stock[:offset] + replacement + stock[offset + 16:]


def _run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        # External diagnostics can include private caller paths; do not echo them.
        raise ValueError(Path(command[0]).name + " recipe tool failed (exit " + str(result.returncode) + ")")


def _java(name):
    home = os.environ.get("JAVA_HOME")
    tool = str(Path(home) / "bin" / name) if home else shutil.which(name)
    if not tool:
        raise ValueError("Warning recipe requires JDK 17+: " + name)
    return tool


def _warning(apk, lookup):
    jars = [(tool["file"], _input(tool["sha256"], lookup)) for tool in RECIPES["tools"]]
    with tempfile.TemporaryDirectory(prefix="xiaomi-warning-recipe-") as directory:
        work = Path(directory)
        source, input_apk, output = work / "WarningRecipe.java", work / "stock.apk", work / "warning.dex"
        source.write_text(WARNING_SOURCE, encoding="utf-8")
        input_apk.write_bytes(apk)
        for name, data in jars:
            (work / name).write_bytes(data)
        classpath = os.pathsep.join(str(work / name) for name, _ in jars)
        _run([_java("javac"), "--release", "17", "-encoding", "UTF-8", "-cp", classpath,
              "-d", str(work), str(source)])
        _run([_java("java"), "-cp", str(work) + os.pathsep + classpath,
              "WarningRecipe", str(input_apk), str(output)])
        return output.read_bytes()


def generate(item, lookup):
    """Return exact generated bytes, or None for a component/path without a recipe."""
    key = (item.get("component"), item.get("path"))
    recipe = next((r for r in (RECIPES["assistant"], RECIPES["warning"], *RECIPES["weather"])
                   if key == (r["output"]["component"], r["output"]["path"])), None)
    marker = next((r for r in RECIPES["markers"] if key == (r["component"], r["path"])), None)
    if recipe is None and marker is None:
        return None
    expected = recipe["output"] if recipe else marker
    if item.get("sha256") != expected["sha256"] or type(item.get("bytes")) is not int or item["bytes"] != expected["bytes"]:
        raise ValueError("Requested generated material identity mismatch")
    try:
        if marker is not None:
            data = marker["text"].encode("utf-8")
        else:
            stock = _input(recipe["input_sha256"], lookup)
            if recipe is RECIPES["assistant"]:
                data = _assistant(stock)
            elif recipe is RECIPES["warning"]:
                data = _warning(stock, lookup)
            else:
                data = _weather(stock, recipe)
        return _identity(data, expected["sha256"], expected["bytes"], "Generated material")
    except (OSError, struct.error, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        raise ValueError("Recipe generation failed: " + type(error).__name__) from error
