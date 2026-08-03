content = open('knowledge-pulse.md').read()

# Fix the Deduplication Index - add I-3144 entries before ## Recent Decisions
old_block = """|vending-bench-collusion → I-3071
## Recent Decisions"""

new_block = """|vending-bench-collusion → I-3071
|instrumental-subgoal → I-3144
|reduced-cyber-refusals → I-3144
|evaluation-containment → I-3144
|subgoal-formation → I-3144
|ExploitGym → I-3144
|GPT-5.6-sol → I-3144
|answer-key-theft → I-3144
|goal-directed-escalation → I-3144
## Recent Decisions"""

count = content.count(old_block)
print(f"Found {count} occurrence(s)")
if count == 1:
    content = content.replace(old_block, new_block, 1)
    open('knowledge-pulse.md', 'w').write(content)
    print("Deduplication Index updated successfully")
else:
    idx = content.find('|vending-bench-collusion')
    print("Context around vending-bench-collusion:")
    print(repr(content[idx:idx+500]))
