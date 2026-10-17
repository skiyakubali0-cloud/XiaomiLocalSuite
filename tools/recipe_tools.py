"""Explicitly prepare the pinned warning-DEX build tools; never fetch on import/check."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def prepare(local_dir=None, *, download=False, root=ROOT):
    if (local_dir is None) != bool(download):
        raise ValueError('请选择离线依赖目录或显式 --download，不能自动下载')
    root = Path(root)
    build, destination = root / 'build', root / 'build/recipe-tools'
    if build.is_symlink() or destination.is_symlink():
        raise ValueError('依赖目录不能是符号链接')
    dependencies = json.loads((root / 'recipes/generated.json').read_text(encoding='utf-8'))['tools']
    verified = []
    for item in dependencies:
        name, size = item['file'], item['bytes']
        url = urllib.parse.urlparse(item['url'])
        if not re.fullmatch(r'[A-Za-z0-9_.-]+\.jar', name) or not 0 < size < 16 * 1024**2:
            raise ValueError('依赖文件名或大小无效')
        if url.scheme != 'https' or url.hostname not in ('dl.google.com', 'repo.maven.apache.org') or url.query:
            raise ValueError('依赖来源不在公开配方中')
        path = destination / name
        if path.is_symlink():
            raise ValueError('缓存依赖不能是符号链接')
        if local_dir is not None:
            with (Path(local_dir) / name).open('rb') as stream:
                raw = stream.read(size + 1)
        else:
            with urllib.request.urlopen(item['url'], timeout=60) as response:
                raw = response.read(size + 1)
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('依赖校验失败：' + name)
        if path.exists() and path.read_bytes() != raw:
            raise ValueError('保留不匹配的旧缓存，不自动覆盖：' + name)
        verified.append((path, raw))
    destination.mkdir(parents=True, exist_ok=True)
    for path, raw in verified:
        if not path.exists():
            with path.open('xb') as stream:
                stream.write(raw)
    return len(verified)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--local-dir', type=Path)
    mode.add_argument('--download', action='store_true')
    args = parser.parse_args()
    try:
        count = prepare(args.local_dir, download=args.download)
        print('已校验 {} 份依赖，仅保存在本机 build/recipe-tools。'.format(count))
    except (OSError, ValueError) as error:
        parser.exit(1, '准备依赖失败：' + str(error) + '\n')


if __name__ == '__main__':
    main()
