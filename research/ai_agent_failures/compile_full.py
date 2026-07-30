import re

def extract_text(html):
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL|re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL|re.IGNORECASE)
    html = re.sub(r'<noscript[^>]*>.*?</noscript>', '', html, flags=re.DOTALL|re.IGNORECASE)
    html = re.sub(r'<svg[^>]*>.*?</svg>', '', html, flags=re.DOTALL|re.IGNORECASE)
    html = re.sub(r'<[^>]+>', ' ', html)
    html = html.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    html = html.replace('&quot;', '"').replace('&#39;', "'").replace('&mdash;', '---').replace('&ndash;', '--')
    html = html.replace('&hellip;', '...').replace('&rsquo;', "'").replace('&lsquo;', "'")
    html = html.replace('&rdquo;', '"').replace('&ldquo;', '"')
    html = html.replace('&#x2F;', '/').replace('&#x27;', "'")
    html = re.sub(r'[ \t]+', ' ', html)
    html = re.sub(r'\n\s*\n', '\n\n', html)
    return html.strip()

# Get full content of URLs 2, 4, 5 (they were large)
for fname, outname in [('url2.html', '02_zylos_FULL.txt'), 
                        ('url4.html', '04_agentbrisk_FULL.txt'),
                        ('url5.html', '05_circuitbreaker_FULL.txt')]:
    try:
        with open(f'/tmp/{fname}', 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        text = extract_text(content)
        with open(f'/opt/data/handbook/research/ai_agent_failures/{outname}', 'w') as f:
            f.write(text)
        print(f"{outname}: {len(text)} chars")
    except Exception as e:
        print(f"{fname}: ERROR {e}")
