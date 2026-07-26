content = open('knowledge-pulse.md').read()
import re
ids = re.findall(r'I-(\d+)', content)
max_id = max(int(i) for i in ids if i.isdigit())
print(f'I-{max_id + 1}')
