"""Assemble a selected 1.7 suite from resolved, locked local materials; never install."""
import json
from pathlib import Path
import shutil
import tempfile

import build_suite as b

IDS = (*b.COMPONENTS, "clock", "calendar", "mipush")
FEATURE_COMPONENTS = {"phone": "phone", "privacy": "xiaoai", "suggestions": "xiaoai",
                      "warning": "disaster", "clock": "clock"}
PAYLOADS = {**{key: "payload/" + key + ".zip" for key in b.COMPONENTS},
            "clock": "payload/unified.apk", "calendar": "payload/calendar.apk",
            "mipush": "payload/unified.apk"}


def selection(ids):
    """Validate explicit IDs and return dependency closure in controller order."""
    b.require(ids is not None and not isinstance(ids, (str, bytes)), "Provide component IDs, not a CSV string")
    values = list(ids)
    b.require(values and all(isinstance(key, str) and key in IDS for key in values),
              "Select at least one known component ID")
    b.require(len(set(values)) == len(values), "Duplicate component ID")
    chosen = set(values)
    if "xiaoai" in chosen:
        chosen.add("assistant")
    if "phone" in chosen:
        chosen.add("market")
    return tuple(key for key in IDS if key in chosen)


def copy_materials(resolved, component, entries, target):
    for name, item in entries.items():
        origin = resolved
        for part in (component, *name.split("/")):
            origin = origin / part
            b.require(not origin.is_symlink(), "Resolved material symlink: " + component + "/" + name)
        b.require(origin.is_file(), "Missing resolved material: " + component + "/" + name)
        b.require(origin.stat().st_size == item["bytes"], "Material bytes mismatch: " + component + "/" + name)
        destination = target / name
        b.require(not destination.exists(), "Material overlaps template: " + name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with origin.open("rb") as source, destination.open("xb") as output:
            shutil.copyfileobj(source, output, 1024 * 1024)
        b.require(destination.stat().st_size == item["bytes"] and b.digest(destination) == item["sha256"],
                  "Material SHA256 mismatch: " + component + "/" + name)


def trim_catalog(parent, chosen):
    path = parent / "webroot/catalog.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    b.require(isinstance(rows, list) and len(rows) == len(IDS)
              and all(isinstance(row, dict) and isinstance(row.get("id"), str) for row in rows)
              and {row["id"] for row in rows} == set(IDS), "Unexpected 1.7 catalog IDs")
    # Validate identities and dependencies before looking up any payload on disk.
    for row in rows:
        key = row["id"]
        dependencies = ["assistant"] if key == "xiaoai" else ["market"] if key == "phone" else []
        b.require(row.get("file") == PAYLOADS[key] and row.get("dependencies") == dependencies
                  and row.get("kind") == ("module" if key in b.COMPONENTS else "apk"),
                  "Unexpected catalog contract: " + key)
    for key in IDS:
        if key not in chosen:
            b.edit(parent / "catalog.sh", r"^" + key + r"\).*\n", lambda _: "")
    # Unknown lookups must never inherit FILE/SHA/KIND from a previous successful lookup.
    b.edit(parent / "catalog.sh", r"^lookup\(\) \{$",
           lambda m: m[0] + "\nMID='' PKG='' CODE='' FILE='' SHA='' TITLE='' KIND=''")
    selected = [row for row in rows if row["id"] in chosen]
    for row in selected:
        payload = parent / row["file"]
        sha = b.digest(payload)
        row.update(sha256=sha, bytes=payload.stat().st_size)
        b.edit(parent / "catalog.sh", r"^(" + row["id"] + r"\).*?; SHA=')[0-9a-f]{64}(';.*)$",
               lambda m: m[1] + sha + m[2])
    path.write_text(json.dumps(selected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def limit_capabilities(parent, chosen):
    original = " ".join(IDS)
    order = " ".join(chosen)
    features = [key for key, component in FEATURE_COMPONENTS.items() if component in chosen]
    b.edit(parent / "control.sh", r"^ORDER='" + original + r"'$", lambda _: "ORDER='" + order + "'")
    b.edit(parent / "preset.sh", r"^P_ORDER='" + original + r"'$",
           lambda m: m[0] + "\nP_AVAILABLE='" + order + "'")
    # Keep the fixed canonical IDs/features, then reject unavailable dependency closures.
    b.edit(parent / "preset.sh", r'^normalize "\$\{P_PROFILE:--\}" "\$P_ORDER"; P_PROFILE=\$P_NORMAL$',
           lambda m: m[0] + '\nfor P_ID in $(printf \'%s\' "$P_PROFILE" | tr \',\' \' \'); do\n'
           ' case " $P_AVAILABLE " in *" $P_ID "*) ;; *) blocked \'Component not included in this package\';; esac\ndone')
    b.edit(parent / "preset.sh", r"^ORDER=\$P_ORDER$", lambda _: "ORDER=$P_AVAILABLE")
    b.edit(parent / "preset.sh", r"^ for P_ID in \$P_ORDER; do$", lambda _: " for P_ID in $P_AVAILABLE; do")
    # Capabilities are read-only and pass the same exact platform + control-file integrity gates.
    response = ",".join(chosen)
    b.edit(parent / "control.sh", r'^case "\$1" in\n library\)',
           lambda _: 'case "$1" in\n capabilities) [ "$#" = 1 ] || fail \'参数数量错误\'; '
           "platform; integrity; printf '%s\\n' '" + response + "';;\n library)")
    if "xiaoai" not in chosen:
        # Disabled old XiaoAI also needs an explicit paired package before it can be re-enabled.
        b.edit(parent / "customize.sh", r'^if \[ -f "\$X/module.prop" \] && \[ ! -e "\$X/disable" \]; then$',
               lambda _: 'if [ -f "$X/module.prop" ]; then')
        b.edit(parent / "customize.sh", r'^if \[ "\$PAIR_XIAOAI" = true \]; then\n(?s:.*?)^fi$',
               lambda _: 'if [ "$PAIR_XIAOAI" = true ]; then\n'
               " abort '本包未选择小爱，但已安装小爱需要与新统一APK配套更新；请重新勾选小爱构建，未更新APK'\nfi")
    if len(chosen) != len(IDS):
        b.edit(parent / "module.prop", r"^description=.*$",
               lambda _: "description=EEA OS4.0.0.6 专用；本包可用组件：" + ", ".join(chosen)
               + "；共享API102，子组件由用户选择安装，不自动重置钱包。")
    return {"available_ids": list(chosen), "available_features": features}


def install_during_flash(parent, chosen):
    helper = parent / "install-selected.sh"
    b.edit(helper, r"^AUTO_IDS='@SELECTED_IDS@'$", lambda _: "AUTO_IDS='" + ",".join(chosen) + "'")
    # Re-enable inside the existing worker lock, before a manual restore can start.
    b.edit(parent / "control.sh", r'^(  if \[ "\$ID" = wallet \]; then wallet_install; else "\$K" module install .*; fi)$',
           lambda m: m[0] + '\n  if [ "${XLS_FLASH_WORKER:-0}" = 1 ] && [ -e "$MODULES/$MID/disable" ]; then "$K" module enable "$MID"; fi')
    b.edit(parent / "customize.sh", r"^set_perm_recursive ", lambda m:
           'if ! AUTO_PAIRED_XIAOAI="$PAIR_XIAOAI" sh "$MODPATH/install-selected.sh" flash; then\n'
           " ui_print '自动组件部署失败，已停止；父套件保留用于查看日志和逐项恢复，不能视为全部安装成功。'\nfi\n" + m[0])
    b.edit(parent / "customize.sh", r"^ui_print '统一兼容与推送设置已安装；.*$", lambda _:
           "ui_print '已执行电脑所选组件部署计划；核对上方结果，手动重启使挂载生效。'")
    service = parent / "service.sh"
    service.write_text('''#!/system/bin/sh
M=${0%/*}
if [ -f "$M/install-selected.pending" ]; then
 # Only the one explicit flash plan may continue, after a user-initiated boot.
 COUNT=0
 while [ "$(getprop sys.boot_completed)" != 1 ] && [ "$COUNT" -lt 60 ]; do
  sleep 2
  COUNT=$((COUNT + 1))
 done
 sh "$M/install-selected.sh" resume
else
 sh "$M/control.sh" reconcile
fi
''', encoding="utf-8")


def assemble(source_root, resolved_dir, unified_apk, selected_ids, output, apk_checker=b.check_apk):
    """No reference ZIP required. Resolved files live under COMPONENT/LOCK_PATH.

    Returns explicit capabilities for the caller/mobile UI; does not initialize Android
    preferences or claim device qualification. Different signing keys are clean-install only.
    """
    chosen = selection(selected_ids)  # Reject unknown IDs before any filesystem access.
    source, resolved, unified_apk, output = map(Path, (source_root, resolved_dir, unified_apk, output))
    public = source.resolve()
    b.require(not output.resolve().is_relative_to(public), "Output must be outside public source")
    b.require(not output.exists() and not output.is_symlink(), "Refusing to overwrite output")
    b.require(output.suffix.lower() == ".zip", "Output must be a new .zip path")
    b.require(not resolved.is_symlink(), "Resolved directory must not be a symlink")
    resolved = resolved.resolve()
    b.require(resolved.is_dir(), "Missing resolved material directory")
    lock, entries = b.load_lock(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="recipe-assemble-", dir=output.parent) as temporary:
        work = Path(temporary)
        apk = work / "unified.apk"
        shutil.copyfile(unified_apk, apk)
        evidence = unified_apk.with_suffix(".build-evidence.json")
        if evidence.is_file():
            shutil.copyfile(evidence, apk.with_suffix(".build-evidence.json"))
        b.validate_apk_metadata(apk)
        apk_checker(apk)
        parent = work / "parent"
        b.copy_template(source / "suite/module", parent)
        (parent / "payload").mkdir(exist_ok=True)
        shutil.copyfile(apk, parent / "payload/unified.apk")
        if "calendar" in chosen:
            copy_materials(resolved, "parent", {name: item for name, item in entries["parent"].items()
                                               if name != "payload/unified.apk"}, parent)
        # update_identity needs the privacy text even in packages that omit XiaoAI binaries.
        xiaoai = work / "xiaoai"
        b.copy_template(source / "components/xiaoai", xiaoai)
        b.update_identity(parent, xiaoai, lock["original_unified_sha256"], b.digest(apk))
        for component in b.COMPONENTS:
            if component not in chosen:
                continue
            child = xiaoai if component == "xiaoai" else work / component
            if component != "xiaoai":
                b.copy_template(source / "components" / component, child)
            b.require(entries[component], "Missing component material lock: " + component)
            copy_materials(resolved, component, entries[component], child)
            b.checksums(child, "checksums.sha256", b.files(child))
            b.write_zip(child, parent / ("payload/" + component + ".zip"))
            shutil.rmtree(child)
        trim_catalog(parent, chosen)
        capabilities = limit_capabilities(parent, chosen)
        install_during_flash(parent, chosen)
        # The existing WebUI renders only catalog.json rows and checks their dependency closure.
        b.checksums(parent, "control.sha256", [p for p in b.files(parent)
                    if p.relative_to(parent).parts[0] != "payload" and p.name != "customize.sh"])
        b.checksums(parent, "checksums.sha256", b.files(parent))
        archive = work / "suite.zip"
        b.write_zip(parent, archive)
        sha, size = b.digest(archive), archive.stat().st_size
        with output.open("xb") as target:
            try:
                with archive.open("rb") as stream:
                    shutil.copyfileobj(stream, target, 1024 * 1024)
            except BaseException:
                target.close()
                output.unlink()
                raise
    return {"output": str(output.resolve()), "sha256": sha, "bytes": size,
            "selected": list(chosen), "wallet_reset": False,
            **capabilities, "unified_always_included": True, "clean_install_only": True,
            "device_tested": False, "auto_install_components": True,
            "install_policy": "during-flash-with-phone-continuation",
            "wallet_first_migration": "phone-confirmation-only"}
