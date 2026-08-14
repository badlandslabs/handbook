#!/usr/bin/env python3
"""Push S-2605 chapter and updated tracker to GitHub."""
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
        'content': base64.b64encode(content.encode()).decode(),
        'branch': BRANCH,
    }
    if sha:
        data['sha'] = sha
    url = f'https://api.github.com/repos/{REPO}/contents/{path}'
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method='PUT')
    try:
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read())
        print(f'Pushed {path}: {result["commit"]["sha"][:8]}')
        return result['commit']['sha']
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f'Error pushing {path}: {e.code} {body}')
        raise

# Push the chapter
chapter_path = 'stacks/s2605-the-tool-description-engineering-stack-when-your-system-prompt-is-not-where-your-tool-selection-decisions-get-made.md'
with open(chapter_path) as f:
    chapter_content = f.read()
sha = get_sha(chapter_path)
push_file(chapter_path, chapter_content, sha, 'Add S-2605 · The Tool Description Engineering Stack — When Your System Prompt Is Not Where Your Tool-Selection Decisions Get Made')

# Push the tracker
tracker_path = 'knowledge-pulse.md'
with open(tracker_path) as f:
    tracker_content = f.read()
sha = get_sha(tracker_path)
push_file(tracker_path, tracker_content, sha, 'Update knowledge-pulse.md: add I-3297, S-2605 Tool Description Engineering')

print('Done.')
