#!/usr/bin/env python3
import re

with open('knowledge-pulse.md') as f:
    content = f.read()

lines = content.split('\n')

# Find non-WRITTEN I-32xx entries
for i, line in enumerate(lines):
    line = line.rstrip()
    if not line.startswith('|'):
        continue
    cols = [c.strip() for c in line.split('|') if c.strip()]
    if len(cols) >= 2 and cols[0].startswith('I-32') and not cols[0].startswith('I-320'):
        # Find status
        status = None
        composite = None
        for c in cols:
            if c.startswith('WRITTEN') or c.startswith('DUPLICATE') or c.startswith('DEFERRED') or c.startswith('CANDIDATE') or c.startswith('RESEARCH') or c.startswith('DORMANT'):
                status = c
            if c.startswith('**') and '/' in c:
                composite = c
        if status and 'WRITTEN' not in status:
            title = cols[2] if len(cols) > 2 else 'N/A'
            print(f"L{i+1}: {cols[0]} | {title[:70]} | {status} | {composite}")
