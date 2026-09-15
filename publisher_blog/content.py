"""Small, deliberately limited Markdown importer for our authored articles."""
import re
from html import escape
from pathlib import Path

def read_article(path):
    text = Path(path).read_text(encoding='utf-8-sig').strip()
    blocks = text.split('\n\n')
    if not blocks[0].startswith('# '):
        raise ValueError('Article must start with a title.')
    title = blocks.pop(0)[2:].strip()
    def inline(value):
        safe = escape(value)
        return re.sub(r'\[([^\]]+)\]\((https://[^\s)]+)\)', r'<a href="\2">\1</a>', safe)
    html = []
    for block in blocks:
        if block.startswith('## '):
            html.append('<h2>' + inline(block[3:].strip()) + '</h2>')
        else:
            html.append('<p>' + inline(block.replace('\n', ' ')) + '</p>')
    return title, ''.join(html)

