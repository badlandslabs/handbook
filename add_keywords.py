#!/usr/bin/env python3
with open('knowledge-pulse.md', 'rb') as f:
    content = f.read()

keywords = [
    "evidence-verification",
    "calibration-dichotomy",
    "evidence-tool-overconfidence",
    "verification-tool-grounding",
    "tool-type-calibration",
    "retrieval-noise",
    "confidence-miscalibration",
    "rlhf-confidence",
    "tool-routing",
    "calibration-anchor",
    "acl-2026",
    "confidence-decay",
    "overconfidence-detection",
    "tool-type-classification",
    "evidence-tool",
    "verification-tool",
    "confidence-dichotomy",
    "xuan-2026",
]

keyword_lines = '\n'.join(f"{k} \xe2\x86\x92 I-3248" for k in sorted(keywords)) + '\n'

decision = """- *2026-08-11* \xe2\x80\x94 **I-3248 \xe2\x86\x92 S-2488 \xe2\x80\x94 The Evidence\xe2\x80\x93Verification Calibration Stack \xe2\x80\x94 Composite 9.30**: Fresh research from ACL 2026 (Xuan et al., arXiv:2026.acl-long.520). The paper's central finding: tool type is the primary driver of agent miscalibration. Evidence tools (web search, RAG) induce severe overconfidence due to noise in retrieved information \xe2\x80\x94 the model treats unverified text as authoritative and compounds error with certainty. Verification tools (code interpreters, calculators, test runners) ground reasoning via deterministic feedback, producing well-calibrated confidence. RLHF training rewards confident-sounding outputs, making this worse. Key architectural contributions: (1) classify every tool as evidence or verification type; (2) inject verification-tool alternatives wherever evidence tools dominate; (3) apply tool-type-specific confidence thresholds and decay multipliers; (4) use verification-tool outputs as calibration anchors for evidence-tool outputs; (5) route abstention to verification paths before human escalation. Deduplication: S-1793 covers general miscalibration but not tool-type-specific calibration; S-1052 covers cascade propagation of wrong facts but not the confidence mechanism; S-100 covers data staleness but not the confidence/computation aspect. This entry covers the tool-type-driven calibration architecture \xe2\x80\x94 a gap not addressed by any prior entry.
"""

# Step 1: Insert keywords into the deduplication index after the last Ideas Bank
# The Deduplication Index for the Ideas Bank at byte 930328 starts at 934966
di_start = content.find(b'\n## Deduplication Index\n', content.find(b'## Ideas Bank\n'))
if di_start == -1:
    print("Could not find Deduplication Index!")
    exit(1)

# Find the end of this deduplication index (next ## section)
di_content_start = di_start + len(b'\n## Deduplication Index\n')
di_end = content.find(b'\n## ', di_content_start)
if di_end == -1:
    di_end = len(content)

print(f"Deduplication Index: bytes {di_start} to {di_end}")

# Insert keywords at the end of the deduplication index
new_content = content[:di_end] + keyword_lines.encode('utf-8') + content[di_end:]

# Step 2: Add decision to the last Recent Decisions section
last_rd = new_content.rfind(b'\n## Recent Decisions\n')
if last_rd == -1:
    print("Could not find Recent Decisions!")
    exit(1)

rd_content_start = last_rd + len(b'\n## Recent Decisions\n')
rd_end = new_content.find(b'\n## ', rd_content_start)
if rd_end == -1:
    rd_end = len(new_content)

print(f"Recent Decisions section: bytes {rd_content_start} to {rd_end}")
new_content = new_content[:rd_end] + decision.encode('utf-8') + new_content[rd_end:]

with open('knowledge-pulse.md', 'wb') as f:
    f.write(new_content)
print("Tracker updated successfully")

# Verify
with open('knowledge-pulse.md', 'rb') as f:
    verify = f.read()
print(f"Keywords inserted: {verify.count(b'evidence-verification')} occurrences")
print(f"I-3248 in file: {'yes' if b'I-3248' in verify else 'NO'}")
print(f"Decision added: {'yes' if b'I-3248' in verify and b'S-2488' in verify else 'NO'}")
