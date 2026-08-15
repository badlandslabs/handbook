#!/usr/bin/env python3
"""Push S-2640 chapter and updated tracker to GitHub."""
import urllib.request
import urllib.error
import base64
import json
import os

TOKEN=os.environ.get('GH_PAT', '') or os.environ.get('GITHUB_TOKEN', '')
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
        'content': base64.b64encode(content.encode()).decode(),
        'branch': BRANCH,
    }
    if sha:
        data['sha'] = sha
    body = json.dumps(data).encode()
    url = f'https://api.github.com/repos/{REPO}/contents/{path}'
    req = urllib.request.Request(url, data=body, headers=headers, method='PUT')
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())

# Chapter content
chapter_path = 'stacks/s2640-the-production-eval-gap-stack-when-your-agent-passes-every-benchmark-and-fails-every-tuesday.md'
chapter_content = open(chapter_path).read()

# Tracker content  
tracker_path = 'knowledge-pulse.md'
tracker_content = open(tracker_path).read()

# Push chapter
print(f"Pushing {chapter_path}...")
chapter_sha = get_sha(chapter_path)
result = push_file(chapter_path, chapter_content, chapter_sha,
    f'Add S-2640 · The Production Eval Gap Stack — When Your Agent Passes Every Benchmark and Fails Every Tuesday')
print(f"  SHA: {result.get('commit', {}).get('sha', 'N/A')}")

# Push tracker
print(f"Pushing {tracker_path}...")
tracker_sha = get_sha(tracker_path)
result = push_file(tracker_path, tracker_content, tracker_sha,
    f'Update knowledge-pulse.md — I-3309 → S-2640 · The Production Eval Gap Stack')
print(f"  SHA: {result.get('commit', {}).get('sha', 'N/A')}")

print("Done.")
