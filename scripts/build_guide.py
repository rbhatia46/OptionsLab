#!/usr/bin/env python3
"""Render our authored Markdown guides into packaged, offline-readable help pages.

Supports the deliberately small subset used in docs: headings, flat lists,
paragraphs, tables, inline bold/code/links, and fenced code. Escapes all raw HTML.
"""
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def inline(text):
    text=html.escape(text)
    text=re.sub(r'`([^`]+)`',r'<code>\1</code>',text)
    text=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',text)
    def link(m):
        url={'methodology.md':'/methodology'}.get(m[2],m[2])
        return f'<a href="{url}">{m[1]}</a>'
    return re.sub(r'\[([^\]]+)\]\((https?://[^ )]+|[a-zA-Z0-9_./#-]+)\)',link,text)


def render(source):
    blocks=[];toc=[];lines=source.splitlines();i=0
    while i<len(lines):
        line=lines[i].strip()
        if not line:
            i+=1;continue
        if line.startswith('```'):
            code=[];i+=1
            while i<len(lines) and not lines[i].startswith('```'):
                code.append(lines[i]);i+=1
            blocks.append('<pre><code>'+html.escape('\n'.join(code))+'</code></pre>');i+=1;continue
        heading=re.match(r'^(#{1,3}) (.*)',line)
        if heading:
            level=len(heading[1]);title=heading[2];slug=re.sub(r'[^a-z0-9]+','-',title.lower()).strip('-')
            if level==2:toc.append((slug,title))
            blocks.append(f'<h{level} id="{slug}">{inline(title)}</h{level}>');i+=1;continue
        if line.startswith('|'):
            table=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                row=lines[i].strip().strip('|').split('|')
                if not all(re.fullmatch(r'\s*:?-+:?\s*',c) for c in row):
                    table.append([inline(c.strip()) for c in row])
                i+=1
            blocks.append('<div class="table-wrap"><table><thead><tr>'+''.join(f'<th>{c}</th>' for c in table[0])+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{c}</td>' for c in row)+'</tr>' for row in table[1:])+'</tbody></table></div>');continue
        listed=re.match(r'^(\d+\.|-) (.*)',line)
        if listed:
            ordered=listed[1]!='-';items=[]
            while i<len(lines):
                item=re.match(r'^(\d+\.|-) (.*)',lines[i].strip())
                if not item or (item[1]!='-')!=ordered:break
                items.append('<li>'+inline(item[2])+'</li>');i+=1
            tag='ol' if ordered else 'ul';blocks.append(f'<{tag}>'+''.join(items)+f'</{tag}>');continue
        paragraph=[]
        while i<len(lines) and lines[i].strip():
            paragraph.append(lines[i].strip());i+=1
        blocks.append('<p>'+inline(' '.join(paragraph))+'</p>')
    return '\n'.join(blocks),toc


if __name__=='__main__':
    for source,name in [('docs/usage-guide.md','guide.html'),('docs/methodology.md','methodology.html')]:
        body,toc=render((ROOT/source).read_text())
        navigation=''.join(f'<a href="#{slug}">{html.escape(title)}</a>' for slug,title in toc)
        title='Usage guide' if name=='guide.html' else 'Methodology'
        page='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'''+title+''' — Options Lab</title><link rel="icon" href="/favicon.svg"><link rel="stylesheet" href="/style.css"></head><body><header><a href="/" class="wordmark">OPTIONS <b>LAB</b></a><nav class="guide-nav"><a href="/" class="secondary">← Workbench</a><a class="secondary" href="/?preset=one-btc-example">Load the guide example</a><a class="secondary" href="/api/presets/one-btc-example" download="one-btc-example.json">↓ Example JSON</a></nav></header><main class="guide-main"><div class="eyebrow">LEARN THE WORKBENCH</div><details class="guide-contents"><summary>Jump to a section</summary><nav>'''+navigation+'''</nav></details><article class="prose guide-prose">'''+body+'''</article><div class="info-banner">Loading a preset only changes the builder. Review its controls and click Run backtest to execute it.</div></main></body></html>'''
        (ROOT/'app/options_lab/web'/name).write_text(page)
        print(f'Built {name}: {len(toc)} sections')
