# W-01 · AI Dev Environment

The baseline setup for AI development. Install these, in this order, and you can do everything else in the handbook.

## Forces
- Installing AI tools in the wrong order wastes an afternoon (CUDA before drivers, Python version conflicts)
- Too many tools = configuration tax; too few = blocked on basics
- The environment should let you switch models, run local inference, and observe token costs

## The move

**In order:**

### 1. Python 3.11+
Most AI libraries drop support for older versions quickly.
```bash
# Check version
python --version  # need 3.11+

# macOS/Linux via pyenv (recommended)
pyenv install 3.12.3
pyenv global 3.12.3
```

### 2. The core SDKs
```bash
pip install anthropic openai       # model APIs
pip install ollama                  # local model client
pip install chromadb               # local vector store
pip install python-dotenv          # .env file loading
```

### 3. Ollama (local inference)
Download from [ollama.com](https://ollama.com) and run:
```bash
ollama serve          # start the server (port 11434)
ollama pull llama3.2  # pull a model
ollama list           # verify it's there
```

### 4. Claude Code (AI-native CLI)
```bash
npm install -g @anthropic-ai/claude-code
claude --version
```
See [W-02](w02-claude-code.md) for setup.

### 5. API keys in `.env`
```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```
Load in code:
```python
from dotenv import load_dotenv
load_dotenv()
```
Never commit `.env`. Add it to `.gitignore` before your first commit.

## Receipt
> Verified 2026-06-25 — ollama serve + ollama pull llama3.2 confirmed working on Windows 11 (WSL2). Claude Code install confirmed (this session runs it).

## See also
[W-02](w02-claude-code.md) · [W-03](w03-local-models-ollama.md) · [S-01](../stacks/s01-local-model-dispatch.md)

## Go deeper
Keywords: `pyenv` · `conda` · `uv` · `poetry` · `dotenv` · `CUDA setup` · `WSL2`
