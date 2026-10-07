#!/usr/bin/env python3
"""Verify this typography change preserves template semantics against its baseline.

Only typography CSS declarations are normalized. No backend is imported.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline', default='899affd')
parser.add_argument('--output', type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]


def semantics(text):
    text = re.sub(r'(?:font-(?:family|weight|size)|letter-spacing)\s*:[^;{}]+;', '', text)
    return '\n'.join(line.rstrip() for line in text.splitlines())


results = []
for path in sorted((root / 'web/templates').glob('*.html')):
    relative = str(path.relative_to(root))
    before = subprocess.check_output(['git', 'show', f'{args.baseline}:{relative}'], cwd=root, text=True)
    after = path.read_text()
    results.append({'file': relative, 'status': 'PASS' if semantics(before) == semantics(after) else 'FAIL',
                    'check': 'DOM, wording, logic, URLs and non-typography declarations unchanged'})
relative = 'web/static/js/timeout.js'
before = subprocess.check_output(['git', 'show', f'{args.baseline}:{relative}'], cwd=root, text=True)
results.append({'file': relative, 'status': 'PASS' if semantics(before) == semantics((root / relative).read_text()) else 'FAIL',
                'check': 'timeout logic and wording unchanged'})
print(json.dumps(results, ensure_ascii=False, indent=2))
if args.output:
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
raise SystemExit(any(r['status'] != 'PASS' for r in results))
