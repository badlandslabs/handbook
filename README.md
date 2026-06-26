# The AI Agent Handbook

Practical, receipted patterns for building AI agents. No guesswork.

Every entry is a standalone atom: situation, forces, the move, a real receipt. You can read it in two minutes and apply it the same day — whether you've never touched AI or you're architecting multi-agent systems at scale.

---

## How to read this

- **Start anywhere.** Entries are numbered and cross-linked. Jump to what you need.
- **Trust the receipts.** Every technique ships with a real run log — actual output, actual errors. If there is no receipt, the entry says so.
- **Talk to it.** [Ask Claude Code to navigate this handbook for you.](#talk-to-the-handbook)
- **Contribute.** See something wrong, missing, or stale? [Fork and submit a PR.](CONTRIBUTING.md)

---

## Structure

| Book | What it covers |
|---|---|
| [The Laws](laws.md) | The fixed worldview everything hangs from |
| [Book of Stacks](stacks/) | Agent architectures, patterns, and the code that builds them |
| [Book of the Workspace](workspace/) | Tooling, environment, the AI dev setup |
| [Book of the Forward-Deployed Engineer](forward-deployed/) | Shipping AI to real users, evaluating at scale |
| [Book of the Frontier](frontier/) | Research, model landscape, open questions |

---

## Talk to the handbook

If you have Claude Code, run `/handbook` in your terminal to query entries by topic.

Or just ask any capable LLM:

```
You are navigating The AI Agent Handbook at https://github.com/stancsz/handbook.
The handbook is organized into: Laws, Book of Stacks, Book of the Workspace,
Book of the Forward-Deployed Engineer, and Book of the Frontier.
Each entry follows: Name / Situation / Forces / The move / Receipt / See also.
Help me find entries relevant to: [your question]
```

---

## Contribute

Fork → write an entry or fix one → submit a PR. See [CONTRIBUTING.md](CONTRIBUTING.md).

The only rule: if you can't back it with a real receipt, mark it `Receipt pending`.
