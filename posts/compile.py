#!/usr/bin/env python3
"""
compile.py - Compiles .mdtx files to HTML with LaTeX math support.

Usage:
    python3 -m compile src
"""
import os, re, sys, time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple

class MDTXCompiler:
    def __init__(self, source_dir: str):
        # Source directory is posts/src/
        self.source_dir = Path(source_dir).resolve()
        # Root directory is posts/ (one level up from source)
        self.root_dir = self.source_dir.parent
        self._mtimes  = {}

    def scan(self) -> List[Path]:
        return list(self.source_dir.glob("*.mdtx"))

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
        
        # Handle links with more robust regex that can handle whitespace and newlines
        def link_repl(m):
            link_text = m.group(1).strip()
            link_url = m.group(2).strip()
            # Clean up any extra whitespace or newlines in the URL, but preserve the URL structure
            link_url = re.sub(r'\s+', '', link_url)
            # Ensure we have a valid URL
            if link_url:
                return f'<a href="{link_url}">{link_text}</a>'
            else:
                # If URL is empty, return the original text
                return f'[{link_text}]({m.group(2)})'
        
        # Handle https:// URLs with a more robust pattern
        # Use a greedy match to ensure we capture the full URL
        text = re.sub(r'\[([^\]]+)\]\((https://[^)]+)\)', link_repl, text, flags=re.DOTALL)
        
        # Then handle other URLs with the restrictive pattern
        return re.sub(r'\[([^\]]+)\]\(([^)<>]+)\)', link_repl, text, flags=re.DOTALL)

    def apply_emphasis(self, text: str) -> str:
        # Handle bold text first: **text** -> <strong>text</strong>
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        # Handle italic text: *text* -> <em>text</em>
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        return text

    def process_inline_code(self, text: str) -> str:
        # Handle inline code with single backticks: `code`
        def repl(m):
            code = m.group(1)
            # Escape HTML characters in inline code
            code = code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            return f'<code>{code}</code>'
        return re.sub(r'`([^`]+)`', repl, text)

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
                return f'<sup><a href="#fn{i}" id="fnref{i}" aria-label="Footnote {i}">{i}</a></sup>'
            return m.group(0)
        return re.sub(r'\[\^([^\]]+)\]', r, text)

    def footnotes_html(self, fns: Dict[str,str]) -> str:
        if not fns:
            return ""
        parts = ['<div class="footnotes">','<ol>']
        for i, t in fns.items():
            # Process the footnote text for emphasis and other formatting
            processed_text = self.apply_emphasis(t.strip())
            parts.append(f'<li id="fn{i}">{processed_text} <a href="#fnref{i}" class="footnote-backref" aria-label="Back to reference">↩</a></li>')
        parts.append('</ol></div>')
        return "\n".join(parts)

    def process_code(self, text: str) -> str:
        # Handle code blocks with syntax: code[language]: ... end code;
        def repl(m):
            lang, code = m.group(1), m.group(2)
            # Escape HTML characters in code
            code = code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            return f'<pre><code class="language-{lang}">{code}</code></pre>'
        
        # More robust pattern that handles multiline code blocks
        pattern = re.compile(
            r'code\[([^\]]+)\]:\s*\n'
            r'([\s\S]*?)'
            r'\nend code;?',  # Make semicolon optional
            re.DOTALL
        )
        return pattern.sub(repl, text)

    def process_image(self, text: str) -> str:
        def repl(m):
            src=alt=width=caption=""
            for L in m.group(1).splitlines():
                l = L.strip()
                if l.startswith('src:'):     src     = l.split(':',1)[1].strip().rstrip(';')
                if l.startswith('alt:'):     alt     = l.split(':',1)[1].strip().rstrip(';')
                if l.startswith('width:'):   width   = l.split(':',1)[1].strip().rstrip(';')
                if l.startswith('caption:'): caption = l.split(':',1)[1].strip().rstrip(';')
            
            # Images are referenced by name only and located in blog/filename/
            # For file "a.mdtx" with image "img.png", path should be "img.png"
            # Strip any "imgs/" prefix since images are directly in the output directory
            if src.startswith('imgs/'):
                src = src[5:]  # Remove "imgs/" prefix
            
            style = f' style="width:{width}"' if width else ''
            img_html = f'<img src="{src}" alt="{alt}"{style}>'
            return f'<figure>{img_html}<figcaption>{caption}</figcaption></figure>' if caption else img_html
        return re.sub(r'image:\s*\n(.*?)\nend image;?', repl, text, flags=re.DOTALL)  # Make semicolon optional

    def process_example(self, text: str) -> str:
        pattern = re.compile(
            r'example:\s*\n'
            r'([\s\S]*?)'
            r'\nend example;?',  # Match and consume the end marker  
            re.DOTALL
        )
        def repl(m):
            block   = m.group(1)
            t_m     = re.search(r'title:\s*(.+?)(?:;|\n)',      block)  # Look for semicolon or newline
            title   = t_m.group(1).strip()   if t_m   else ''
            
            # Handle both original format "content: {" and processed format "content: \begin{equation}"
            content_start = block.find('content: {')
            if content_start != -1:
                content_start += len('content: {')
                # Find the closing "}" by counting braces to handle nested content
                # Skip the opening brace of content: {
                brace_count = 1
                content_end = content_start
                
                # Look for the matching closing brace, handling nested braces
                for i, char in enumerate(block[content_start:], content_start):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            content_end = i
                            break
                
                if content_end > content_start:
                    body = block[content_start:content_end].strip()
                else:
                    body = ''
            else:
                # Try the processed format with \begin{equation}
                content_start = block.find('content: \\begin{equation}')
                if content_start != -1:
                    content_start += len('content: \\begin{equation}')
                    # Find the corresponding \end{equation}
                    content_end = block.find('\\end{equation}', content_start)
                    if content_end != -1:
                        body = block[content_start:content_end].strip()
                    else:
                        body = ''
                else:
                    body = ''
            
            # Recursively process the example box content through the main processing pipeline
            # Process math FIRST so lists can handle the processed content
            body = self.replace_display_math(body)  # Process display math first
            body = self.replace_inline_math(body)  # Process inline math
            body = self.process_image(body)
            body = self.process_lists_in_example(body)  # Special list processing for example boxes
            body = self.apply_emphasis(body)  # Process emphasis last
            
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
        # First try to match lists with explicit 'end list;' markers
        pattern_with_end = re.compile(
            r'list\[([^\]]+)\]:\s*\n'
            r'((?:\s*-\s*[^\n]*\n(?:[^\n]*\n)*?)+)'  # List items that may contain multiple lines
            r'\s*end list;?',  # Look for end list marker (with or without newline)
            re.DOTALL
        )

        # Then match lists without explicit 'end list;' markers
        # These end at the first non-list content (blank line followed by non-indented text)
        pattern_without_end = re.compile(
            r'list\[([^\]]+)\]:\s*\n'
            r'((?:[ \t]*-[ \t]*[^\n]*(?:\n[ \t]+[^\n]*)*\n?)+)',  # List items and their continuations
            re.DOTALL
        )
        def repl(m):
            list_type = m.group(1)
            content = m.group(2)

            # Parse nested list structure
            def parse_nested_list(lines):
                items = []
                i = 0
                while i < len(lines):
                    line = lines[i]
                    if not line.strip():
                        i += 1
                        continue

                    # Check if this is a list item
                    if line.strip().startswith('- '):
                        item_text = line.strip()[2:].strip()
                        sub_items = []

                        # Look ahead for nested items
                        j = i + 1
                        while j < len(lines):
                            next_line = lines[j]
                            if not next_line.strip():
                                j += 1
                                continue

                            # Check indentation level
                            current_indent = len(line) - len(line.lstrip())
                            next_indent = len(next_line) - len(next_line.lstrip())

                            if next_indent > current_indent and next_line.strip().startswith('- '):
                                # This is a nested item
                                nested_text = next_line.strip()[2:].strip()
                                nested_sub_items = []

                                # Look for deeper nesting
                                k = j + 1
                                while k < len(lines):
                                    deeper_line = lines[k]
                                    if not deeper_line.strip():
                                        k += 1
                                        continue

                                    deeper_indent = len(deeper_line) - len(deeper_line.lstrip())
                                    if deeper_indent > next_indent and deeper_line.strip().startswith('- '):
                                        deeper_text = deeper_line.strip()[2:].strip()
                                        nested_sub_items.append(f'<li>{self.apply_emphasis(deeper_text)}</li>')
                                        k += 1
                                    else:
                                        break

                                if nested_sub_items:
                                    nested_html = f'<ul>{"".join(nested_sub_items)}</ul>'
                                    nested_text += nested_html

                                sub_items.append(f'<li>{self.apply_emphasis(nested_text)}</li>')
                                j = k
                            elif next_indent == current_indent and next_line.strip().startswith('- '):
                                # Same level item, break
                                break
                            else:
                                # Continuation of current item
                                item_text += " " + next_line.strip()
                                j += 1

                        if sub_items:
                            sub_html = f'<ul>{"".join(sub_items)}</ul>'
                            item_text += sub_html

                        items.append(f'<li>{self.apply_emphasis(item_text)}</li>')
                        i = j
                    else:
                        i += 1

                return items

            lines = content.splitlines()
            items = parse_nested_list(lines)
            lis = ''.join(items)

            if list_type.startswith('o'):
                parts = list_type.split('-', 1)
                att = f' type="{parts[1]}"' if len(parts)==2 else ''
                return f'<ol{att}>{lis}</ol>'
            return f'<ul>{lis}</ul>'

        # First process lists with explicit 'end list;' markers
        text = pattern_with_end.sub(repl, text)
        # Then process lists without 'end list;' markers
        text = pattern_without_end.sub(repl, text)
        return text

    def process_lists_in_example(self, text: str) -> str:
        """Process lists in example boxes that don't have explicit 'end list;' markers"""
        pattern = re.compile(
            r'list\[([^\]]+)\]:\s*\n'
            r'((?:[ \t]*-[ \t]*[^\n]*(?:\n[ \t]+[^\n]*)*\n?)*)',  # Match list items and their continuations
            re.DOTALL
        )
        def repl(m):
            list_type = m.group(1)
            content = m.group(2)
            
            # Parse list structure with proper multi-line item handling
            def parse_list_items(text_content):
                lines = text_content.splitlines()
                items = []
                i = 0
                
                while i < len(lines):
                    line = lines[i]
                    if not line.strip():
                        i += 1
                        continue
                    
                    # Check if this starts a top-level list item
                    if line.strip().startswith('- '):
                        # Get the base indentation level for this item
                        base_indent = len(line) - len(line.lstrip())
                        item_content = [line.strip()[2:].strip()]  # Remove '- ' prefix
                        
                        # Collect all lines that belong to this item (including sub-items)
                        j = i + 1
                        sub_items = []
                        
                        while j < len(lines):
                            next_line = lines[j]
                            
                            # Empty lines are part of the item
                            if not next_line.strip():
                                j += 1
                                continue
                            
                            next_indent = len(next_line) - len(next_line.lstrip())
                            
                            # If next line starts a new top-level item, stop
                            if next_indent <= base_indent and next_line.strip().startswith('- '):
                                break
                            
                            # If it's a sub-item (indented and starts with -)
                            if next_indent > base_indent and next_line.strip().startswith('- '):
                                sub_item_text = next_line.strip()[2:].strip()
                                sub_items.append(f'<li>{self.apply_emphasis(sub_item_text)}</li>')
                                j += 1
                            elif next_indent > base_indent:
                                # Continuation of current item (not a sub-item)
                                item_content.append(next_line.strip())
                                j += 1
                            else:
                                # Unindented content that's not a list item - stop here
                                break
                        
                        # Build the full item
                        full_item = " ".join(filter(None, item_content))  # Filter out empty strings
                        if sub_items:
                            # Add nested list if there are sub-items
                            sub_list = f'<ul>{"".join(sub_items)}</ul>'
                            full_item += sub_list
                        
                        items.append(f'<li>{self.apply_emphasis(full_item)}</li>')
                        i = j
                    else:
                        i += 1
                
                return items
            
            items = parse_list_items(content)
            lis = ''.join(items)
            
            if list_type.startswith('o'):
                parts = list_type.split('-', 1)
                att   = f' type="{parts[1]}"' if len(parts)==2 else ''
                return f'<ol{att}>{lis}</ol>'
            return f'<ul>{lis}</ul>'
        return pattern.sub(repl, text)

    def replace_display_math(self, text: str) -> str:
        # Find { ... } blocks that span multiple lines and convert them to \begin{equation} ... \end{equation}
        # Handle both standalone { ... } blocks and indented ones
        pat = re.compile(
            r'(.*?)\n\s*\{\s*\n'   # Any content ending with newline, then { on new line with optional whitespace and newline
            r'([\s\S]*?)'          # Content (non-greedy)
            r'\n\s*\}',            # Closing } on its own line with optional whitespace
            re.MULTILINE | re.DOTALL
        )
        def sub(m):
            # Keep the preceding content and wrap the math content in equation environment
            preceding = m.group(1)
            math_content = m.group(2)
            return f"{preceding}\n\\begin{{equation}}\n{math_content}\n\\end{{equation}}"
        return pat.sub(sub, text)



    def replace_inline_math(self, text: str) -> str:
        # Preserve existing \( \) patterns as-is (they're already LaTeX verbatim)
        # Only convert standalone {} patterns to inline math
        
        def process_math_in_content(content: str) -> str:
            # Process {} patterns in text content (not inside HTML tags or existing math)
            out, i, n = [], 0, len(content)
            while i < n:
                # Skip existing math blocks
                if content[i:i+2] == '\\(':
                    # Find end of inline math
                    end = content.find('\\)', i+2)
                    if end != -1:
                        out.append(content[i:end+2])
                        i = end + 2
                        continue
                elif content[i:i+16] == '\\begin{equation}':
                    # Find end of display math
                    end = content.find('\\end{equation}', i+16)
                    if end != -1:
                        out.append(content[i:end+14])
                        i = end + 14
                        continue
                elif content[i] == '{':
                    # Find matching closing brace, handling nested braces
                    depth, j = 1, i+1
                    while j < n and depth > 0:
                        if   content[j]=='{': depth += 1
                        elif content[j]=='}': depth -= 1
                        j += 1
                    if depth == 0:
                        inner = content[i+1:j-1]
                        # Wrap in \( \) for inline math
                        out.append(f'\\({inner}\\)')
                        i = j
                        continue
                out.append(content[i])
                i += 1
            return "".join(out)
        
        # Split text into HTML tags and content, only process content parts
        parts = re.split(r'(<[^>]*>)', text)
        for i in range(len(parts)):
            if not parts[i].startswith('<'):  # Not an HTML tag
                parts[i] = process_math_in_content(parts[i])
        
        return "".join(parts)

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
        # First, protect any existing code blocks, divs, etc. by replacing them with placeholders
        protected_blocks = {}
        placeholder_counter = 0
        
        # Protect multi-line HTML blocks (like <pre>, <div>, etc.)
        for tag in ['pre', 'div', 'ol', 'ul']:
            pattern = re.compile(f'<{tag}[^>]*>.*?</{tag}>', re.DOTALL)
            def protect_block(m):
                nonlocal placeholder_counter
                placeholder = f'__PROTECTED_BLOCK_{placeholder_counter}__'
                protected_blocks[placeholder] = m.group(0)
                placeholder_counter += 1
                return placeholder
            text = pattern.sub(protect_block, text)
        
        # Now process paragraphs normally
        blocks = re.split(r'\n\s*\n', text.strip())
        out    = []
        for blk in blocks:
            chunk = blk.strip()
            # Skip if it's already HTML, a placeholder, or empty
            if (chunk.startswith('<') and chunk.endswith('>')) or chunk.startswith('__PROTECTED_BLOCK_') or not chunk:
                out.append(chunk)
            else:
                # Only process as paragraph if it's not already processed
                line = ' '.join(l.strip() for l in blk.splitlines())
                if line:  # Only add paragraph if there's content
                    line = self.apply_emphasis(line)
                    out.append(f'<p>{line}</p>')
        
        # Restore protected blocks
        result = "\n".join(out)
        for placeholder, original in protected_blocks.items():
            result = result.replace(placeholder, original)
        
        return result


    
    def extract_all_urls(self, text: str) -> tuple[str, dict[str, tuple[str, str]]]:
        """Extract ALL URLs and replace with simple placeholders."""
        url_map = {}
        url_counter = 0
        
        def replace_url(match):
            nonlocal url_counter
            url_counter += 1
            # Use a more unique placeholder format to avoid conflicts
            placeholder = f'__URL_PLACEHOLDER_{url_counter}__'
            link_text = match.group(1)
            link_url = match.group(2)
            url_map[placeholder] = (link_text, link_url)
            return placeholder
        
        # Extract all markdown-style URLs [text](url) regardless of content
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', replace_url, text, flags=re.DOTALL)
        
        return text, url_map
    
    def restore_urls_as_html(self, text: str, url_map: dict[str, tuple[str, str]]) -> str:
        """Restore all URLs as proper HTML links."""
        # Sort placeholders by number (descending) to avoid partial replacements
        # This ensures PLACEHOLDER_10_ is replaced before PLACEHOLDER_1_
        sorted_items = sorted(url_map.items(), key=lambda x: int(x[0].split('_')[-2]) if x[0].split('_')[-2].isdigit() else 0, reverse=True)
        
        for placeholder, (link_text, link_url) in sorted_items:
            # Clean up the URL (remove extra whitespace/newlines)
            link_url = re.sub(r'\s+', '', link_url.strip())
            html_link = f'<a href="{link_url}">{link_text}</a>'
            # Use exact replacement to avoid partial matches
            text = text.replace(placeholder, html_link)
        return text

    def generate_blog_index(self):
        """Generate the blog index page from all MDTX files"""
        mdtx_files = list(self.source_dir.glob("*.mdtx"))
        posts = []
        
        for mdtx_file in mdtx_files:
            try:
                raw = mdtx_file.read_text(encoding='utf8')
                raw = self.remove_comments(raw)
                _, body = self.process_requires(raw)
                meta, _ = self.parse_metadata(body)
                
                # Skip files that don't have required fields
                if not meta.get('title') or not meta.get('desc'):
                    continue
                
                posts.append({
                    'filename': mdtx_file.stem,
                    'title': meta.get('title', 'Untitled'),
                    'date': meta.get('date', ''),
                    'desc': meta.get('desc', ''),
                    'tags': meta.get('tags', '')
                })
            except Exception as e:
                print(f"Warning: Could not parse {mdtx_file.name}: {e}")
                continue
        
        # Sort posts by date (most recent first)
        # [In Progress] posts go to bottom, then sort by actual dates
        import re
        from datetime import datetime
        
        def sort_key(post):
            date_str = post['date'].strip()
            if date_str == '[In Progress]':
                # Return a very old date to put at bottom
                return datetime(1800, 1, 1)
            
            # Common date patterns in your blog
            patterns = [
                r'(\w+) (\d+), (\d+)',        # "Sep 13, 2025"
                r'(\w+)\.? (\d+), (\d+)',     # "Aug. 23, 2025"
                r'(\w+) (\d+) (\d+)'          # "Jan 19 2025"
            ]
            
            month_map = {
                'Jan': 1, 'January': 1, 'Feb': 2, 'February': 2, 'Mar': 3, 'March': 3,
                'Apr': 4, 'April': 4, 'May': 5, 'Jun': 6, 'June': 6, 'Jul': 7, 'July': 7,
                'Aug': 8, 'August': 8, 'Sep': 9, 'September': 9, 'Oct': 10, 'October': 10,
                'Nov': 11, 'November': 11, 'Dec': 12, 'December': 12
            }
            
            for pattern in patterns:
                match = re.match(pattern, date_str)
                if match:
                    try:
                        month_str, day_str, year_str = match.groups()
                        month = month_map.get(month_str, 1)
                        day = int(day_str)
                        year = int(year_str)
                        return datetime(year, month, day)
                    except (ValueError, KeyError):
                        continue
            
            # If parsing fails, return a very old date to put at bottom
            return datetime(1900, 1, 1)
        
        posts.sort(key=sort_key, reverse=True)
        
        # Generate the blog posts HTML in the new clean format
        # Define canonical tag order
        tag_order = ['math', 'physics', 'ml', 'misc']

        posts_html = []
        for post in posts:
            # Generate tags HTML if tags exist
            tags_html = ''
            if post.get('tags') and post['tags'].strip():
                tag_list = [tag.strip() for tag in post['tags'].split(',') if tag.strip()]
                # Sort tags by canonical order
                tag_list.sort(key=lambda t: tag_order.index(t) if t in tag_order else 999)
                if tag_list:
                    tags_html = '<div class="post-tags">' + ''.join([f'<span class="tag" data-tag="{tag}">{tag}</span>' for tag in tag_list]) + '</div>'

            posts_html.append(f'''            <div class="blog-post-item" data-tags="{post['tags']}">
                <span class="post-date">{post['date']}</span>
                <div class="post-content">
                    <h3><a href="/posts/{post['filename']}">{post['title']}</a>{tags_html}</h3>
                    <p class="post-description">{post['desc']}</p>
                </div>
            </div>''')

        posts_section = '\n'.join(posts_html)

        # Read the current blog index template
        index_path = self.root_dir / "index.html"
        if index_path.exists():
            current_content = index_path.read_text(encoding='utf8')

            # Replace the posts section while preserving tag filters
            import re
            if '<div class="tag-filters">' in current_content:
                # Replace all blog-post-items after tag-filters, before </section>
                pattern = r'(<div class="tag-filters">.*?</div>)\s*<div class="blog-post-item".*?(?=\s*</section>)'
                replacement = r'\1\n' + posts_section + r'\n        '
            else:
                # No tag filters yet, add them along with posts
                pattern = r'(<h2>Posts</h2>)\s*(.*?)(?=\s*</section>)'
                tag_filters = '''            <div class="tag-filters">
                <button class="tag-filter active" data-filter="all">all</button>
                <button class="tag-filter" data-filter="math">math</button>
                <button class="tag-filter" data-filter="physics">physics</button>
                <button class="tag-filter" data-filter="ml">ml</button>
                <button class="tag-filter" data-filter="misc">misc</button>
            </div>
'''
                replacement = r'\1\n' + tag_filters + posts_section + r'\n        '

            new_content = re.sub(pattern, replacement, current_content, flags=re.DOTALL)

            # Write the updated index
            index_path.write_text(new_content, encoding='utf8')
            print(f"Updated blog index with {len(posts)} posts")
        else:
            print("Warning: blog/index.html not found")

    def compile_file(self, path: Path):
        raw  = path.read_text(encoding='utf8')
        
        # Extract ALL URLs IMMEDIATELY after reading, before any processing
        raw, url_map = self.extract_all_urls(raw)
        
        raw  = self.remove_comments(raw)
        reqs, body = self.process_requires(raw)
        meta, body = self.parse_metadata(body)
        fns,  body = self.extract_footnotes(body)
        
        # ←── minimal fix: strip any leftover 'desc:' or 'tags:' lines 
        body = re.sub(r'(?m)^(?:desc|tags):.*\n', '', body)

        # now build date + desc blocks from meta, with emphasis processing
        date_html = f'            <p class="date">{self.apply_emphasis(meta["date"])}</p>\n' if meta.get("date") else ""
        desc_html = f'            <p class="desc">{self.apply_emphasis(meta["desc"])}</p>\n'  if meta.get("desc") else ""

        # Process emphasis and inline code first
        body = self.apply_emphasis(body)
        body = self.process_inline_code(body)

        # Process display math BEFORE block-level elements so it's available in example boxes
        body = self.replace_display_math(body)

        # Process all block-level elements first (before paragraphs)
        body = self.process_code(body)
        body = self.process_image(body)
        body = self.process_example(body)
        body = self.process_lists(body)
        body = self.process_headings(body)
        

        # Process footnotes
        body = self.replace_footrefs(body, fns)
        
        # Process paragraphs last (after all other blocks are processed)
        body = self.process_paragraphs(body)
        
        # Restore all URLs as HTML links at the very end (skip convert_links entirely)
        body = self.restore_urls_as_html(body, url_map)

        # Process inline math last (after display math and paragraphs)
        body = self.replace_inline_math(body)

        # append footnotes
        fn_html = self.footnotes_html(fns)
        if fn_html:
            body += "\n" + fn_html

        if reqs:
            req_text = "".join(f"\\(\\require{{{r}}}\\)" for r in reqs)
            head_reqs = f"    <div style='display:none'>{req_text}</div>\n"
        else:
            head_reqs = ""
        title     = meta.get('title','Untitled')
        tags      = meta.get('tags', '')

        # Generate tags HTML for the post
        tags_html = ''
        if tags and tags.strip():
            tag_order = ['math', 'physics', 'ml', 'misc']
            tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
            # Sort tags by canonical order
            tag_list.sort(key=lambda t: tag_order.index(t) if t in tag_order else 999)
            if tag_list:
                tags_html = '<div class="post-tags">' + ''.join([f'<span class="tag" data-tag="{tag}">{tag}</span>' for tag in tag_list]) + '</div>'

        # Get current timestamp for footer
        compile_time = datetime.now().strftime("%b %d, %Y at %H:%M")
        
        # Create output directory structure
        # For file "a.mdtx" -> create "a/index.html"
        output_dir = self.root_dir / path.stem
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / "index.html"

        html = f"""<!DOCTYPE html>
<html lang="en">

<head>
{head_reqs}    <meta charset="UTF-8">
    <link rel="stylesheet" href="../../style.css">
    <link rel="stylesheet" href="../posts.css">
    <script src="../posts_header.js"></script>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>

    <!-- Configure MathJax to wait for TOC/footnotes before rendering -->
    <script>
        window.MathJax = {{
            startup: {{
                pageReady: () => {{
                    // Wait for TOC and footnotes to initialize first
                    return new Promise((resolve) => {{
                        if (document.readyState === 'loading') {{
                            document.addEventListener('DOMContentLoaded', () => {{
                                // Give TOC/footnotes a moment to set up
                                setTimeout(resolve, 100);
                            }});
                        }} else {{
                            setTimeout(resolve, 100);
                        }}
                    }}).then(() => MathJax.startup.defaultPageReady());
                }}
            }}
        }};
    </script>
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async
      src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
</head>

<body>
    <div id="header-placeholder"></div>

    <main class="blog-post">
        <section class="intro">
            <h1>{title}</h1>
            {tags_html}
{date_html}{desc_html}        </section>

{body}
    </main>

    <footer class="footer">
        <div class="last-updated">
            <p>Compiled {compile_time} | <a href="../src/{path.name}" target="_blank">Source</a></p>
        </div>
    </footer>

    <!-- Table of Contents Generator - loads before MathJax renders -->
    <script src="../toc-generator.js"></script>

    <!-- Footnote Sidebar - loads before MathJax renders -->
    <script src="../footnote-sidebar.js"></script>
</body>
</html>"""

        output_file.write_text(html, encoding='utf8')
        print("Compiled →", path.name, "→", output_file.relative_to(self.root_dir))

    def watch(self):
        print(f"Watching {self.source_dir} …")
        try:
            while True:
                files_changed = []
                for f in self.scan():
                    if self.changed(f):
                        self.compile_file(f)
                        files_changed.append(f)
                
                # Regenerate index if any files changed
                if files_changed:
                    self.generate_blog_index()
                    
                time.sleep(1)
        except KeyboardInterrupt:
            print("Stopped.")

if __name__=="__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 -m compile <src_dir> OR python3 -m compile <file.mdtx> OR python3 -m compile --index <src_dir>")
        sys.exit(1)
    
    # Check for index generation flag
    if sys.argv[1] == "--index":
        if len(sys.argv) != 3:
            print("Usage: python3 -m compile --index <src_dir>")
            sys.exit(1)
        source_dir = sys.argv[2]
        if not os.path.isdir(source_dir):
            print(f"Error: {source_dir} is not a directory")
            sys.exit(1)
        compiler = MDTXCompiler(source_dir)
        compiler.generate_blog_index()
        sys.exit(0)
    
    path_arg = sys.argv[1]
    
    if path_arg.endswith('.mdtx'):
        # Single file mode - compile once and watch that specific file
        file_path = Path(path_arg)
        if not file_path.exists():
            print(f"Error: File {file_path} not found")
            sys.exit(1)
        
        # Get the source directory from the file path
        source_dir = file_path.parent
        compiler = MDTXCompiler(source_dir)
        
        print(f"Compiling {file_path.name}...")
        compiler.compile_file(file_path)
        
        # Also regenerate index after compiling a file
        compiler.generate_blog_index()
        
        print(f"Watching {file_path.name} for changes...")
        try:
            while True:
                if compiler.changed(file_path):
                    print(f"Changes detected in {file_path.name}, recompiling...")
                    compiler.compile_file(file_path)
                    compiler.generate_blog_index()
                time.sleep(1)
        except KeyboardInterrupt:
            print("Stopped.")
            
    else:
        # Directory mode - watch entire source directory
        if not os.path.isdir(path_arg):
            print(f"Error: {path_arg} is not a directory")
            sys.exit(1)
        compiler = MDTXCompiler(path_arg)
        # Generate initial index
        compiler.generate_blog_index()
        compiler.watch()