#!/usr/bin/env python3
"""Scan the publication set, without printing possible secret values."""
import argparse
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BANNED_SUFFIXES = {'.apk','.aab','.aar','.jar','.class','.dex','.so','.elf','.zip','.tgz','.tar','.gz','.img','.bin','.jks','.keystore','.pem','.key','.p12','.pfx','.db','.sqlite','.sqlite3','.log','.png','.jpg','.jpeg','.webp'}
BANNED_PARTS = {'private','.local-private','__pycache__','deps','build','materials','releases','verification'}
PATTERNS = {
    'private-key': re.compile(r'-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----'),
    'github-credential': re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})'),
    'aws-access-key': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'jwt': re.compile(r'\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\b'),
    'personal-absolute-path': re.compile(r'/(?:Us' r'ers|Volu' r'mes)/[^/\s\x27\x22]+/'),
    'personal-email': re.compile(r'(?<![\w.-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])'),
    'device-serial': re.compile(r'(?:adb\s+(?:[^\n]*?\s)?-s\s+|SERIAL\s*=\s*[\x27\x22])([A-Za-z0-9]{6,})'),
    'private-network-ip': re.compile(r'(?<![\w.])(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(?![\w.])'),
    'assigned-secret-literal': re.compile(r'(?i)(?:access_token|refresh_token|client_secret|authorization)\s*[=:]\s*[\x27\x22]([A-Za-z0-9_./+=-]{24,})[\x27\x22]'),
}
# Standard license contact addresses and deliberately synthetic documentation only.
ALLOWED_EMAIL_DOMAINS = {'apache.org','example.com','example.org','example.invalid','users.noreply.github.com'}

def check(name, raw):
    p=Path(name);findings=[]
    if p.is_absolute() or '..' in p.parts or any(x in BANNED_PARTS or x.startswith('._') or x=='.DS_Store' for x in p.parts) or p.suffix.lower() in BANNED_SUFFIXES:
        findings.append((name,0,'forbidden-file'))
    if len(raw)>1024*1024:findings.append((name,0,'oversized-file'))
    try:text=raw.decode('utf-8')
    except UnicodeDecodeError:return findings+[(name,0,'binary-file')]
    if '\x00' in text:return findings+[(name,0,'binary-file')]
    for label,pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            if label=='personal-email' and match[0].rsplit('@',1)[1].lower() in ALLOWED_EMAIL_DOMAINS:continue
            findings.append((name,text.count('\n',0,match.start())+1,label))
    return findings

def files(staged=False):
    args=['git','diff','--cached','--name-only','--diff-filter=ACMR','-z'] if staged else ['git','ls-files','--cached','--others','--exclude-standard','-z']
    result=subprocess.run(args,cwd=ROOT,check=True,capture_output=True)
    return sorted(set(n.decode() for n in result.stdout.split(b'\0') if n))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--staged',action='store_true');a=p.parse_args();findings=[];names=files(a.staged)
    if not names:raise SystemExit('No files to scan')
    for name in names:
        target=ROOT/name
        if target.is_symlink():findings.append((name,0,'symlink'));continue
        raw=subprocess.run(['git','show',':'+name],cwd=ROOT,check=True,capture_output=True).stdout if a.staged else target.read_bytes()
        findings.extend(check(name,raw))
    for name,line,kind in findings:print(f'{name}:{line}: {kind}')
    print(f'Checked {len(names)} files; {len(findings)} findings. Values are never printed.')
    return bool(findings)
if __name__=='__main__':sys.exit(main())
