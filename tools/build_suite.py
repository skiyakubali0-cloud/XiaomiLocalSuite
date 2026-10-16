"""Offline reconstruction of the locked xuanyuan 1.7 Root suite (Python 3.11+)."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

COMPONENTS = ("market", "assistant", "xiaoai", "phone", "gallery", "weather", "disaster", "wallet")
LIMIT = 2**31
GENERATED = {"checksums.sha256", "control.sha256"}
ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_name(name, directory=False):
    value = name[:-1] if directory and name.endswith("/") else name
    parts = value.split("/")
    require(value and not any(c in value for c in "\\:\x00\r\n")
            and not any(ord(c) < 32 for c in value)
            and all(p not in ("", ".", "..") and not p.endswith((".", " "))
                    and not re.match(r"(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", p)
                    for p in parts),
            "Unsafe member path: " + repr(name))
    return value


def inspect_zip(archive):
    """Validate every member, including entries we will never extract."""
    members = {}
    portable_names = {}
    for info in archive.infolist():
        require(info.orig_filename == info.filename, "Truncated ZIP member name")
        name = safe_name(info.filename, info.is_dir())
        mode = info.external_attr >> 16
        require(stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR),
                "ZIP symlink or special member: " + name)
        require(name.casefold() not in portable_names, "Duplicate ZIP member: " + name)
        require(not info.flag_bits & 1 and info.file_size < LIMIT,
                "Encrypted or oversized ZIP member: " + name)
        members[name] = info
        portable_names[name.casefold()] = info
    for name in members:
        parts = name.split("/")
        for end in range(1, len(parts)):
            ancestor = portable_names.get("/".join(parts[:end]).casefold())
            require(ancestor is None or ancestor.is_dir(), "ZIP file/directory collision")
    return members


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_apk_metadata(path):
    with zipfile.ZipFile(path) as archive:
        names = inspect_zip(archive)
        require("assets/xposed_init" not in names
                and "META-INF/xposed/native_init.list" not in names,
                "Unified APK must have only the modern Java entry")
        require(archive.read("META-INF/xposed/java_init.list").decode().splitlines()
                == ["local.xuanyuan.unified.UnifiedModule"], "Unexpected APK entry points")
        require(archive.read("META-INF/xposed/scope.list") == b"", "APK default scope must be empty")
        properties = archive.read("META-INF/xposed/module.prop").decode().splitlines()
        require(sorted(properties) == sorted(("minApiVersion=102", "targetApiVersion=102",
                                              "staticScope=false")), "APK requires modern API102")


def check_apk(path, apksigner="apksigner", aapt2="aapt2"):
    """External tools inspect the staged APK; never execute its contents."""
    def run(*args):
        result = subprocess.run(list(map(str, args)), capture_output=True, text=True)
        require(result.returncode == 0, Path(args[0]).name + " verification failed")
        return result.stdout

    run(apksigner, "verify", "--verbose", path)
    badging = run(aapt2, "dump", "badging", path)
    identity = re.search(r"^package: name='([^']+)' versionCode='([^']+)'", badging, re.M)
    require(identity is not None and identity.groups() == ("local.xuanyuan.mipushcompat", "17"),
            "APK must be local.xuanyuan.mipushcompat versionCode 17")


def load_lock(source):
    lock = json.loads((source / "materials.lock.json").read_text(encoding="utf-8"))
    require(lock["schema"] == 1 and lock["target"] == {
        "device": "xuanyuan", "rom": "OS4.0.0.6.XOAEUXM", "sdk": 37},
        "Only the locked xuanyuan EEA 1.7 release is supported")
    require(re.fullmatch("[0-9a-f]{64}", lock["reference_suite"]["sha256"])
            and re.fullmatch("[0-9a-f]{64}", lock["original_unified_sha256"]), "Invalid lock hash")
    entries = {key: {} for key in (*COMPONENTS, "parent")}
    for item in lock["artifacts"]:
        component, name = item["component"], safe_name(item["path"])
        require(component in entries and name not in entries[component], "Invalid/duplicate lock entry")
        require(isinstance(item["bytes"], int) and 0 <= item["bytes"] < LIMIT
                and re.fullmatch("[0-9a-f]{64}", item["sha256"]), "Invalid material size/hash")
        require(name not in GENERATED, "Lock cannot replace generated checksums")
        entries[component][name] = item
    require(set(entries["parent"]) == {"payload/unified.apk", "payload/calendar.apk",
                                       "payload/calendar-global.apk"}, "Unexpected parent materials")
    require(entries["parent"]["payload/unified.apk"]["sha256"] == lock["original_unified_sha256"],
            "Original unified APK lock mismatch")
    return lock, entries


def copy_template(source, target):
    require(source.is_dir() and not source.is_symlink(), "Missing/linked template: " + str(source))
    target.mkdir()
    for path in sorted(source.rglob("*")):
        require(not path.is_symlink(), "Template symlink: " + str(path))
        name = safe_name(path.relative_to(source).as_posix(), path.is_dir())
        if path.is_dir():
            (target / name).mkdir(exist_ok=True)
        else:
            require(path.is_file() and name not in GENERATED, "Unexpected template file: " + name)
            (target / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target / name)


def materialize(archive, members, entries, target):
    for name, item in entries.items():
        require(name in members and not members[name].is_dir(), "Missing locked material: " + name)
        require(members[name].file_size == item["bytes"], "Material bytes mismatch: " + name)
        path = target / name
        require(not path.exists(), "Material overlaps public template: " + name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(members[name]) as stream, path.open("xb") as output:
            shutil.copyfileobj(stream, output, 1024 * 1024)
        require(path.stat().st_size == item["bytes"] and digest(path) == item["sha256"],
                "Material SHA256 mismatch: " + name)


def edit(path, pattern, replacement):
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, lambda match: replacement(match), text, flags=re.M)
    require(count == 1, "Expected one identity field in " + path.name)
    path.write_text(updated, encoding="utf-8", newline="\n")


def update_identity(parent, xiaoai, old, new):
    edit(parent / "shared.sh", r"^UNIFIED_SHA=" + old + r"$", lambda _: "UNIFIED_SHA=" + new)
    # Keep the former current APK as well as every pre-existing historical allowlist entry.
    if new != old:
        edit(parent / "shared.sh", r'^ (\[ "\$UNIFIED_LIVE_SHA" = "\$UNIFIED_SHA" \])',
             lambda m: m[0] + ' || [ "$UNIFIED_LIVE_SHA" = "' + old + '" ]')
    edit(parent / "migrate-legacy.sh", r"^SELF_SHA=" + old + r"$", lambda _: "SELF_SHA=" + new)
    if new != old:
        edit(xiaoai / "privacy.sh", r"^( [0-9a-f|]+\|" + old + r")\) ;;$",
             lambda m: m[1] + "|" + new + ") ;;")
    privacy_sha = digest(xiaoai / "privacy.sh")
    # The original 1603 CLI must be paired too; otherwise the new APK strands it.
    def paired(match):
        if match[1] == privacy_sha:
            return match[0]
        return ("  2026101603:" + match[1] + ") PAIR_XIAOAI=true;;\n"
                + "  2026101603:" + privacy_sha + ") ;;")
    edit(parent / "customize.sh", r"^  2026101603:([0-9a-f]{64})\) ;;$", paired)


def files(root):
    return sorted(p for p in root.rglob("*") if p.is_file())


def checksums(root, name, selected):
    (root / name).write_text("".join(digest(p) + "  " + p.relative_to(root).as_posix() + "\n"
                                    for p in selected), encoding="utf-8", newline="\n")


def write_zip(root, output):
    # Known sizes let zipfile use classic local headers, including streamed files.
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, allowZip64=False) as archive:
        for path in files(root):
            require(path.stat().st_size < LIMIT, "Output member exceeds classic ZIP limit")
            name = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | (0o755 if name.endswith(".sh") else 0o644)) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            info.file_size = path.stat().st_size
            with path.open("rb") as source, archive.open(info, "w", force_zip64=False) as target:
                shutil.copyfileobj(source, target, 1024 * 1024)
    require(output.stat().st_size < LIMIT, "Output ZIP must be smaller than 2 GiB")


def update_catalog(parent):
    catalog_path = parent / "webroot/catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    expected = {**{c: "payload/" + c + ".zip" for c in COMPONENTS},
                "clock": "payload/unified.apk", "mipush": "payload/unified.apk",
                "calendar": "payload/calendar.apk"}
    require(len(catalog) == len(expected) and {row["id"] for row in catalog} == set(expected),
            "Unexpected parent catalog")
    for row in catalog:
        name = expected[row["id"]]
        require(row["file"] == name, "Unexpected catalog payload")
        payload = parent / name
        sha = digest(payload)
        row.update(sha256=sha, bytes=payload.stat().st_size)
        edit(parent / "catalog.sh", r"^(" + row["id"] + r"\).*?; SHA=')[0-9a-f]{64}(';.*)$",
             lambda m: m[1] + sha + m[2])
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_suite(source, reference, unified_apk, output, *, apk_checker=check_apk):
    """apk_checker is injectable for synthetic tests only; CLI always uses SDK tools."""
    source, reference, unified_apk, output = map(Path, (source, reference, unified_apk, output))
    require(not output.exists() and not output.is_symlink(), "Refusing to overwrite output")
    require(output.suffix.lower() == ".zip", "Output must be a new .zip path")
    lock, entries = load_lock(source)
    with tempfile.TemporaryDirectory(prefix="build-suite-") as temporary:
        work = Path(temporary)
        # Snapshot explicit inputs: hash/check/use the same bytes even if callers replace them.
        ref = work / "reference.zip"
        shutil.copyfile(reference, ref)
        require(digest(ref) == lock["reference_suite"]["sha256"], "Reference suite SHA256 mismatch")
        apk = work / "unified.apk"
        shutil.copyfile(unified_apk, apk)
        validate_apk_metadata(apk)
        apk_checker(apk)
        new_sha = digest(apk)
        parent = work / "parent"
        copy_template(source / "suite/module", parent)
        with zipfile.ZipFile(ref) as archive:
            members = inspect_zip(archive)
            materialize(archive, members, entries["parent"], parent)
            shutil.copyfile(apk, parent / "payload/unified.apk")
            for component in COMPONENTS:
                nested = work / "component.zip"
                name = "payload/" + component + ".zip"
                require(name in members and not members[name].is_dir(), "Missing component: " + name)
                with archive.open(members[name]) as stream, nested.open("wb") as target:
                    shutil.copyfileobj(stream, target, 1024 * 1024)
                child = work / component
                copy_template(source / "components" / component, child)
                with zipfile.ZipFile(nested) as child_archive:
                    child_members = inspect_zip(child_archive)
                    materialize(child_archive, child_members, entries[component], child)
                if component == "xiaoai":
                    update_identity(parent, child, lock["original_unified_sha256"], new_sha)
                checksums(child, "checksums.sha256", files(child))
                write_zip(child, parent / name)
                shutil.rmtree(child)
                nested.unlink()
        update_catalog(parent)
        checksums(parent, "control.sha256", [p for p in files(parent)
                  if p.relative_to(parent).parts[0] != "payload" and p.name != "customize.sh"])
        checksums(parent, "checksums.sha256", files(parent))
        final = work / "suite.zip"
        write_zip(parent, final)
        output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation protects existing files and simultaneous builds.
        with output.open("xb") as target:
            try:
                with final.open("rb") as stream:
                    shutil.copyfileobj(stream, target, 1024 * 1024)
            except BaseException:
                target.close()
                output.unlink()
                raise
    return digest(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT, help="Public template/lock directory")
    parser.add_argument("--reference-suite", type=Path, required=True, help="Local locked 1.7 reference ZIP")
    parser.add_argument("--unified-apk", type=Path, required=True, help="Caller-signed code17 API102 APK")
    parser.add_argument("--output", type=Path, required=True, help="New private local ZIP; never overwritten")
    parser.add_argument("--apksigner", default="apksigner", help="Local Android SDK apksigner executable")
    parser.add_argument("--aapt2", default="aapt2", help="Local Android SDK aapt2 executable")
    args = parser.parse_args()
    try:
        sha = build_suite(args.source_root, args.reference_suite, args.unified_apk, args.output,
                          apk_checker=lambda p: check_apk(p, args.apksigner, args.aapt2))
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
        print("Build failed: " + str(error), file=sys.stderr)
        return 1
    print("CLEAN-INSTALL ONLY: a different signing key cannot upgrade the original signed APK.")
    print("Private local output (do not publish): " + str(args.output))
    print("SHA256: " + sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
