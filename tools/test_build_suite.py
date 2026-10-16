"""Synthetic offline tests; no OEM binaries, Android device, SDK or network required."""
import io
import json
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

import build_suite as builder


def sha(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


def zipped(items):
    stream = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # Deliberate duplicate-name fixtures.
        with zipfile.ZipFile(stream, "w") as archive:
            for name, data in items:
                archive.writestr(name, data)
    return stream.getvalue()


def fake_apk(**overrides):
    members = {
        "AndroidManifest.xml": b"synthetic binary manifest; external checker is injected",
        "classes.dex": b"synthetic code17",
        "META-INF/xposed/java_init.list": b"local.xuanyuan.unified.UnifiedModule\n",
        "META-INF/xposed/scope.list": b"",
        "META-INF/xposed/module.prop": b"minApiVersion=102\ntargetApiVersion=102\nstaticScope=false\n",
    }
    members.update(overrides)
    return zipped(members.items())


class SuiteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "public source"
        self.source.mkdir()
        self.original = b"synthetic reference unified APK"
        self.old = sha(self.original)
        self.new_apk = fake_apk()
        self.apk = self.root / "caller signed.apk"
        self.apk.write_bytes(self.new_apk)
        self.reference = self.root / "reference.zip"
        self.output = self.root / "private output" / "suite.zip"
        actual_lock = json.loads((builder.ROOT / "materials.lock.json").read_text())
        for relative in ("suite/module", *("components/" + c for c in builder.COMPONENTS)):
            shutil.copytree(builder.ROOT / relative, self.source / relative)
        for p in self.source.rglob("*"):
            if p.is_file():
                p.write_bytes(p.read_bytes().replace(actual_lock["original_unified_sha256"].encode(),
                                                     self.old.encode()))
        self.parent = self.source / "suite/module"
        self.privacy = self.source / "components/xiaoai/privacy.sh"
        self.original_privacy_sha = builder.digest(self.privacy)
        customize = self.parent / "customize.sh"
        customize.write_text(re.sub(r"2026101603:[0-9a-f]{64}\) ;;",
                                   "2026101603:" + self.original_privacy_sha + ") ;;",
                                   customize.read_text()))
        self.binary = {c: ("system/product/app/" + c + "/payload.apk",
                           ("\x00exact synthetic binary " + c).encode()) for c in builder.COMPONENTS}
        self.parent_binary = {"payload/calendar.apk": b"calendar original\0",
                              "payload/calendar-global.apk": b"global original\0",
                              "payload/unified.apk": self.original}
        self.lock = {"schema": 1, "target": actual_lock["target"],
                     "reference_suite": {"name": "synthetic-1.7.zip", "sha256": ""},
                     "original_unified_sha256": self.old, "artifacts": []}
        for component, (name, data) in self.binary.items():
            self.lock["artifacts"].append(dict(component=component, path=name, sha256=sha(data), bytes=len(data)))
        for name, data in self.parent_binary.items():
            self.lock["artifacts"].append(dict(component="parent", path=name, sha256=sha(data), bytes=len(data)))
        self.rewrite_reference()
        self.checked = []

    def rewrite_reference(self, *, outer_extra=(), child_extra=(), corrupt=None):
        items = list(self.parent_binary.items()) + [("customize.sh", b"DO NOT COPY REFERENCE SCRIPTS")]
        for component, (name, data) in self.binary.items():
            if corrupt == component:
                data = bytes([data[0] ^ 1]) + data[1:]
            nested = zipped([(name, data), ("customize.sh", b"DO NOT COPY"),
                             *(child_extra if component == "market" else ())])
            items.append(("payload/" + component + ".zip", nested))
        self.reference.write_bytes(zipped([*items, *outer_extra]))
        self.lock["reference_suite"]["sha256"] = builder.digest(self.reference)
        self.save_lock()

    def save_lock(self):
        (self.source / "materials.lock.json").write_text(json.dumps(self.lock))

    def build(self, **kwargs):
        def checker(path):
            self.assertEqual(path.read_bytes(), self.new_apk)
            self.checked.append(path)
        return builder.build_suite(self.source, self.reference, self.apk, self.output,
                                   apk_checker=kwargs.pop("apk_checker", checker), **kwargs)

    def verify_checksums(self, archive, name, expected):
        lines = archive.read(name).decode().splitlines()
        self.assertEqual({line.split("  ", 1)[1] for line in lines}, set(expected))
        for line in lines:
            digest, member = line.split("  ", 1)
            self.assertEqual(digest, sha(archive.read(member)), member)

    def verify_classic(self, data):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                header = struct.unpack_from("<4s5H3I2H", data, info.header_offset)
                self.assertEqual(header[0], b"PK\x03\x04")
                self.assertLess(header[1], 45)  # No ZIP64 local header.
                self.assertNotEqual(header[7], 0xffffffff)
                self.assertNotEqual(header[8], 0xffffffff)
                extra = data[info.header_offset + 30 + header[-2]:
                             info.header_offset + 30 + header[-2] + header[-1]]
                self.assertEqual(extra, b"")
            self.assertLess(len(data), 2**31)

    def test_complete_rebuild_preserves_binaries_guards_and_precise_hashes(self):
        result = self.build()
        self.assertEqual(result, builder.digest(self.output))
        self.assertEqual(len(self.checked), 1)
        self.verify_classic(self.output.read_bytes())
        new_sha = sha(self.new_apk)
        with zipfile.ZipFile(self.output) as parent:
            self.assertEqual(parent.read("payload/unified.apk"), self.new_apk)
            for name, data in self.parent_binary.items():
                if name != "payload/unified.apk":
                    self.assertEqual(parent.read(name), data)
            changed = {"shared.sh", "migrate-legacy.sh", "customize.sh", "catalog.sh", "webroot/catalog.json"}
            for path in builder.files(self.parent):
                name = path.relative_to(self.parent).as_posix()
                if name not in changed:
                    self.assertEqual(parent.read(name), path.read_bytes(), name)
            shared = parent.read("shared.sh").decode()
            self.assertIn("UNIFIED_SHA=" + new_sha, shared)
            self.assertIn('[ "$UNIFIED_LIVE_SHA" = "' + self.old + '" ]', shared)
            original_shared = (self.parent / "shared.sh").read_text()
            expected_shared = original_shared.replace("UNIFIED_SHA=" + self.old, "UNIFIED_SHA=" + new_sha)
            expected_shared = expected_shared.replace(
                ' [ "$UNIFIED_LIVE_SHA" = "$UNIFIED_SHA" ]',
                ' [ "$UNIFIED_LIVE_SHA" = "$UNIFIED_SHA" ] || [ "$UNIFIED_LIVE_SHA" = "' + self.old + '" ]', 1)
            self.assertEqual(shared, expected_shared)
            for old_hash in re.findall(r"[0-9a-f]{64}", original_shared):
                self.assertIn(old_hash, shared)  # Includes original and all historical allowlists.
            self.assertEqual(parent.read("migrate-legacy.sh"),
                             (self.parent / "migrate-legacy.sh").read_bytes().replace(
                                 ("SELF_SHA=" + self.old).encode(), ("SELF_SHA=" + new_sha).encode()))
            catalog = json.loads(parent.read("webroot/catalog.json"))
            before_catalog = json.loads((self.parent / "webroot/catalog.json").read_text())
            for before, row in zip(before_catalog, catalog):
                data = parent.read(row["file"])
                self.assertEqual(row["sha256"], sha(data))
                self.assertEqual(row["bytes"], len(data))
                self.assertEqual({k: v for k, v in row.items() if k not in {"sha256", "bytes"}},
                                 {k: v for k, v in before.items() if k not in {"sha256", "bytes"}})
                self.assertRegex(parent.read("catalog.sh").decode(),
                                 re.escape(row["id"]) + r"\).*SHA='" + sha(data) + "'")
            for component, (name, binary) in self.binary.items():
                nested = parent.read("payload/" + component + ".zip")
                self.verify_classic(nested)
                with zipfile.ZipFile(io.BytesIO(nested)) as child:
                    self.assertEqual(child.read(name), binary)
                    for template in builder.files(self.source / "components" / component):
                        relative = template.relative_to(self.source / "components" / component).as_posix()
                        if component == "xiaoai" and relative == "privacy.sh":
                            self.assertEqual(child.read(relative), template.read_bytes().replace(
                                (self.old + ") ;;").encode(), (self.old + "|" + new_sha + ") ;;").encode()))
                            privacy_sha = sha(child.read(relative))
                        else:
                            self.assertEqual(child.read(relative), template.read_bytes(), component + "/" + relative)
                    self.verify_checksums(child, "checksums.sha256", set(child.namelist()) - {"checksums.sha256"})
            customize = parent.read("customize.sh").decode()
            self.assertIn("2026101603:" + privacy_sha + ") ;;", customize)
            self.assertIn("2026101603:" + self.original_privacy_sha + ") PAIR_XIAOAI=true;;", customize)
            expected_customize = (self.parent / "customize.sh").read_text().replace(
                "2026101603:" + self.original_privacy_sha + ") ;;",
                "2026101603:" + self.original_privacy_sha + ") PAIR_XIAOAI=true;;\n"
                + "  2026101603:" + privacy_sha + ") ;;")
            self.assertEqual(customize, expected_customize)
            self.verify_checksums(parent, "control.sha256", {n for n in parent.namelist()
                                  if not n.startswith("payload/") and n not in
                                  {"customize.sh", "control.sha256", "checksums.sha256"}})
            self.verify_checksums(parent, "checksums.sha256", set(parent.namelist()) - {"checksums.sha256"})
        self.assertEqual(self.apk.read_bytes(), self.new_apk)
        self.assertEqual((self.privacy).read_bytes().count(new_sha.encode()), 0)

    def test_reference_sha_rejected_before_checker(self):
        self.reference.write_bytes(self.reference.read_bytes() + b"tampered")
        with self.assertRaisesRegex(ValueError, "Reference suite SHA256 mismatch"):
            self.build()
        self.assertFalse(self.checked)
        self.assertFalse(self.output.exists())

    def test_material_sha_rejected_even_when_outer_hash_matches(self):
        self.rewrite_reference(corrupt="market")
        with self.assertRaisesRegex(ValueError, "Material SHA256 mismatch"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_material_size_and_missing_rejected(self):
        for mutation in ("bytes", "missing"):
            with self.subTest(mutation=mutation):
                entry = self.lock["artifacts"][0]
                original = dict(entry)
                if mutation == "bytes":
                    entry["bytes"] += 1
                else:
                    entry["path"] = "missing.apk"
                self.save_lock()
                with self.assertRaisesRegex(ValueError, "Material bytes mismatch|Missing locked material"):
                    self.build()
                entry.update(original)
        self.assertFalse(self.output.exists())

    def test_dangerous_members_rejected_in_parent_and_children(self):
        symlink = zipfile.ZipInfo("unused-link")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        cases = [[("../escape", b"x")], [("/absolute", b"x")], [("C:/drive", b"x")],
                 [("a\\b", b"x")], [("a/./b", b"x")], [("a//b", b"x")],
                 [(".. /escape", b"x")], [("NUL.apk", b"x")], [("trailing.", b"x")],
                 [("case", b"x"), ("CASE", b"x")],
                 [("line\nbreak", b"x")], [("duplicate", b"1"), ("duplicate", b"2")],
                 [("alias", b"x"), ("alias/", b"")], [(symlink, b"target")],
                 [("file", b"x"), ("file/child", b"x")]]
        for level in ("parent", "child"):
            for items in cases:
                with self.subTest(level=level, items=items):
                    self.rewrite_reference(**{("outer_extra" if level == "parent" else "child_extra"): items})
                    with self.assertRaises(ValueError):
                        self.build()
                    self.assertFalse(self.output.exists())

    def test_apk_metadata_rejected(self):
        for override in ({"META-INF/xposed/scope.list": b"android\n"},
                         {"META-INF/xposed/java_init.list": b"one\ntwo\n"},
                         {"META-INF/xposed/module.prop": b"minApiVersion=101\n"},
                         {"assets/xposed_init": b"legacy"},
                         {"META-INF/xposed/native_init.list": b"native"}):
            with self.subTest(override=override):
                self.apk.write_bytes(fake_apk(**override))
                with self.assertRaises(ValueError):
                    self.build()
                self.assertFalse(self.output.exists())

    def test_apk_duplicate_and_symlink_rejected(self):
        symlink = zipfile.ZipInfo("unused-link")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        for items in ([("classes.dex", b"a"), ("classes.dex", b"b")], [("../escape", b"x")],
                      [(symlink, b"target")]):
            self.apk.write_bytes(zipped(items))
            with self.assertRaises(ValueError):
                self.build()
        self.assertFalse(self.checked)

    def test_apk_checker_failure_does_not_create_output(self):
        def reject(path):
            raise ValueError("signature rejected")
        with self.assertRaisesRegex(ValueError, "signature rejected"):
            self.build(apk_checker=reject)
        self.assertFalse(self.output.exists())

    def test_existing_output_never_overwritten(self):
        self.output.parent.mkdir()
        self.output.write_bytes(b"keep")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.build()
        self.assertEqual(self.output.read_bytes(), b"keep")

    def test_output_created_during_build_never_overwritten(self):
        def concurrent_writer(path):
            self.output.parent.mkdir()
            self.output.write_bytes(b"concurrent output")
        with self.assertRaises(FileExistsError):
            self.build(apk_checker=concurrent_writer)
        self.assertEqual(self.output.read_bytes(), b"concurrent output")

    def test_existing_output_symlink_never_followed(self):
        self.output.parent.mkdir()
        destination = self.root / "never create.zip"
        try:
            self.output.symlink_to(destination)
        except OSError:
            self.skipTest("Symlink creation unavailable")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.build()
        self.assertFalse(destination.exists())

    def test_lock_duplicates_and_traversal_rejected(self):
        self.lock["artifacts"].append(dict(self.lock["artifacts"][0]))
        self.save_lock()
        with self.assertRaisesRegex(ValueError, "duplicate lock"):
            self.build()
        self.lock["artifacts"].pop()
        self.lock["artifacts"][0]["path"] = "../../escape.apk"
        self.save_lock()
        with self.assertRaisesRegex(ValueError, "Unsafe member path"):
            self.build()

    def test_exact_identity_fields_required(self):
        shared = self.parent / "shared.sh"
        shared.write_text(shared.read_text().replace("UNIFIED_SHA=" + self.old, "UNIFIED_SHA=unknown"))
        with self.assertRaisesRegex(ValueError, "Expected one identity field"):
            self.build()
        self.assertFalse(self.output.exists())

    @unittest.skipUnless(hasattr(__import__("os"), "symlink"), "Symlinks unavailable")
    def test_template_symlink_rejected(self):
        path = self.parent / "linked"
        try:
            path.symlink_to(self.apk)
        except OSError:
            self.skipTest("Symlink creation unavailable")
        with self.assertRaisesRegex(ValueError, "Template symlink"):
            self.build()

    def test_material_cannot_overwrite_template(self):
        name, data = self.binary["market"]
        target = self.source / "components/market" / name
        target.parent.mkdir(parents=True)
        target.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "overlaps public template"):
            self.build()


class SDKCheckerTests(unittest.TestCase):
    def test_signature_and_compiled_manifest_identity(self):
        path = Path("local caller.apk")
        good = "package: name='local.xuanyuan.mipushcompat' versionCode='17' versionName='1.6'\n"
        for badging, accepted in ((good, True), (good.replace("'17'", "'16'"), False),
                                  (good.replace("mipushcompat", "wrong"), False), ("", False)):
            with self.subTest(badging=badging), patch.object(builder.subprocess, "run") as run:
                run.side_effect = [subprocess.CompletedProcess([], 0, "Verified", ""),
                                   subprocess.CompletedProcess([], 0, badging, "")]
                if accepted:
                    builder.check_apk(path, "local-apksigner", "local-aapt2")
                else:
                    with self.assertRaisesRegex(ValueError, "versionCode 17"):
                        builder.check_apk(path, "local-apksigner", "local-aapt2")
                self.assertEqual(run.call_args_list[0].args[0], ["local-apksigner", "verify", "--verbose", str(path)])
                self.assertEqual(run.call_args_list[1].args[0], ["local-aapt2", "dump", "badging", str(path)])

    def test_invalid_signature_stops_before_manifest(self):
        with patch.object(builder.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "")) as run:
            with self.assertRaisesRegex(ValueError, "apksigner verification failed"):
                builder.check_apk(Path("unsigned.apk"))
            self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
