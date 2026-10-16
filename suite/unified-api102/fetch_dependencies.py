"""Fetch pinned AARs into ignored build/deps using only the Python standard library."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent


def load_lock():
    return json.loads((ROOT / "deps.lock.json").read_text(encoding="utf-8"))


def verify(data, dependency):
    if hashlib.sha256(data).hexdigest() != dependency["sha256"]:
        raise ValueError("Dependency checksum mismatch: " + dependency["file"])


def ignored_build(root):
    build = root / "build"
    if build.is_symlink():
        raise ValueError("build/ must be a local directory, not a symlink")
    build.mkdir(exist_ok=True)
    ignore = build / ".gitignore"
    if not ignore.exists():
        with ignore.open("x", encoding="utf-8") as stream:
            stream.write("# Generated files, dependencies and private signing material.\n*\n")
    return build


def fetch(local_dir=None):
    dependencies = load_lock()
    # Verify all inputs before creating the cache; never trust caller-supplied JARs.
    contents = []
    for dependency in dependencies:
        name = dependency["file"]
        if local_dir is not None:
            data = (local_dir / name).read_bytes()
        else:
            with urllib.request.urlopen(dependency["url"], timeout=60) as response:
                data = response.read()
        verify(data, dependency)
        contents.append((name, data))
    destination = ignored_build(ROOT) / "deps"
    destination.mkdir(exist_ok=True)
    for name, data in contents:
        path = destination / name
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError("Refusing to replace cached dependency: " + name)
        else:
            with path.open("xb") as stream:
                stream.write(data)
    print("Verified dependencies in build/deps/")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--local-dir", type=Path, help="Read the three pinned AARs from this directory (offline)")
    source.add_argument("--download", action="store_true", help="Download the exact Maven Central URLs in deps.lock.json")
    args = parser.parse_args()
    try:
        fetch(args.local_dir)
    except (OSError, ValueError):
        # Network and filesystem errors may include local paths; keep diagnostics generic.
        parser.exit(1, "Dependency fetch failed; check inputs, connectivity and locked SHA-256 values.\n")


if __name__ == "__main__":
    main()
