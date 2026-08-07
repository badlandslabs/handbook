#!/usr/bin/env python3
"""Push S-2234 chapter and updated tracker to GitHub."""
import urllib.request
import urllib.error
import base64
import json
import os

TOKEN = os.environ.get('GH_PAT', '') or os.environ.get('GITHUB_TOKEN', '')
REPO = 'badlandslabs/handbook'
BRANCH = 'main'

headers = {
    'Authorization': f'token {TOKEN}',
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'Content-Type': 'application/json',
}

def get_sha(path):
    url = f'https://api.github.com/repos/{REPO}/contents/{path}?ref={BRANCH}'
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read())
        return data['sha']
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

def push_file(path, content, sha=None, message=None):
    data = {
        'message': message or f'Update {path}',
        'content': base64.b64encode(content).decode(),
        'branch': BRANCH,
    }
    if sha:
        data['sha'] = sha
    body = json.dumps(data).encode()

    url = f'https://api.github.com/repos/{REPO}/contents/{path}'
    req = urllib.request.Request(url, headers=headers, data=body)
    req.get_method = lambda: 'PUT'
    try:
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read())
        print(f'OK {path} -> {result["commit"]["sha"][:8]}')
        return True
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        print(f'FAIL {path} -> HTTP {e.code}: {body_text[:300]}')
        return False

os.chdir('/opt/data/handbook')

files = [
    ('stacks/s2234-the-agent-governance-readiness-stack-when-your-pilot-wins-but-production-fails.md',
     'S-2234: The Agent Governance Readiness Stack — pilot wins, production fails'),
    ('knowledge-pulse.md',
     'Update knowledge-pulse.md: I-3177 Agent Governance Readiness, I-3176 last'),
]

for rel_path, commit_msg in files:
    if not os.path.exists(rel_path):
        print(f'SKIP {rel_path} — not found')
        continue
    with open(rel_path, 'rb') as f:
        content = f.read()
    sha = get_sha(rel_path)
    if sha:
        print(f'  {rel_path}: sha={sha[:8]}')
    else:
        print(f'  {rel_path}: new file')
    push_file(rel_path, content, sha=sha, message=commit_msg)

print('Done.')
