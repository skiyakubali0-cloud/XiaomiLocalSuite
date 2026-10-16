#!/usr/bin/env python3
"""Run the public host checks without a phone, accounts or OEM inputs."""
from pathlib import Path
import os
import hashlib
import json
import zipfile
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sdk=os.environ.get('ANDROID_SDK_ROOT') or os.environ.get('ANDROID_HOME')
if not sdk:raise SystemExit('Set ANDROID_SDK_ROOT or ANDROID_HOME before running tests')
os.environ['ANDROID_SDK_ROOT']=sdk
os.environ.setdefault('ANDROID_JAR',str(Path(sdk)/'platforms/android-36/android.jar'))
project=ROOT/'suite/unified-api102'
# Legacy host harnesses expect deps/*.jar. These derived files are Git-ignored.
for entry in json.loads((project/'deps.lock.json').read_text()):
    archive=project/'build/deps'/entry['file']
    if not archive.is_file():raise SystemExit('Prepare pinned dependencies with fetch_dependencies.py --download or --local-dir')
    raw=archive.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise SystemExit('Dependency checksum mismatch')
    (project/'deps').mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        (project/'deps'/(entry['file'].split('-')[0]+'.jar')).write_bytes(z.read('classes.jar'))
commands=[
 [sys.executable,'tools/check_public_tree.py'],
 [sys.executable,'-B','-m','unittest','discover','-s','tools','-p','test_*.py','-v'],
 [sys.executable,'-B','-m','unittest','discover','-s','suite/multi-device','-p','test_*.py','-v'],
 [sys.executable,'-B','-m','unittest','discover','-s','suite/wallet-release','-p','test_wallet.py','-v'],
 [sys.executable,'-B','-m','unittest','discover','-s','suite/unified-api102/tests','-p','test_*.py','-v'],
 [sys.executable,'-B','suite/unified-api102/tests/phone-clock-suggestion/run_tests.py'],
 [sys.executable,'-B','suite/unified-api102/tests/privacy-warning/run.py'],
]
for command in commands:
 print('+ '+' '.join(command),flush=True)
 subprocess.run(command,cwd=ROOT,check=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
print('Public host checks passed. No device behavior is implied.')
