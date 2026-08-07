#!/usr/bin/env python3
"""Push S-2270 chapter to GitHub via REST API."""
import urllib.request
import urllib.error
import base64
import json
import os

# Read token from environment
token = os.environ.get('GH_PAT', '')
if not token:
    # Fallback to netrc
    netrc_path = os.path.expanduser('~/.netrc')
    with open(netrc_path, 'r') as f:
        for line in f:
            if 'password' in line.lower():
                token = line.strip().split()[-1]
                break

if not token:
    print("ERROR: No token found")
    exit(1)

print(f"Token found: {token[:8]}...{token[-4:]}")

REPO = 'badlandslabs/handbook'
BRANCH = 'main'

headers = {
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
}

# Read the file to push
filepath = '/opt/data/handbook/stacks/s2270-the-entropy-stack-when-your-agent-becomes-less-reliable-the-longer-it-runs.md'
with open(filepath, 'rb') as f:
    content = f.read()

remote_path = 'stacks/s2270-the-entropy-stack-when-your-agent-becomes-less-reliable-the-longer-it-runs.md'
message = 'Add S-2270 · The Entropy Stack — When Your Agent Becomes Less Reliable the Longer It Runs'

# Get SHA of existing file (if any)
url = f'https://api.github.com/repos/{REPO}/contents/{remote_path}?ref={BRANCH}'
req = urllib.request.Request(url, headers=headers)
sha = None
try:
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read())
    sha = data['sha']
    print(f"Existing SHA: {sha}")
except urllib.error.HTTPError as e:
    if e.code == 404:
        sha = None
        print("File does not exist on remote, creating new")
    else:
        body = e.read()
        print(f"HTTP Error getting SHA: {e.code} {body.decode()}")
        raise

# Push
payload = {
    'message': message,
    'content': base64.b64encode(content).decode('ascii'),
}
if sha:
    payload['sha'] = sha

url = f'https://api.github.com/repos/{REPO}/contents/{remote_path}'
data = json.dumps(payload).encode()
req = urllib.request.Request(url, data=data, headers=headers, method='PUT')
try:
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    commit = result.get('commit', {})
    print(f"SUCCESS: {commit.get('html_url', result.get('content', {}).get('html_url', 'no URL'))}")
    print(f"Commit SHA: {commit.get('sha', 'unknown')}")
except urllib.error.HTTPError as e:
    body = e.read()
    print(f"FAILED: {e.code} {body.decode()}")
    exit(1)
