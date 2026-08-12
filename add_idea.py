#!/usr/bin/env python3
with open('knowledge-pulse.md', 'rb') as f:
    content = f.read()

new_entry = '| I-3248 | The Evidence\u2013Verification Calibration Stack \u2014 When Your Search-Powered Agent Is Certain and Wrong | evidence-verification, calibration-dichotomy, evidence-tool-overconfidence, verification-tool-grounding, tool-type-calibration, retrieval-noise, confidence-miscalibration, rlhf-confidence, tool-routing, calibration-anchor, acl-2026, confidence-decay, overconfidence-detection, tool-type-classification, evidence-tool, verification-tool, xuan-2026, arxiv-acl-520 | 9 | 9 | 10 | 10 | 8 | **9.30** | WRITTEN \u2014 S-2488 | 2026-08-11 | 2026-08-11 |\n'

search_for = b'| I-3247 |'
pos = content.rfind(search_for)
if pos == -1:
    print("Could not find I-3247")
else:
    line_end = content.find(b'\n', pos)
    if line_end == -1:
        line_end = len(content)
    insert_pos = line_end + 1
    new_content = content[:insert_pos] + new_entry.encode('utf-8') + content[insert_pos:]
    with open('knowledge-pulse.md', 'wb') as f:
        f.write(new_content)
    print(f"Inserted I-3248 at line ending at byte {insert_pos}")
