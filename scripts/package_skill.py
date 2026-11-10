#!/usr/bin/env python3
"""Build a clean, installable copy of the Flight Atlas skill.

The repository also holds a README and a docs/ gallery (about 2 MB of example
reports) that are for people browsing GitHub, not for the assistant. This script
copies only what the skill needs: SKILL.md, LICENSE, agents/, assets/, references/
and scripts/ (without caches).

  python3 scripts/package_skill.py                      # dist/flight-atlas/ and dist/flight-atlas.zip
  python3 scripts/package_skill.py --dest ~/.claude/skills   # install for Claude Code (all projects)
  python3 scripts/package_skill.py --dest .claude/skills     # install for one project

Stdlib only. Never stores personal travel data: run it from a clean checkout.
"""
import argparse
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = 'flight-atlas'
INCLUDE = ('SKILL.md', 'LICENSE', 'agents', 'assets', 'references', 'scripts')
SKIP_PARTS = {'__pycache__', '.DS_Store'}
SKIP_SUFFIXES = {'.pyc', '.pyo'}


def skill_files(root=ROOT):
    """Relative paths of every file that belongs in the installed skill."""
    files = []
    for entry in INCLUDE:
        path = root / entry
        if not path.exists():
            raise SystemExit(f'Missing {entry} in {root}; run this from a Flight Atlas checkout')
        candidates = [path] if path.is_file() else sorted(p for p in path.rglob('*') if p.is_file())
        for file in candidates:
            rel = file.relative_to(root)
            if SKIP_PARTS.intersection(rel.parts) or file.suffix in SKIP_SUFFIXES:
                continue
            files.append(rel)
    return files


def copy_to(target, files, force=False):
    if target.exists():
        if not force:
            raise SystemExit(f'{target} already exists; remove it or pass --force to replace it')
        shutil.rmtree(target)
    for rel in files:
        out = target / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, out)
    return target


def write_zip(path, files):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for rel in files:
            archive.write(ROOT / rel, f'{NAME}/{rel.as_posix()}')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dest', type=Path, help=f'skills directory to install into (creates DEST/{NAME})')
    parser.add_argument('--out', type=Path, default=ROOT / 'dist', help='where to write the folder and zip when --dest is not given')
    parser.add_argument('--force', action='store_true', help='replace an existing installed copy')
    args = parser.parse_args()
    files = skill_files()
    size = sum((ROOT / f).stat().st_size for f in files)
    if args.dest:
        target = copy_to(args.dest.expanduser() / NAME, files, args.force)
        print(f'Installed {len(files)} files ({size / 1e6:.1f} MB) to {target}')
        return
    folder = copy_to(args.out / NAME, files, force=True)
    archive = write_zip(args.out / f'{NAME}.zip', files)
    print(f'{len(files)} files ({size / 1e6:.1f} MB): {folder}')
    print(f'Upload this zip to Claude: {archive} ({archive.stat().st_size / 1e6:.1f} MB)')


if __name__ == '__main__':
    sys.exit(main())
