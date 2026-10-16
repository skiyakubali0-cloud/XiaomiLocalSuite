"""Local controller behavior tests; no ADB, Android runtime, or release edits.

Run: python3 test_control.py -v
Every fixture rereads control.sh. Only paths and the bottom CLI dispatch are
adapted; controller functions remain intact. Payload fixtures substitute catalog
digests, so payload hashing is real while no release archive is installed.
Android package paths, digests and user state are mocked independently; extracted
component scripts only record calls. A fixture helper selects catalog versions.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time
import unittest


SOURCE = Path(__file__).parent / "module-fixture"

GALLERY_HASHES = {
    "com.miui.gallery": (
        "c25c993cc1462a955b145035ee071d98781ba51370bad232a78eb567eb84cfbc",
        "be6bb05752cf667430c9359cd46fa8f4ed3552ecbe2e90a7b6279eaeb471f4a2",
        "6a9c9677a6a6ef398c3d60dad58c71942adab010b8e4e7727b2c028063c3fd9d"),
    "com.hyper.gallery.plugin": (
        "d0a6af98b4910113fb4ecf62fff349881ec1adde8291682fe500bde59eadf8d1",
        "f763216706094ca04cf2c4e67600595bbfa55f0533b8468a7c36ca2463bf9497"),
    "com.miui.mediaeditor": (
        "52343b5d46f227100fc0b75ee6eed633a431db51f95eb3c2f1ba44ad40aacefc",
        "365954e0e94263b7372fa5e6f4d244690b5edd9607b5642a1488a622732f7756",
        "e7c37c8ee2e10e8e45b60ad3ff293ad8a0b1c702f9e79aaa8df97ecfbcf4f699"),
    "com.miui.extraphoto": (
        "ca7794bb50c7ab612aab9494d0fc8fe887bfbd5a28ba3ffd8fecaba7a218c7c4",
        "b6149345f1aa4f3b84d84152b186f5c60bc6bc4c95957ac3cc232fb047722756"),
}
RETAINED_UPDATES = (
    ("market", "com.xiaomi.market", "14dd58663e83d83dc6ab0f95af88be3d2b96ca28c651e3e8f7b0144807e4c05a"),
    ("xiaoai", "com.miui.voiceassist", "caafb6930e7a9b86c46ea9fc3ab00fbd76c826026fa0f23260f39737b42c8ffa"),
)

# All Android commands terminate here. Unknown commands fail closed.
MOCK = r'''
import json, os, pathlib, sys, time
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
root = pathlib.Path(os.environ["TEST_ROOT"])
packages = json.loads(os.environ.get("TEST_PACKAGES", "{}"))
package_state = root / "package-state.json"
state = json.loads(package_state.read_text()) if package_state.exists() else {}
def record(command):
    with (root / "calls").open("a") as f:
        f.write(json.dumps(command) + "\n")
if name == "getprop":
    props = {"ro.product.device": "xuanyuan", "ro.build.version.sdk": "37",
             "ro.build.version.incremental": "OS4.0.0.6.XOAEUXM",
             "sys.boot_completed": "1"}
    props.update(json.loads(os.environ.get("TEST_PROPS", "{}")))
    print(props.get(args[0], ""))
elif name == "id" and args == ["-u"]:
    print("0")
elif name == "am" and args == ["get-current-user"]:
    print("0")
elif name == "pm" and args == ["list", "users"]:
    print("UserInfo{0:Owner:13} running")
elif name == "pm" and args[:2] == ["list", "packages"]:
    for package in packages:
        current = state.get(package, {})
        if current.get("hidden", False):
            continue
        if "-d" in args and not current.get("disabled", False):
            continue
        if args[-1] not in ("0", package) and args[-1] not in package:
            continue
        print("package:" + package)
elif name == "pm" and args[:3] == ["path", "--user", "0"] and len(args) == 4:
    if args[3] in packages:
        print("package:" + str(root / "apks" / (args[3] + ".apk")))
elif name == "pm" and len(args) == 4 and args[1:3] == ["--user", "0"] and args[0] in ("hide", "unhide", "enable", "disable-user"):
    record([name] + args)
    current = state.setdefault(args[3], {})
    if args[0] == "hide":
        current["hidden"] = os.environ.get("TEST_HIDE_NOOP") != "1"
    elif args[0] == "unhide":
        current["hidden"] = False
    else:
        current["disabled"] = args[0] == "disable-user"
    package_state.write_text(json.dumps(state))
elif name == "dumpsys" and args == ["package", "com.xiaomi.market"]:
    record([name] + args)
    hidden = str(state.get(args[1], {}).get("hidden", False)).lower()
    preferred = os.environ.get("TEST_PREFERRED_HIDDEN", "false")
    # Misleading earlier sections and another user must not verify User 0.
    print("Preferred Activities User 0:")
    print(f"    User 0: hidden={preferred}")
    print("Packages:")
    print(f"    User 0: ceDataInode=42 installed=true hidden={hidden} suspended=false")
    print("    User 10: ceDataInode=99 installed=true hidden=true")
elif name == "fixture-script":
    record([name] + args)
elif name == "settings" and args[:1] == ["get"]:
    print("null")
elif name == "cmd" and args[:2] == ["role", "get-role-holders"]:
    pass
elif name == "meta-overlayfs":
    pass
elif name == "stat" and len(args) == 3 and args[0] == "-c" and args[1] in ("%s", "%Y"):
    try:
        info = pathlib.Path(args[2]).lstat()
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    # Android stat defaults to the link itself; bytes and integer epoch seconds.
    print(info.st_size if args[1] == "%s" else info.st_mtime_ns // 1_000_000_000)
elif name == "df" and args == ["-Pk", str(root / "data")]:
    free = int(os.environ.get("TEST_FREE_KB", "16777216"))
    total = 67108864
    print("Filesystem 1024-blocks Used Available Capacity Mounted on")
    print(f"/dev/mock-data {total} {total - free} {free} {(total - free) * 100 // total}% {root / 'data'}")
elif name == "ksud":
    record(args)
    if args[:2] == ["module", "install"] and os.environ.get("TEST_GATE"):
        (root / "entered").touch()
        until = time.monotonic() + 8
        while not (root / "release").exists():
            if time.monotonic() > until:
                sys.exit(90)
            time.sleep(.02)
    elif args[:2] == ["module", "disable"] and len(args) == 3:
        (root / "data/adb/modules" / args[2] / "disable").touch()
    elif args == ["module", "list"]:
        print("[]")
elif name == "busybox" and args[:1] == ["nohup"]:
    # Keep queued jobs deterministic; tests invoke the real worker explicitly.
    (root / "launch").touch()
elif name == "busybox" and args[:2] == ["unzip", "-oq"] and args[-2] == "-d":
    record([name] + args)
    destination = pathlib.Path(args[-1])
    for filename in ("control.sh", "profiles.sh"):
        (destination / filename).write_text('fixture-script ' + destination.name + ' "$@"\n')
elif name == "busybox" and args[:1] == ["awk"]:
    os.execv("/usr/bin/awk", ["awk"] + args[1:])
elif name == "sha256sum":
    import hashlib
    if args == ["-c", "control.sha256"]:
        for line in pathlib.Path(args[1]).read_text().splitlines():
            expected, filename = line.split(None, 1)
            if hashlib.sha256(pathlib.Path(filename).read_bytes()).hexdigest() != expected:
                sys.exit(1)
    elif len(args) == 1:
        apk = pathlib.Path(args[0])
        if apk.parent == root / "apks" and apk.stem in packages:
            digest = packages[apk.stem]
        elif args[0].endswith("/product/app/MITSMClientGlobal/MITSMClientGlobal.apk") and os.environ.get("TEST_WALLET_MATCH"):
            digest = "567e8f05e4b2cbc7c203ce5f10672756ea8af0542c3fc5aafaa3e677ebcaa671"
        else:
            try:
                digest = hashlib.sha256(pathlib.Path(args[0]).read_bytes()).hexdigest()
            except OSError:
                sys.exit(1)
        print(digest + "  " + args[0])
    else:
        sys.exit(91)
else:
    print("Unexpected mock command: " + name + repr(args), file=sys.stderr)
    sys.exit(92)
'''


class ControllerTests(unittest.TestCase):
    def test_reviewed_updates_are_exact_and_component_scoped(self):
        for owner, package, digest in RETAINED_UPDATES:
            self.passes("retained_update", owner, package, digest)
        owners = ("market", "xiaoai", "assistant", "phone", "gallery", "", "market,xiaoai")
        packages = ("com.xiaomi.market", "com.miui.voiceassist", "com.miui.personalassistant", "")
        digests = tuple(row[2] for row in RETAINED_UPDATES) + ("0" * 64, "")
        for owner in owners:
            for package in packages:
                for digest in digests:
                    if (owner, package, digest) in RETAINED_UPDATES:
                        continue
                    with self.subTest(owner=owner, package=package, digest=digest):
                        self.assertNotEqual(self.run_control("retained_update", owner, package, digest).returncode, 0)
        for owner, package, digest in RETAINED_UPDATES:
            for altered in (digest.upper(), digest[:-1], digest + "0", " " + digest, digest + "\n"):
                self.assertNotEqual(self.run_control("retained_update", owner, package, altered).returncode, 0)
        self.assertEqual(self.calls(), [])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="suite-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.module = self.root / "module"
        self.state = self.root / "data/adb/xuanyuan-os4-suite-state"
        self.modules = self.root / "data/adb/modules"
        self.module.mkdir()
        self.modules.mkdir(parents=True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        mock = self.bin / "mock.py"
        mock.write_text("#!" + sys.executable + "\n" + MOCK)
        mock.chmod(0o700)
        for name in ("getprop", "id", "am", "pm", "settings", "cmd", "ksud",
                     "busybox", "sha256sum", "stat", "df", "adb", "reboot",
                     "dumpsys", "fixture-script"):
            (self.bin / name).symlink_to(mock)
        overlay = self.root / "data/adb/metamodule/meta-overlayfs"
        overlay.parent.mkdir(parents=True)
        overlay.symlink_to(mock)
        self.enable("meta-overlayfs")
        self.boot = self.root / "boot-id"
        self.boot.write_text("boot-A\n")
        source = (SOURCE / "control.sh").read_text()
        prefix, dispatch = source.rsplit('\ncase "$1" in\n', 1)
        self.assertTrue(dispatch.rstrip().endswith("esac"), "CLI dispatch changed")
        paths = {"M=${0%/*}": "M=" + shlex.quote(str(self.module)),
                 "/data": str(self.root / "data"),
                 "/product/": str(self.root / "product") + "/",
                 "/proc/sys/kernel/random/boot_id": str(self.boot)}
        for old, new in paths.items():
            prefix = prefix.replace(old, new)
        prefix = re.sub(r"^K=.*$", "K=" + shlex.quote(str(self.bin / "ksud")), prefix, flags=re.M)
        prefix = re.sub(r"^BB=.*$", "BB=" + shlex.quote(str(self.bin / "busybox")), prefix, flags=re.M)
        self.controller = self.module / "control.sh"
        self.controller.write_text(prefix + '\ntest_module_version() { lookup "$1"; [ "$#" -lt 2 ] || CODE=$2; module_version_ok; }\n"$@"\n')
        catalog = (SOURCE / "catalog.sh").read_text()
        (self.module / "payload").mkdir()
        for filename, digest in re.findall(r"FILE='([^']+)'; SHA='([^']+)'", catalog):
            content = ("test payload: " + filename).encode()
            (self.module / "payload" / filename).write_bytes(content)
            catalog = catalog.replace(digest, hashlib.sha256(content).hexdigest())
        (self.module / "catalog.sh").write_text(catalog)
        (self.module / "owned-packages.txt").write_text((SOURCE / "owned-packages.txt").read_text())
        (self.module / "control.sha256").write_text("".join(
            hashlib.sha256((self.module / name).read_bytes()).hexdigest() + "  " + name + "\n"
            for name in ("control.sh", "catalog.sh", "owned-packages.txt")))
        # macOS bash-as-sh otherwise misparses $TITLE followed by Chinese punctuation.
        self.env = dict(os.environ, PATH=str(self.bin) + ":/usr/bin:/bin",
                        LC_ALL="C", TEST_ROOT=str(self.root),
                        TEST_PACKAGES=json.dumps({p: hashes[0] for p, hashes in GALLERY_HASHES.items()}))

    def enable(self, mid):
        path = self.modules / mid
        path.mkdir(exist_ok=True)
        catalog = (SOURCE / "catalog.sh").read_text()
        match = re.search(r"MID='" + re.escape(mid) + r"';.*?CODE='([^']*)'", catalog)
        (path / "module.prop").write_text("versionCode=" + (match[1] if match else "1") + "\n")

    def run_control(self, *args, input=None, **env):
        return subprocess.run(["/bin/sh", str(self.controller), *map(str, args)],
                              input=input, text=True, capture_output=True,
                              env=dict(self.env, **env), timeout=12)

    def passes(self, *args, **kwargs):
        result = self.run_control(*args, **kwargs)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def rejects(self, message, *args, **kwargs):
        result = self.run_control(*args, **kwargs)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(message, result.stderr)
        return result

    def calls(self):
        path = self.root / "calls"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def queued(self, component="gallery"):
        self.passes("start", "install", component)
        return Path((self.state / "latest").read_text().strip())

    def test_retained_updates_pass_owned_check_but_unknown_updates_stop_restore(self):
        for owner, package, digest in RETAINED_UPDATES:
            with self.subTest(owner=owner):
                self.passes("owned_check", owner, TEST_PACKAGES=json.dumps({package: digest}))
                self.rejects("存在其他版本", "owned_check", owner,
                             TEST_PACKAGES=json.dumps({package: "0" * 64}))
        self.enable("xuanyuan-os4-market")
        job = self.queued("market")
        self.rejects("存在其他版本", "worker", job, "restore", "market",
                     TEST_PACKAGES=json.dumps({"com.xiaomi.market": "0" * 64, "com.xiaomi.mipicks": "1" * 64}))
        self.assertFalse((job / "started").exists())
        self.assertFalse((self.state / "restored/market").exists())
        self.assertEqual(self.calls(), [])

    def test_gallery_known_versions_and_unknown_versions_before_mutation(self):
        packages = {p: hashes[0] for p, hashes in GALLERY_HASHES.items()}
        for package, hashes in GALLERY_HASHES.items():
            for digest in hashes:
                with self.subTest(package=package, digest=digest):
                    self.passes("gallery_check", TEST_PACKAGES=json.dumps(dict(packages, **{package: digest})))
        self.enable("xuanyuan-os4-gallery")
        database = self.root / "data/user/0/com.miui.gallery/photos.db"
        database.parent.mkdir(parents=True)
        database.write_bytes(b"photos must survive")
        for operation in ("install", "restore"):
            self.passes("preflight", operation, "gallery")
            for package in packages:
                for digest in ("0" * 64, None):
                    with self.subTest(operation=operation, package=package, digest=digest):
                        unknown = dict(packages)
                        if digest is None:
                            del unknown[package]
                        else:
                            unknown[package] = digest
                        job = self.queued()
                        self.rejects("未经验证的相册更新", "worker", job, operation, "gallery",
                                     TEST_PACKAGES=json.dumps(unknown))
                        self.assertEqual((job / "state").read_text().strip(), "failed")
                        self.assertFalse((job / "started").exists())
                        self.assertFalse((job / "completed").exists())
                        self.assertFalse((self.state / "restored/gallery").exists())
                        self.assertFalse((self.modules / "xuanyuan-os4-gallery/disable").exists())
                        self.assertEqual(database.read_bytes(), b"photos must survive")
                        self.assertEqual(self.calls(), [])
        # Positive restore control exercises extraction, disable and profile script.
        job = self.queued()
        self.passes("worker", job, "restore", "gallery")
        self.assertIn(["module", "disable", "xuanyuan-os4-gallery"], self.calls())
        self.assertIn(["fixture-script", "extracted-gallery", "restore"], self.calls())
        self.assertTrue((self.modules / "xuanyuan-os4-gallery/disable").exists())
        self.assertTrue((self.state / "restored/gallery").exists())
        self.assertEqual(database.read_bytes(), b"photos must survive")

    def test_only_reviewed_old_gallery_can_upgrade_to_11(self):
        mid = "xuanyuan-os4-gallery"
        self.enable(mid)
        prop = self.modules / mid / "module.prop"
        for live in ("2026101401", "2026101302"):
            prop.write_text("versionCode=" + live + "\n")
            self.passes("test_module_version", "gallery")
            self.passes("preflight", "install", "gallery")
            self.passes("preflight", "restore", "gallery")
        for live in ("2026101301", "2026101402", "", "garbage"):
            with self.subTest(live=live):
                prop.write_text("versionCode=" + live + "\n")
                self.assertNotEqual(self.run_control("test_module_version", "gallery").returncode, 0)
                for operation in ("install", "restore"):
                    self.rejects("当前版本与套件不同", "preflight", operation, "gallery")
        prop.write_text("versionCode=2026101302\n")
        for target in ("2026101402", "2026101301", ""):
            self.assertNotEqual(self.run_control("test_module_version", "gallery", target).returncode, 0)
        for component in ("market", "assistant", "xiaoai", "phone", "weather", "disaster", "wallet"):
            with self.subTest(component=component):
                self.enable("xuanyuan-os4-" + component)
                self.passes("test_module_version", component)
                (self.modules / ("xuanyuan-os4-" + component) / "module.prop").write_text("versionCode=2026101302\n")
                self.assertNotEqual(self.run_control("test_module_version", component, "2026101401").returncode, 0)
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.state.exists())

    def test_market_restore_verifies_actual_user0_and_install_unhides(self):
        self.enable("xuanyuan-os4-market")
        packages = {"com.xiaomi.market": RETAINED_UPDATES[0][2], "com.xiaomi.mipicks": "1" * 64}
        self.env["TEST_PACKAGES"] = json.dumps(packages)
        self.passes("preflight", "restore", "market")
        job = self.queued("market")
        self.passes("worker", job, "restore", "market", TEST_PREFERRED_HIDDEN="false")
        self.assertEqual((job / "state").read_text().strip(), "succeeded")
        self.assertEqual(self.calls(), [
            ["module", "list"],
            ["busybox", "unzip", "-oq", str(self.module / "payload/market.zip"), "-d", str(job / "extracted-market")],
            ["fixture-script", "extracted-market", "enable"],
            ["module", "disable", "xuanyuan-os4-market"],
            ["pm", "hide", "--user", "0", "com.xiaomi.market"],
            ["dumpsys", "package", "com.xiaomi.market"],
        ])
        self.assertTrue(json.loads((self.root / "package-state.json").read_text())["com.xiaomi.market"]["hidden"])
        self.assertTrue((self.state / "restored/market").exists())
        (self.root / "calls").unlink()
        job = self.queued("market")
        self.passes("worker", job, "install", "market")
        calls = self.calls()
        unhide = ["pm", "unhide", "--user", "0", "com.xiaomi.market"]
        enable = ["pm", "enable", "--user", "0", "com.xiaomi.market"]
        self.assertIn(unhide, calls)
        self.assertIn(enable, calls)
        self.assertLess(calls.index(unhide), calls.index(enable))
        self.assertIn(["fixture-script", "extracted-market", "disable"], calls)
        self.assertFalse(json.loads((self.root / "package-state.json").read_text())["com.xiaomi.market"]["hidden"])
        self.assertFalse((self.state / "restored/market").exists())
        self.assertEqual((job / "state").read_text().strip(), "succeeded")

    def test_market_false_user0_hidden_rejects_preferred_and_other_user_match(self):
        self.enable("xuanyuan-os4-market")
        self.env["TEST_PACKAGES"] = json.dumps({"com.xiaomi.market": RETAINED_UPDATES[0][2], "com.xiaomi.mipicks": "1" * 64})
        job = self.queued("market")
        self.rejects("商店隐藏状态未通过验证", "worker", job, "restore", "market",
                     TEST_HIDE_NOOP="1", TEST_PREFERRED_HIDDEN="true")
        self.assertEqual((job / "state").read_text().strip(), "failed")
        self.assertFalse((job / "completed").exists())
        self.assertFalse((self.state / "restored/market").exists())
        self.assertFalse((self.state / "lock").exists())
        self.assertIn(["pm", "hide", "--user", "0", "com.xiaomi.market"], self.calls())
        self.assertIn(["dumpsys", "package", "com.xiaomi.market"], self.calls())

    def test_json_roundtrip_and_job_log(self):
        value = '中文\\path "quoted"\nnext\tcolumn ' + "".join(chr(i) for i in range(1, 32)) + "END"
        self.assertEqual(json.loads(self.passes("json", input=value).stdout), value)
        job = self.queued()
        (job / "message").write_text(value)
        (job / "log").write_text(value)
        result = json.loads(self.passes("job").stdout)
        self.assertEqual(result["message"], value)
        self.assertEqual(result["log"], value)
        self.assertEqual(result["state"], "queued")

    def test_ids_reject_injection_and_empty_items(self):
        self.passes("validate_ids", "market,assistant")
        marker = self.root / "injected"
        for ids in ("", ",market", "market,", "market,,assistant", "unknown",
                    "market assistant", "market\nassistant", "market;touch " + str(marker),
                    "$(touch " + str(marker) + ")", "market,`touch " + str(marker) + "`"):
            with self.subTest(ids=ids):
                result = self.run_control("start", "install", ids)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(marker.exists())
                self.assertFalse(self.state.exists(), result.stdout + result.stderr)
        self.assertEqual(self.calls(), [])

    def test_payload_tampering_stops_worker_before_install(self):
        self.passes("preflight", "install", "gallery")
        job = self.queued()
        (self.module / "payload/gallery.zip").write_bytes(b"tampered")
        self.rejects("安装文件校验失败", "worker", job, "install", "gallery")
        self.assertEqual((job / "state").read_text().strip(), "failed")
        self.assertFalse((job / "started").exists())
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.state / "lock").exists())

    def test_wrong_rom_device_or_sdk_never_queues(self):
        self.passes("platform")
        for key, value in (("ro.product.device", "nezha"), ("ro.build.version.sdk", "36"),
                           ("ro.build.version.incremental", "OS4.0.0.6.XOACNXM")):
            with self.subTest(property=key):
                self.rejects("机型或系统不受支持", "start", "install", "gallery",
                             TEST_PROPS=json.dumps({key: value}))
                self.assertFalse(self.state.exists())
        self.assertEqual(self.calls(), [])

    def test_low_disk_preflight_rejects_without_writes(self):
        self.enable("xuanyuan-os4-gallery")
        self.passes("preflight", "install", "gallery")
        self.passes("preflight", "restore", "gallery")

        def snapshot():
            return {str(p.relative_to(self.root)): (
                p.lstat().st_mode, p.lstat().st_mtime_ns,
                os.readlink(p) if p.is_symlink() else p.read_bytes() if p.is_file() else None
            ) for p in self.root.rglob("*")}

        before = snapshot()
        for operation in ("install", "restore"):
            with self.subTest(operation=operation):
                self.rejects("存储空间不足", "preflight", operation, "gallery", TEST_FREE_KB="1024")
                self.assertEqual(snapshot(), before, "Low-disk preflight modified the fixture")
                self.assertFalse(self.state.exists())
                self.assertEqual(self.calls(), [])

    def test_wallet_guard_restore_and_no_reset_marker(self):
        before = {str(p.relative_to(self.root)) for p in self.root.rglob("*")}
        self.rejects("不生成重置标记", "preflight", "install", "wallet")
        self.rejects("凭据", "preflight", "restore", "wallet")
        self.assertEqual(self.calls(), [])
        job = self.queued("wallet")
        self.passes("worker", job, "install", "wallet", TEST_WALLET_MATCH="1")
        self.assertEqual((job / "state").read_text().strip(), "succeeded")
        installs = [c for c in self.calls() if c[:2] == ["module", "install"]]
        self.assertEqual(installs, [["module", "install", str(self.module / "payload/wallet.zip")]])
        added = {str(p.relative_to(self.root)) for p in self.root.rglob("*")} - before
        self.assertFalse(any("reset" in p.lower() or "mitsm" in p.lower() for p in added), added)
        self.assertFalse((self.root / "product").exists())

    def test_dependencies_block_install_and_restore(self):
        self.rejects("LSPosed", "preflight", "install", "xiaoai")
        self.enable("zygisk_lsposed")
        self.enable("zygisksu")
        self.rejects("需要勾选智能助理", "preflight", "install", "xiaoai")
        self.passes("preflight", "install", "assistant,xiaoai")
        self.rejects("先安装商店", "preflight", "install", "phone")
        self.enable("xuanyuan-os4-xiaoai")
        self.rejects("先停用小爱", "preflight", "restore", "assistant")
        self.enable("xuanyuan-os4-phone")
        self.rejects("先恢复电话", "preflight", "restore", "market")
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.state.exists())

    def test_queued_and_running_lock_prevent_second_task(self):
        job = self.queued()
        self.rejects("已有任务", "start", "install", "gallery")
        self.assertEqual(list((self.state / "jobs").iterdir()), [job])
        proc = subprocess.Popen(["/bin/sh", str(self.controller), "worker", str(job), "install", "gallery"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                env=dict(self.env, TEST_GATE="1"))
        try:
            deadline = time.monotonic() + 6
            while not (self.root / "entered").exists() and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue((self.root / "entered").exists(), "Worker did not reach installer")
            self.assertEqual((job / "state").read_text().strip(), "running")
            self.rejects("已有任务", "start", "install", "gallery")
            self.assertEqual(list((self.state / "jobs").iterdir()), [job])
            (self.root / "release").touch()
            stdout, stderr = proc.communicate(timeout=10)
            self.assertEqual(proc.returncode, 0, stdout + stderr)
            self.assertEqual((job / "state").read_text().strip(), "succeeded")
            self.assertEqual(len([c for c in self.calls() if c[:2] == ["module", "install"]]), 1)
            self.assertFalse((self.state / "lock").exists())
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()

    def test_reboot_dead_process_and_expired_queue_are_interrupted(self):
        for cause in ("reboot", "dead-process", "expired-queue"):
            with self.subTest(cause=cause):
                job = self.queued()
                lock = self.state / "lock"
                if cause == "reboot":
                    self.boot.write_text("boot-B\n")
                elif cause == "dead-process":
                    dead = subprocess.Popen(["/usr/bin/true"])
                    dead.wait()
                    (lock / "pid").write_text(str(dead.pid))
                    (job / "state").write_text("running\n")
                else:
                    (lock / "created").write_text(str(int(time.time()) - 120))
                result = json.loads(self.passes("job").stdout)
                self.assertEqual(result["state"], "interrupted")
                self.assertIn("中断", result["message"])
                self.assertFalse(lock.exists())
                self.assertEqual(json.loads(self.passes("job").stdout), result)
        self.assertEqual(self.calls(), [])

    def test_new_lock_without_boot_metadata_survives_reconcile(self):
        lock = self.state / "lock"
        for boot_file in ("missing", "empty"):
            with self.subTest(boot_file=boot_file):
                lock.mkdir(parents=True)
                if boot_file == "empty":
                    (lock / "boot").touch()
                self.passes("reconcile")
                self.assertTrue(lock.is_dir(), "Reconcile stole a newly acquired lock")
                self.assertEqual(sorted(p.name for p in lock.iterdir()),
                                 [] if boot_file == "missing" else ["boot"])
                self.assertFalse((self.state / "latest").exists())
                # Positive cleanup control: an abandoned empty lock must not live forever.
                old = int(time.time()) - 120
                os.utime(lock, (old, old))
                self.passes("reconcile")
                self.assertFalse(lock.exists())
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    print("Testing current controller SHA256: " + hashlib.sha256((SOURCE / "control.sh").read_bytes()).hexdigest(), flush=True)
    unittest.main()
