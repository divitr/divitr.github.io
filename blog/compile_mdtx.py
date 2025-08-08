#!/usr/bin/env python3
"""
compile_mdtx.py - Compiles .mdtx files to HTML with LaTeX math support.

Usage:
    python3 compile_mdtx.py [directory]
"""
import os, re, sys, time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple

class MDTXCompiler:
    def __init__(self, root_dir: str):
        self.root     = Path(root_dir).resolve()
        self._mtimes  = {}

    def scan(self) -> List[Path]:
        return list(self.root.rglob("*.mdtx"))

    def changed(self, p: Path) -> bool:
        m, k = p.stat().st_mtime, str(p)
        if k not in self._mtimes or m > self._mtimes[k]:
            self._mtimes[k] = m
            return True
        return False

    def remove_comments(self, text: str) -> str:
        return re.sub(r'//.*', '', text)

    def process_requires(self, text: str) -> Tuple[List[str], str]:
        reqs, out = [], []
        for L in text.splitlines():
            m = re.match(r'^\s*req:\s*([^;]+);', L.strip())
            if m:
                reqs.extend(r.strip() for r in m.group(1).split(','))
            else:
                out.append(L)
        return reqs, "\n".join(out)

    def parse_metadata(self, text: str) -> Tuple[Dict[str,str], str]:
        """
        Pull out all the lines up to the first empty line as metadata,
        split that on ';' into key:value pairs, then return (meta, body).
        """
        # split into metadata block and the rest
        parts = text.split('\n\n', 1)
        meta_block = parts[0]
        body       = parts[1] if len(parts) > 1 else ''
        
        meta = {}
        for entry in meta_block.split(';'):
            entry = entry.strip()
            if not entry:
                continue
            if ':' not in entry:
                continue
            k, v = entry.split(':', 1)
            meta[k.strip()] = v.strip()
        
        return meta, body


    def convert_links(self, text: str) -> str:
        text = re.sub(r'\*\[', '[', text)
        return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)

    def apply_emphasis(self, text: str) -> str:
        return re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)

    def extract_footnotes(self, text: str) -> Tuple[Dict[str,str], str]:
        fns, out = {}, []
        for L in text.splitlines():
            m = re.match(r'\[\^([^\]]+)\]:\s*(.+)', L.strip())
            if m:
                fns[m.group(1)] = m.group(2)
            else:
                out.append(L)
        return fns, "\n".join(out)

    def replace_footrefs(self, text: str, fns: Dict[str,str]) -> str:
        def r(m):
            i = m.group(1)
            if i in fns:
                return f'<sup><a href="#fn{i}" id="fnref{i}">{i}</a></sup>'
            return m.group(0)
        return re.sub(r'\[\^([^\]]+)\]', r, text)

    def footnotes_html(self, fns: Dict[str,str]) -> str:
        if not fns:
            return ""
        parts = ['<div class="footnotes">','<hr>','<ol>']
        for i, t in fns.items():
            parts.append(f'<li id="fn{i}">{t} <a href="#fnref{i}" class="footnote-backref">↩</a></li>')
        parts.append('</ol></div>')
        return "\n".join(parts)

    def process_code(self, text: str) -> str:
        def repl(m):
            lang, code = m.group(1), m.group(2)
            return f'<pre><code class="language-{lang}">{code}</code></pre>'
        return re.sub(r'code\[([^\]]+)\]:\s*\n(.*?)\nend code;',
                      repl, text, flags=re.DOTALL)

    def process_image(self, text: str) -> str:
        def repl(m):
            src=alt=width=caption=""
            for L in m.group(1).splitlines():
                l = L.strip()
                if l.startswith('src:'):     src     = l.split(':',1)[1].strip().rstrip(';')
                if l.startswith('alt:'):     alt     = l.split(':',1)[1].strip().rstrip(';')
                if l.startswith('width:'):   width   = l.split(':',1)[1].strip().rstrip(';')
                if l.startswith('caption:'): caption = l.split(':',1)[1].strip().rstrip(';')
            style = f' style="width:{width}"' if width else ''
            img_html = f'<img src="{src}" alt="{alt}"{style}>'
            return f'<figure>{img_html}<figcaption>{caption}</figcaption></figure>' if caption else img_html
        return re.sub(r'image:\s*\n(.*?)\nend image;', repl, text, flags=re.DOTALL)

    def process_example(self, text: str) -> str:
        pattern = re.compile(
            r'example:\s*\n'
            r'([\s\S]*?)'
            r'\nend example;',
            re.DOTALL
        )
        def repl(m):
            block   = m.group(1)
            t_m     = re.search(r'title:\s*(.+?);',      block)
            content = re.search(r'content:\s*\{([\s\S]*?)\};', block)
            title   = t_m.group(1).strip()   if t_m   else ''
            body    = content.group(1).rstrip() if content else ''
            body    = self.apply_emphasis(self.convert_links(body))
            return (
                '<div class="example-box">\n'
                  f'<div class="example-box-title">{title}</div>\n'
                  '<div class="example-box-prompt">\n'
                  f'{body}\n'
                  '</div>\n'
                '</div>\n'
            )
        return pattern.sub(repl, text)

    def process_lists(self, text: str) -> str:
        pattern = re.compile(
            r'list\[([^\]]+)\]:\s*\n'
            r'((?:\s*-\s*[^\n]+\n?)+)',
            re.DOTALL
        )
        def repl(m):
            list_type = m.group(1)
            lines     = m.group(2).splitlines()
            items     = [l.strip()[2:].strip() for l in lines if l.strip().startswith('- ')]
            items     = [self.apply_emphasis(self.convert_links(it)) for it in items]
            lis       = ''.join(f'<li>{it}</li>' for it in items)
            if list_type.startswith('o'):
                parts = list_type.split('-', 1)
                att   = f' type="{parts[1]}"' if len(parts)==2 else ''
                return f'<ol{att}>{lis}</ol>'
            return f'<ul>{lis}</ul>'
        return pattern.sub(repl, text)

    def replace_display_math(self, text: str) -> str:
        pat = re.compile(
            r'(^|\n)[ \t]*\{\s*\n'
            r'([\s\S]+?)'
            r'\n[ \t]*\}'
            r'(?=\n|$)',
            re.MULTILINE
        )
        def sub(m):
            return f"{m.group(1)}\\[\n{m.group(2)}\n\\]\n"
        return pat.sub(sub, text)

    def replace_inline_math(self, text: str) -> str:
        parts = re.split(r'(\\\[[\s\S]*?\\\])', text)
        for i in range(0, len(parts), 2):
            parts[i] = self._wrap_inline(parts[i])
        return "".join(parts)

    def _wrap_inline(self, seg: str) -> str:
        out, i, n = [], 0, len(seg)
        while i < n:
            if seg[i] == '{':
                depth, j = 1, i+1
                while j < n and depth > 0:
                    if   seg[j]=='{': depth += 1
                    elif seg[j]=='}': depth -= 1
                    j += 1
                if depth == 0:
                    inner = seg[i+1:j-1]
                    out.append(f'\\({inner}\\)')
                    i = j
                    continue
            out.append(seg[i])
            i += 1
        return "".join(out)

    def process_headings(self, text: str) -> str:
        out = []
        for L in text.splitlines():
            if L.startswith('#'):
                lvl = min(len(L) - len(L.lstrip('#')), 6)
                out.append(f'<h{lvl}>{L.lstrip("#").strip()}</h{lvl}>')
            else:
                out.append(L)
        return "\n".join(out)

    def process_paragraphs(self, text: str) -> str:
        blocks = re.split(r'\n\s*\n', text.strip())
        out    = []
        for blk in blocks:
            chunk = blk.strip()
            if chunk.startswith('<') and chunk.endswith('>'):
                out.append(chunk)
            else:
                line = ' '.join(l.strip() for l in blk.splitlines())
                line = self.convert_links(line)
                line = self.apply_emphasis(line)
                out.append(f'<p>{line}</p>')
        return "\n".join(out)

    def compile_file(self, path: Path):
        raw  = path.read_text(encoding='utf8')
        raw  = self.remove_comments(raw)
        reqs, body = self.process_requires(raw)
        meta, body = self.parse_metadata(body)
        fns,  body = self.extract_footnotes(body)

        # ←── minimal fix: strip any leftover 'desc:' or 'tags:' lines 
        body = re.sub(r'(?m)^(?:desc|tags):.*\n', '', body)

        # now build date + desc blocks from meta, with links & emphasis processing
        date_html = f'            <p class="date">{self.convert_links(self.apply_emphasis(meta["date"]))}</p>\n' if meta.get("date") else ""
        desc_html = f'            <p class="desc">{self.convert_links(self.apply_emphasis(meta["desc"]))}</p>\n'  if meta.get("desc") else ""

        # links & emphasis
        body = self.convert_links(body)
        body = self.apply_emphasis(body)

        # block transforms
        body = self.process_code(body)
        body = self.process_image(body)
        body = self.process_example(body)
        body = self.process_lists(body)

        # math
        body = self.replace_display_math(body)
        body = self.replace_inline_math(body)

        # headings & footnotes
        body = self.process_headings(body)
        body = self.replace_footrefs(body, fns)

        # paragraphs
        body = self.process_paragraphs(body)

        # append footnotes
        fn_html = self.footnotes_html(fns)
        if fn_html:
            body += "\n" + fn_html

        head_reqs = "".join(f"    \\(\\require{{{r}}}\\)\n" for r in reqs)
        title     = meta.get('title','Untitled')

        html = f"""<!DOCTYPE html>
<html lang="en">

<head>
{head_reqs}    <meta charset="UTF-8">
    <link rel="icon" href="../../favicon.ico" type="image/x-icon">
    <link rel="stylesheet" href="../blog_style.css">
    <link rel="stylesheet"
          href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async
      src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
</head>

<body>
    <script src="../toc-generator.js"></script>
    <header>
        <div class="logo">
          <a href="/" style="text-decoration:none;color:#4a4a4a">DR</a>
        </div>
        <nav>
          <a href="/research">Research</a>
          <a href="/blog">Blog</a>
        </nav>
    </header>

    <main>
        <article class="intro">
            <h1>{title}</h1>
{date_html}{desc_html}        </article>

{body}

    </main>
</body>
</html>"""

        path.with_suffix('.html').write_text(html, encoding='utf8')
        print("Compiled →", path.relative_to(self.root))

    def watch(self):
        print(f"Watching {self.root} …")
        try:
            while True:
                for f in self.scan():
                    if self.changed(f):
                        self.compile_file(f)
                time.sleep(1)
        except KeyboardInterrupt:
            print("Stopped.")

if __name__=="__main__":
    if len(sys.argv)!=2:
        print("Usage: python3 compile_mdtx.py [directory]")
        sys.exit(1)
    d = sys.argv[1]
    if not os.path.isdir(d):
        print(f"Error: {d} is not a directory")
        sys.exit(1)
    MDTXCompiler(d).watch()