"""Fail without printing secrets if private files or recognizable tokens enter Git."""
from __future__ import annotations

import re
import subprocess
from pathlib import PurePosixPath

PRIVATE_DIRS = {'.aws', '.ssh', 'data', 'logs', 'artifacts', 'backups', 'exports', 'secrets', 'credentials', 'graphify-out'}
TOKEN_PATTERNS = [
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(rb'\bgh[pousr]_[A-Za-z0-9]{36,255}\b'),
    re.compile(rb'\bgithub_pat_[A-Za-z0-9_]{50,255}\b'),
    re.compile(rb'\bsk-or-v1-[A-Za-z0-9]{32,}\b'),
    re.compile(rb'\bsk-ant-[A-Za-z0-9_-]{32,}\b'),
    re.compile(rb'\bAKIA[A-Z0-9]{16}\b'),
]


def private_path(name: str) -> bool:
    path = PurePosixPath(name)
    if path.name.endswith('.example') or path.name == '.gitkeep':
        return False
    return (bool(PRIVATE_DIRS.intersection(path.parts)) or path.name.startswith('.env')
            or path.name.endswith(('.env', '.har', '.pem', '.key', '.p12', '.pfx', '.db', '.sqlite', '.sqlite3'))
            or path.name in {'.envrc', '.mcp.json', '.netrc', '.pypirc'})


def main() -> int:
    names = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
    issues = []
    checked = 0
    for name in names:
        if not name:
            continue
        checked += 1
        if private_path(name):
            issues.append(f'{name}: private/runtime file must be untracked')
            continue
        # Read the index, not the worktree: an edited local file cannot hide a
        # secret that is still present in the staged version being committed.
        content = subprocess.check_output(['git', 'show', f':{name}'])
        if any(pattern.search(content) for pattern in TOKEN_PATTERNS):
            issues.append(f'{name}: possible secret detected (value withheld)')
    if issues:
        print('\n'.join(issues))
        return 1
    print(f'Public-file check passed: {checked} tracked files; no private paths or recognized secrets.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
