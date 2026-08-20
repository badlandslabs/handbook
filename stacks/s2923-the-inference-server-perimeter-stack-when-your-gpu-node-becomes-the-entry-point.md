# S-2923 · The Inference Server Perimeter Stack

Your agent is only as secure as the process serving the model. You've hardened your prompt injection layer, locked down your MCP servers, and sealed your tool definitions. Then a user uploads an image and your inference server SSRF-probes your cloud metadata endpoint from inside your VPC — in 12 hours flat. The LLM serving stack is an attack surface in its own right, with its own CVE taxonomy, and it is not protected by your application security.

## Forces

- **Inference servers deserialize attacker-controlled data at runtime**: model files, image URLs, request tensors — all arrive from outside the trust boundary and are processed with elevated privileges on GPU nodes that often have cloud metadata access
- **The CVE-to-exploit window has collapsed to hours**: LMDeploy CVE-2026-33626 was publicly weaponized in ~12 hours; your patching cycle is measured in days or weeks
- **Traditional security tooling misses serving-layer attacks**: there are no malware signatures for a malicious GGUF file or a poisoned image URL, and the attack surface spans deserialization, SSRF, path traversal, and IPC exposure across vLLM, SGLang, lmdeploy, Triton, Ollama, and BentoML
- **The perimeter is implicit, not hardened by default**: inference servers bind to routable ports, expose admin/metrics endpoints, and use local IPC channels that default to "localhost" but are routinely misconfigured in containerized deployments

## The Move

### 1. Know the CVE taxonomy

The LLM serving vulnerability landscape clusters into six recurring classes:

| Class | Description | Critical Example |
|-------|-------------|-----------------|
| **Deserialization RCE** | Unsafe `pickle.load()` / `torch.load()` on attacker-supplied data | vLLM CVE-2025-62164, lmdeploy CVE-2025-67729 |
| **SSRF** | Server fetches attacker-controlled URLs without validation | LMDeploy CVE-2026-33626 (CVSS 7.5) |
| **Dynamic Code Execution** | Model files carry templates/scripts executed server-side | SGLang CVE-2026-5760 (CVSS 9.8) via Jinja2 in GGUF |
| **IPC Exposure** | Inter-process channels bind to routable interfaces | ZeroMQ misconfiguration across frameworks |
| **Path Traversal** | Attacker-controlled file paths in model loading | Multiple CVEs across vLLM, BentoML |
| **Auth Bypass** | Admin/metrics endpoints unauthenticated by default | Framework-specific CVEs |

The most dangerous is deserialization RCE: frameworks load tensors and model files that an attacker can influence, and `torch.load()` uses Python pickle under the hood. This is not a niche vector — it is how the frameworks are designed to work.

### 2. Hardening checklist before going to production

**Network surface (baseline — every framework)**
```
- Serving API is behind an authenticated gateway, not public internet
- Admin, metrics, and model-management endpoints are not publicly reachable
- IPC channels bind to localhost or Unix sockets, never a routable interface
- Inter-process ZeroMQ channels use authentication + encryption if exposed
```

**Model loading**
```bash
# CRITICAL: Disable trust_remote_code for any model you didn't train
# This executes arbitrary Python in the model directory
trust_remote_code = false  # Default and required for untrusted sources

# For Hugging Face: use safetensors (prevents arbitrary pickle execution)
# safetensors format is guaranteed to not execute code
```

**Vision and image processing**
```python
# Vulnerable: LMDeploy load_image() fetches URLs without validation
# Fix: proxy through a validated image service or disable remote URLs
# CVE-2026-33626 exploited this path within 12 hours of disclosure

# For agents that accept image URLs:
# 1. Only allow data: URLs or pre-validated CDN URLs
# 2. Block 169.254.0.0/16 (AWS/GCP/Azure metadata ranges)
# 3. Block 127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
# 4. Timeout external image fetches to <5 seconds
```

**Deserialization hygiene**
```python
# vLLM and lmdeploy use torch.load() internally
# Only load model files from sources you control
# For third-party models: verify SHA-256 before loading
import hashlib
expected_sha = "a3f5c..."
actual_sha = hashlib.sha256(model_bytes).hexdigest()
assert actual_sha == expected_sha, "Model file checksum mismatch"

# If you must load third-party weights:
# - Run model loading in an isolated process with seccomp + AppArmor
# - Or use a model sandbox (see S-298: sandboxing as persistence layer)
```

### 3. Monitor the exploit window

The 12-hour exploitation of LMDeploy CVE-2026-33626 is the benchmark. Your detection tooling must catch exploitation attempts, not just vulnerabilities:

```yaml
#otel-metrics:
#  inference_server_anomalies:
#    - metric: http_request_duration_bucket
#      filter: uri matches "/v1/models/*" && status == 200
#      alert: request from internal IP ranges to metadata endpoint
#    - metric: model_load_duration_seconds
#      alert: load time > 3x baseline (potential malicious payload parsing)
#    - metric: ssrf_probe_detected
#      alert: outgoing HTTP from inference process to RFC-1918 address
```

### 4. The isolation requirement

For any untrusted model source:
```bash
# Run inference server with seccomp + AppArmor/SELinux confinement
# The inference process should NOT be able to:
#   - Make outbound network connections (except to model registry)
#   - Read /proc/[other_pid]/environ
#   - Access /var/secrets/, ~/.aws/credentials, or cloud metadata
#   - Execute arbitrary code via mmap or execve on loaded data

# Kubernetes: run inference workloads in a dedicated security context
securityContext:
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
  seccompProfile:
    type: RuntimeDefault
```

### 5. Supply chain verification

```bash
# Verify model integrity before loading
# Option 1: Hugging Face model integrity
# models are signed with GPG; verify with:
huggingface-cli scan-model <model-id>

# Option 2: Community model pinning
# Use model integrity hashes from a trusted registry, not HF page metadata

# Option 3: Private model registry
# Push models to an internal registry with SHA-256 verification on pull
```

> Receipt pending — verification commands require live access to a serving framework environment.

## See also
- [S-2778 · The Model File Supply Chain Stack](/stacks/s2778-the-model-file-supply-chain-stack-when-your-inference-server-runs-attacker-code-the-moment-it-loads-a-model.md) — GGUF/Jinja2 RCE via model templates
- [S-201 · MCP Server Security Hardening](/stacks/s201-mcp-server-security-hardening.md) — MCP server CVE landscape and hardening
- [S-77 · System Prompt Injection Hardening](/stacks/s77-system-prompt-injection-hardening.md) — model behavior layer defenses
- [F-194 · AgentJacking & MCP Tool-Response Poisoning](/forward-deployed/f194-agentjacking-mcp-tool-response-poisoning.md) — agent-level supply chain attacks
