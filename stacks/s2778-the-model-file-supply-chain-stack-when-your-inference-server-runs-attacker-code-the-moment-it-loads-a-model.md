# S-2778 · The Model File Supply Chain Stack — When Your Inference Server Runs Attacker Code the Moment It Loads a Model

You downloaded a reranking model from Hugging Face. It's well-scored, recent, and popular. Your SGLang server processes it. Three seconds later, an attacker has RCE on your GPU node. No credentials touched. No malicious endpoint hit. The weapon was a model file.

This is not a hypothetical. CVE-2026-5760 (CVSS 9.8) made it real: a crafted GGUF file triggers unsandboxed Jinja2 template rendering on SGLang's `/v1/rerank` endpoint, achieving unauthenticated remote code execution on the inference server. The attacker doesn't need your API. They need your trust in a model file.

## Forces

- **The model file is now an attack surface.** GGUF files carry more than weights — they carry chat templates, metadata, and tokenizer configurations that get rendered server-side. SGLang uses `jinja2.Environment()` to process model-supplied chat templates. If a model file ships with a malicious Jinja2 payload embedded in its template metadata, that payload executes when the server processes any request through that template. This is Server-Side Template Injection (SSTI) with no user interaction required.
- **The supply chain model is "trust but verify" for weights, not metadata.** Teams vet model architectures, check for backdoored weights (via rare token probes), and verify quantization integrity. Nobody inspects the `chat_template` field in a GGUF's metadata — it doesn't occur to them that a template could be a weapon. The metadata is trusted as configuration, not content.
- **Inference servers execute at high privilege.** Unlike an agent's sandboxed tool call, an inference server runs as a system process with GPU access, network connectivity, and often cloud credentials. RCE on an inference node is tenant isolation failure, data exfiltration, and lateral movement rolled into one. The attacker's code runs on the same hardware as your model weights.
- **The GGUF ecosystem has no integrity contract for metadata.** Unlike software package managers that enforce signing (npm, PyPI, Cargo), model repositories (Hugging Face, Civitai, private registries) treat model files as opaque blobs. The GGUF spec (designed for portability) has no mechanism to authenticate or isolate template metadata. A file can be bit-for-bit identical to a legitimate model and carry a different payload in its metadata.
- **Patch availability is lagging disclosure.** CVE-2026-5760 had no official vendor patch at publication. Three additional critical CVEs (CVSS 9.8–7.8) landed in SGLang within months of each other, indicating systemic security debt in widely deployed serving frameworks. Organizations cannot rely on upstream patches alone.

## The Move

**Threat model your inference layer as an attack surface, not just infrastructure.**

Treat every model file as untrusted code at the metadata layer. Implement these controls in depth:

**At the serving layer:**
- Disable dynamic chat template rendering in production serving configs. Use server-defined templates, not model-supplied ones.
- If chat templates are required, sandbox Jinja2 rendering: process templates in a strict `SandboxedEnvironment` (jinja2-sandbox), or replace with a vetted T5-style template system that has no access to Python builtins or os-level calls.
- Restrict the `/v1/rerank` endpoint to authenticated callers and network-level isolation (VPC peering, firewall rules). Even if the template vulnerability is fixed, the endpoint was the exploitation path.
- Pin SGLang (and other serving frameworks) to specific versions. Track CVE feeds for your serving stack: SGLang, vLLM, LMDeploy, and text-generation-inference all process model files that carry metadata.

**At the model registry layer:**
- Implement a model import pipeline that scans GGUF metadata before deployment: extract and lint the `chat_template` field, `tokenizer_config.json`, and any embedded Jinja2 content for suspicious patterns (`{{`, `{%`, `os.`, `__import__`, `subprocess`).
- Introduce a model provenance standard: sign model metadata at upload time (HF signed commits, Sigstore), verify signatures at import time. This closes the gap between weight integrity and metadata integrity.
- Maintain an allowlist of approved chat templates per model family. Treat template deviations as a supply chain alert.

**At the infrastructure layer:**
- Run inference workloads in hardened network namespaces: inference nodes should have no outbound internet access (except to approved model registries), no cloud credential attachment, and strict IAM perimeters. Assume compromise — limit blast radius.
- Enable seccomp/AppArmor/SELinux profiles on inference containers that block `execve` syscalls from Jinja2 rendering processes.
- Monitor for unexpected outbound connections from inference nodes, unexpected file writes in model directories, or anomalous process spawning patterns.

```python
# Minimal GGUF metadata scanner — run before deploying any model file
import gguf
import re

SUSPICIOUS_PATTERNS = [
    r"\{\{.*\}\}",          # Jinja2 interpolation
    r"\{%.*%\}",             # Jinja2 tag
    r"__import__",          # Python dynamic import
    r"os\.",                 # os module access
    r"subprocess",           # subprocess spawning
    r"exec\s*\(",            # eval/exec
    r"eval\s*\(",
]

def scan_gguf_metadata(path: str) -> list[str]:
    """Scan GGUF file metadata for SSTI payloads before deployment."""
    reader = gguf.GGUFReader(path)
    alerts = []
    for key in reader.fields:
        raw = str(reader.fields[key].parts)
        for pattern in SUSPICIOUS_PATTERNS:
            if re.search(pattern, raw):
                alerts.append(f"SUSPICIOUS [{pattern}] in field: {key}")
    return alerts

# Example usage
alerts = scan_gguf_metadata("/models/candidate-reranker.gguf")
if alerts:
    print("MODEL REJECTED — metadata scan failed:")
    for a in alerts:
        print(f"  {a}")
    exit(1)
print("Model metadata scan: CLEAN")
```

## Receipt

> Verified 2026-08-17 — CVE-2026-5760 (CSA AI Safety Initiative, April 2026, CVSS 9.8) confirmed: SGLang uses `jinja2.Environment()` for chat template rendering without sandboxing. Attack path: attacker uploads trojanized GGUF to Hugging Face → victim downloads and deploys on `/v1/rerank` → Jinja2 SSTI payload executes `os.popen()` or equivalent on the inference server. No authentication required. Active exploitation confirmed in the wild (CSA). Three additional critical SGLang CVEs (CVSS 9.8, 9.8, 7.8) disclosed in the same period. The GGUF format's metadata field is the attack surface — not the model weights themselves. Mitigation: disable model-supplied templates, sandbox Jinja2, sign/model-provenance, harden inference node network policy.

## See also

- [S-902 · The Scaffold Supply Chain Stack](/opt/data/handbook/stacks/s902-the-scaffold-supply-chain-stack-when-your-agent-builds-a-backdoor-into-your-own-infra.md) — agent scaffold supply chain attacks (skill/registry poisoning)
- [S-1412 · The OWASP MCP Top 10 Stack](/opt/data/handbook/stacks/s1412-the-owasp-mcp-top-10-stack-when-your-agent-framework-has-ten-critical-risks-nobody-is-tracking.md) — MCP supply chain threats (different protocol, same attack surface thinking)
- [S-2760 · The MCP Server Hijack Stack](/opt/data/handbook/stacks/s2760-the-mcp-server-hijack-stack-when-your-tool-server-becomes-your-attackers-pivot-point.md) — tool server compromise in the agent stack
- [S-1902 · The Disaggregated Inference Stack](/opt/data/handbook/stacks/s1902-the-disaggregated-inference-stack-when-your-agent-queue-stalls-because-one-prompt-poisoned-the-batch.md) — inference serving architecture (same layer, different risk)
