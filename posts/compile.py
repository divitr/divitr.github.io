#!/usr/bin/env python3
"""
compile.py - Compiles .mdtx files to HTML with LaTeX math support.

Usage:
    python3 -m compile src
"""
import os, re, sys, time, subprocess, json, html
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple


def _extract_braced_arg(s: str, i: int):
    """Return (content, end_pos) for the balanced {…} group starting at s[i].
    Skips over \\{ and \\} so escaped braces don't affect depth counting.
    Returns (None, i) if s[i] is not '{' or braces are unmatched."""
    if i >= len(s) or s[i] != '{':
        return None, i
    depth, j = 0, i
    while j < len(s):
        if s[j] == '\\' and j + 1 < len(s):
            j += 2          # skip escaped character
            continue
        if s[j] == '{':
            depth += 1
        elif s[j] == '}':
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return None, i          # unmatched


def _expand_physics_macros(latex: str) -> str:
    """Expand \\norm, \\abs, \\dv, \\pdv (1- and 2-arg) to standard LaTeX
    that KaTeX understands natively."""
    result = []
    i, n = 0, len(latex)

    def skip_spaces(pos):
        while pos < n and latex[pos] in ' \t\n':
            pos += 1
        return pos

    while i < n:
        if latex[i] == '\\' and i + 1 < n:
            if latex[i + 1].isalpha():
                # Collect the full command name
                j = i + 1
                while j < n and latex[j].isalpha():
                    j += 1
                cmd = latex[i:j]

                if cmd == '\\norm':
                    k = skip_spaces(j)
                    arg, k = _extract_braced_arg(latex, k)
                    if arg is not None:
                        result.append(f'\\left\\| {arg} \\right\\|')
                        i = k
                        continue

                elif cmd == '\\abs':
                    k = skip_spaces(j)
                    arg, k = _extract_braced_arg(latex, k)
                    if arg is not None:
                        result.append(f'\\left| {arg} \\right|')
                        i = k
                        continue

                elif cmd == '\\dv':
                    k = skip_spaces(j)
                    arg1, k = _extract_braced_arg(latex, k)
                    if arg1 is not None:
                        k2 = skip_spaces(k)
                        arg2, k2 = _extract_braced_arg(latex, k2)
                        if arg2 is not None:
                            result.append(f'\\frac{{d {arg1}}}{{d {arg2}}}')
                            i = k2
                            continue

                elif cmd == '\\pdv':
                    k = skip_spaces(j)
                    arg1, k = _extract_braced_arg(latex, k)
                    if arg1 is not None:
                        k2 = skip_spaces(k)
                        arg2, k2 = _extract_braced_arg(latex, k2)
                        if arg2 is not None:
                            # 2-arg form: \pdv{f}{x} → \frac{\partial f}{\partial x}
                            result.append(f'\\frac{{\\partial {arg1}}}{{\\partial {arg2}}}')
                            i = k2
                        else:
                            # 1-arg operator form: \pdv{x} → \frac{\partial}{\partial x}
                            result.append(f'\\frac{{\\partial}}{{\\partial {arg1}}}')
                            i = k
                        continue

                # Unrecognised command — pass through unchanged
                result.append(cmd)
                i = j
                continue
            else:
                # Non-alpha after backslash (e.g. \\{ \\} \\, \\\\)
                result.append(latex[i:i + 2])
                i += 2
                continue

        result.append(latex[i])
        i += 1

    return ''.join(result)


def _plain_title_text(text: str) -> str:
    """Convert MDTX title text into a plain string suitable for <title>."""
    def math_repl(match):
        inner = match.group(1)
        inner = re.sub(r'\\([A-Za-z]+)', lambda m: {
            'mu': 'μ',
            'theta': 'θ',
            'phi': 'φ',
            'psi': 'ψ',
            'alpha': 'α',
            'beta': 'β',
            'gamma': 'γ',
            'delta': 'δ',
            'epsilon': 'ε',
            'lambda': 'λ',
            'sigma': 'σ',
            'tau': 'τ',
            'omega': 'ω',
        }.get(m.group(1), m.group(1)), inner)
        inner = re.sub(r'[{}^_]', '', inner)
        inner = re.sub(r'\s+', ' ', inner).strip()
        return inner

    text = re.sub(r'\{([^{}]*)\}', math_repl, text)
    return html.escape(text.strip(), quote=False)


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
        # Treat comments as whole-line directives so literal `//` can appear in prose/code.
        return re.sub(r'(?m)^[ \t]*//.*(?:\n|$)', '', text)

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
        
        # Ensure emoji is captured if present
        if 'emoji' not in meta:
            meta['emoji'] = ''
        
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
        # Inline code should stay on one line; do not let unmatched backticks bleed across paragraphs.
        return re.sub(r'`([^`\n]+)`', repl, text)

    def extract_footnotes(self, text: str) -> Tuple[Dict[str,str], str]:
        fns, out = {}, []
        for L in text.splitlines():
            m = re.match(r'\[\^([^\]]+)\]:\s*(.+)', L.strip())
            if m:
                fns[m.group(1)] = m.group(2)
            else:
                out.append(L)
        return fns, "\n".join(out)

    def build_footnote_numbers(self, text: str, fns: Dict[str, str]) -> Dict[str, int]:
        footnote_numbers = {}
        next_number = 1

        for match in re.finditer(r'\[\^([^\]]+)\]', text):
            label = match.group(1)
            if label in fns and label not in footnote_numbers:
                footnote_numbers[label] = next_number
                next_number += 1

        # Keep unreferenced footnotes stable by appending them in definition order.
        for label in fns:
            if label not in footnote_numbers:
                footnote_numbers[label] = next_number
                next_number += 1

        return footnote_numbers

    def replace_footrefs(self, text: str, fns: Dict[str,str], footnote_numbers: Dict[str, int]) -> str:
        def r(m):
            label = m.group(1)
            if label in fns and label in footnote_numbers:
                number = footnote_numbers[label]
                return f'<sup><a href="#fn{number}" id="fnref{number}" aria-label="Footnote {number}">{number}</a></sup>'
            return m.group(0)

        # Do not rewrite footnote markers inside code/pre blocks that should render literally.
        parts = re.split(r'(<code>[\s\S]*?</code>|<pre[\s\S]*?</pre>|<[^>]*>)', text)
        for i in range(len(parts)):
            if not parts[i].startswith('<'):
                parts[i] = re.sub(r'\[\^([^\]]+)\]', r, parts[i])
        return ''.join(parts)

    def footnotes_html(self, fns: Dict[str,str], footnote_numbers: Dict[str, int], bib_entries: dict = None, alpha_keys: dict = None) -> str:
        if not fns:
            return ""
        parts = ['<div class="footnotes">','<ol>']
        for label, t in sorted(fns.items(), key=lambda item: footnote_numbers[item[0]]):
            number = footnote_numbers[label]
            processed_text = t.strip()
            processed_text = self.apply_emphasis(processed_text)
            processed_text = self.process_inline_code(processed_text)
            if bib_entries:
                processed_text = self.process_citations(processed_text, bib_entries, alpha_keys)
            processed_text = self.replace_inline_math(processed_text)
            parts.append(f'<li id="fn{number}">{processed_text} <a href="#fnref{number}" class="footnote-backref" aria-label="Back to reference">↩</a></li>')
        parts.append('</ol></div>')
        return "\n".join(parts)

    def extract_bibliography(self, text: str) -> Tuple[str, str]:
        """Extracts the bibliography block from the text if it exists."""
        bib_match = re.search(r'bibliography:\s*(.*?)\s*end bibliography;?', text, re.DOTALL)
        if bib_match:
            bib_content = bib_match.group(1)
            # Remove the bibliography block from the text
            clean_text = text[:bib_match.start()] + text[bib_match.end():]
            return bib_content, clean_text
        return "", text

    def _clean_latex_accents(self, text: str) -> str:
        """Converts LaTeX character accents and capitalization braces to Unicode."""
        # Clean capitalization-preservation braces around individual letters: {H} -> H, {T} -> T
        text = re.sub(r'\{([A-Za-z])\}', r'\1', text)
        
        accents = {
            '`': {'a': 'à', 'e': 'è', 'i': 'ì', 'o': 'ò', 'u': 'ù', 'A': 'À', 'E': 'È', 'I': 'Ì', 'O': 'Ò', 'U': 'Ù'},
            "'": {'a': 'á', 'e': 'é', 'i': 'í', 'o': 'ó', 'u': 'ú', 'y': 'ý', 'A': 'Á', 'E': 'É', 'I': 'Í', 'O': 'Ó', 'U': 'Ú', 'Y': 'Ý'},
            '^': {'a': 'â', 'e': 'ê', 'i': 'î', 'o': 'ô', 'u': 'û', 'A': 'Â', 'E': 'È', 'I': 'Î', 'O': 'Ô', 'U': 'Û'},
            '~': {'a': 'ã', 'o': 'õ', 'n': 'ñ', 'A': 'Ã', 'O': 'Õ', 'N': 'Ñ'},
            '"': {'a': 'ä', 'e': 'ë', 'i': 'ï', 'o': 'ö', 'u': 'ü', 'y': 'ÿ', 'A': 'Ä', 'E': 'Ë', 'I': 'Ï', 'O': 'Ö', 'U': 'Ü'},
            'H': {'o': 'ő', 'u': 'ű', 'O': 'Ő', 'U': 'Ű'},
            'c': {'c': 'ç', 'C': 'Ç'},
        }
        
        def repl_braced(m):
            cmd, char = m.group(1), m.group(2)
            if cmd in accents and char in accents[cmd]:
                return accents[cmd][char]
            return m.group(0)
            
        # Matches {\"a} or {\~a}
        text = re.sub(r'\{\\([`\'"~^Hc])([a-zA-Z])\}', repl_braced, text)
        # Matches \"{a}
        text = re.sub(r'\\([`\'"~^Hc])\{([a-zA-Z])\}', repl_braced, text)
        # Matches \"a
        text = re.sub(r'\\([`\'"~^Hc])([a-zA-Z])', repl_braced, text)
        
        return text

    def parse_bibtex(self, bib_text: str) -> Dict[str, Dict[str, str]]:
        """Parses BibTeX content into a structured dictionary."""
        entries = {}
        pos = 0
        n = len(bib_text)
        while True:
            pos = bib_text.find('@', pos)
            if pos == -1:
                break
            
            entry_type_match = re.match(r'@([a-zA-Z0-9_]+)\s*\{', bib_text[pos:])
            if not entry_type_match:
                pos += 1
                continue
            
            entry_type = entry_type_match.group(1).lower()
            if entry_type in ('comment', 'preamble'):
                pos += len(entry_type_match.group(0))
                continue
                
            start_brace = pos + entry_type_match.end() - 1
            
            # Find matching closing brace
            brace_depth = 0
            end_pos = -1
            for i in range(start_brace, n):
                if bib_text[i] == '{':
                    brace_depth += 1
                elif bib_text[i] == '}':
                    brace_depth -= 1
                    if brace_depth == 0:
                        end_pos = i
                        break
            
            if end_pos == -1:
                pos += 1
                continue
                
            entry_content = bib_text[start_brace+1 : end_pos].strip()
            pos = end_pos + 1
            
            first_comma = entry_content.find(',')
            if first_comma == -1:
                key = entry_content.strip()
                fields_str = ""
            else:
                key = entry_content[:first_comma].strip()
                fields_str = entry_content[first_comma+1:].strip()
                
            fields = {'type': entry_type}
            
            # Scan fields key-value pairs
            f_pos = 0
            f_len = len(fields_str)
            while f_pos < f_len:
                field_match = re.match(r'\s*([a-zA-Z0-9_\-]+)\s*=\s*', fields_str[f_pos:])
                if not field_match:
                    f_pos += 1
                    continue
                
                field_name = field_match.group(1).lower()
                val_start = f_pos + field_match.end()
                
                if val_start >= f_len:
                    break
                    
                val_char = fields_str[val_start]
                val_end = -1
                if val_char == '{':
                    v_depth = 0
                    for j in range(val_start, f_len):
                        if fields_str[j] == '{':
                            v_depth += 1
                        elif fields_str[j] == '}':
                            v_depth -= 1
                            if v_depth == 0:
                                val_end = j
                                break
                    if val_end != -1:
                        val_val = fields_str[val_start+1 : val_end]
                        f_pos = val_end + 1
                    else:
                        val_val = fields_str[val_start+1:]
                        f_pos = f_len
                elif val_char == '"':
                    val_end = fields_str.find('"', val_start + 1)
                    if val_end != -1:
                        val_val = fields_str[val_start+1 : val_end]
                        f_pos = val_end + 1
                    else:
                        val_val = fields_str[val_start+1:]
                        f_pos = f_len
                else:
                    comma_pos = fields_str.find(',', val_start)
                    if comma_pos != -1:
                        val_val = fields_str[val_start:comma_pos].strip()
                        f_pos = comma_pos + 1
                    else:
                        val_val = fields_str[val_start:].strip()
                        f_pos = f_len
                        
                val_val = re.sub(r'\s+', ' ', val_val).strip()
                while len(val_val) >= 2 and val_val[0] == '{' and val_val[-1] == '}':
                    val_val = val_val[1:-1].strip()
                
                val_val = self._clean_latex_accents(val_val)
                fields[field_name] = val_val
                
            entries[key] = fields
        return entries

    def generate_alpha_key(self, entry: Dict[str, str]) -> str:
        """Generates an alpha-style key from author and year fields."""
        authors_str = entry.get('author', '').strip()
        year_str = entry.get('year', '').strip()
        
        year_suffix = ""
        if year_str:
            digits = re.sub(r'\D', '', year_str)
            if len(digits) >= 2:
                year_suffix = digits[-2:]
            else:
                year_suffix = digits
                
        if not authors_str:
            return "Unknown" + year_suffix
            
        authors = re.split(r'\s+[aA][nN][dD]\s+', authors_str)
        
        last_names = []
        for auth in authors:
            auth = auth.strip()
            if ',' in auth:
                last = auth.split(',', 1)[0].strip()
            else:
                parts = auth.split()
                last = parts[-1].strip() if parts else auth
                
            last = re.sub(r'[^a-zA-Z]', '', last)
            last_names.append(last)
            
        num_authors = len(last_names)
        if num_authors == 1:
            prefix = last_names[0][:3]
        elif num_authors == 2:
            prefix = (last_names[0][:1] if last_names[0] else "") + (last_names[1][:1] if last_names[1] else "")
        elif num_authors == 3:
            prefix = "".join(l[:1] for l in last_names[:3] if l)
        else:
            prefix = "".join(l[:1] for l in last_names[:3] if l) + "+"
            
        return prefix + year_suffix

    def format_authors_short(self, authors_str: str) -> str:
        """Formats author names list into clean reading representation."""
        if not authors_str:
            return ""
        authors = re.split(r'\s+[aA][nN][dD]\s+', authors_str)
        cleaned_authors = []
        for auth in authors:
            auth = auth.strip()
            if ',' in auth:
                parts = auth.split(',', 1)
                auth = parts[1].strip() + ' ' + parts[0].strip()
            cleaned_authors.append(auth)
            
        if len(cleaned_authors) == 1:
            return cleaned_authors[0]
        elif len(cleaned_authors) == 2:
            return f"{cleaned_authors[0]} and {cleaned_authors[1]}"
        elif len(cleaned_authors) == 3:
            return f"{cleaned_authors[0]}, {cleaned_authors[1]}, and {cleaned_authors[2]}"
        else:
            return f"{cleaned_authors[0]} et al."

    def process_citations(self, text: str, bib_entries: dict, alpha_keys: dict) -> str:
        """Processes in-text citations like ref@Knuth84 or refs@Knuth84,Rivest78."""
        citation_instances = {}
        
        # Match refs@ followed by multiple comma-separated keys
        pattern_multiple = re.compile(r'\brefs@([\w\-]+(?:\s*,\s*[\w\-]+)*)', re.IGNORECASE)
        # Match ref@ followed by a single key (no commas allowed)
        pattern_single = re.compile(r'\bref@([\w\-]+)', re.IGNORECASE)
        
        def repl_multiple(match):
            raw_keys = match.group(1)
            keys = [k.strip() for k in raw_keys.split(',')]
            
            # If none of the keys exist in the bibliography entries, keep the original text
            if not any(k in bib_entries for k in keys):
                return match.group(0)
            
            links = []
            for key in keys:
                if key in bib_entries:
                    entry = bib_entries[key]
                    alpha = alpha_keys.get(key, key)
                    
                    count = citation_instances.get(key, 0) + 1
                    citation_instances[key] = count
                    instance_id = f"cite-ref-{key}-{count}"
                    
                    title = entry.get('title', '').replace('"', '&quot;')
                    authors_display = self.format_authors_short(entry.get('author', '')).replace('"', '&quot;')
                    year = entry.get('year', '').replace('"', '&quot;')
                    
                    link_html = (
                        f'<a href="#cite-{key}" id="{instance_id}" class="citation-ref" '
                        f'data-title="{title}" data-authors="{authors_display}" data-year="{year}">'
                        f'{alpha}</a>'
                    )
                    links.append(link_html)
                else:
                    # Fallback for keys that were not found in the bibliography
                    links.append(key)
            
            return f"[{', '.join(links)}]"
            
        def repl_single(match):
            key = match.group(1)
            if key in bib_entries:
                entry = bib_entries[key]
                alpha = alpha_keys.get(key, key)
                
                count = citation_instances.get(key, 0) + 1
                citation_instances[key] = count
                instance_id = f"cite-ref-{key}-{count}"
                
                title = entry.get('title', '').replace('"', '&quot;')
                authors_display = self.format_authors_short(entry.get('author', '')).replace('"', '&quot;')
                year = entry.get('year', '').replace('"', '&quot;')
                
                return (
                    f'[<a href="#cite-{key}" id="{instance_id}" class="citation-ref" '
                    f'data-title="{title}" data-authors="{authors_display}" data-year="{year}">'
                    f'{alpha}</a>]'
                )
            return match.group(0)
            
        parts = re.split(r'(<code>[\s\S]*?</code>|<pre[\s\S]*?</pre>|<[^>]*>)', text)
        for i in range(len(parts)):
            if not parts[i].startswith('<'):
                parts[i] = pattern_multiple.sub(repl_multiple, parts[i])
                parts[i] = pattern_single.sub(repl_single, parts[i])
        return ''.join(parts)

    def format_bibliography_entry(self, entry: dict) -> str:
        """Formats a bibliography dictionary into a clean citation string."""
        authors = self.format_authors_short(entry.get('author', ''))
        title = entry.get('title', '').strip()
        journal = entry.get('journal', '').strip()
        booktitle = entry.get('booktitle', '').strip()
        year = entry.get('year', '').strip()
        volume = entry.get('volume', '').strip()
        number = entry.get('number', '').strip()
        pages = entry.get('pages', '').strip()
        publisher = entry.get('publisher', '').strip()
        
        parts = []
        if authors:
            parts.append(f"{authors}.")
            
        entry_type = entry.get('type', 'article').lower()
        if entry_type in ('article', 'inproceedings', 'phdthesis', 'mastersthesis', 'unpublished'):
            if title:
                parts.append(f'"{title}".')
            if journal:
                parts.append(f'<em>{journal}</em>')
            elif booktitle:
                parts.append(f'in <em>{booktitle}</em>')
        else:
            if title:
                parts.append(f'<em>{title}</em>.')
            if publisher:
                parts.append(publisher)
                
        details = []
        if volume:
            details.append(f"Vol. {volume}")
        if number:
            details.append(f"No. {number}")
        if pages:
            pages_clean = pages.replace('--', '–')
            details.append(f"pp. {pages_clean}")
            
        if details:
            parts.append(", ".join(details))
            
        if year:
            parts.append(f"{year}.")
            
        res = " ".join(parts)
        res = re.sub(r'\.\s*\.', '.', res)
        return res

    def bibliography_html(self, bib_entries: dict, alpha_keys: dict) -> str:
        """Generates the References section HTML list."""
        if not bib_entries:
            return ""
            
        parts = ['<div class="references">', '<h2>References</h2>', '<ul>']
        sorted_entries = sorted(bib_entries.items(), key=lambda item: alpha_keys.get(item[0], item[0]))
        
        for key, entry in sorted_entries:
            alpha = alpha_keys.get(key, key)
            ref_text = self.format_bibliography_entry(entry)
            ref_text = self.replace_inline_math(ref_text)
            ref_text = self.apply_emphasis(ref_text)
            
            badges = []
            if 'pdf' in entry:
                badges.append(f' [<a href="{entry["pdf"]}" target="_blank">PDF</a>]')
            if 'arxiv' in entry:
                arxiv_id = entry['arxiv']
                arxiv_url = arxiv_id if arxiv_id.startswith('http') else f"https://arxiv.org/abs/{arxiv_id}"
                badges.append(f' [<a href="{arxiv_url}" target="_blank">arXiv</a>]')
            if 'doi' in entry:
                doi_id = entry['doi']
                doi_url = doi_id if doi_id.startswith('http') else f"https://doi.org/{doi_id}"
                badges.append(f' [<a href="{doi_url}" target="_blank">DOI</a>]')
            if 'url' in entry and 'pdf' not in entry:
                badges.append(f' [<a href="{entry["url"]}" target="_blank">link</a>]')
                
            badges_html = "".join(badges)
            backlink_html = f' <a href="#cite-ref-{key}-1" class="ref-backref" aria-label="Back to reference">↩</a>'
            
            parts.append(
                f'<li id="cite-{key}">'
                f'<span class="ref-key">[{alpha}]</span>'
                f'<span class="ref-text">{ref_text}{badges_html}{backlink_html}</span>'
                f'</li>'
            )
            
        parts.append('</ul></div>')
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

    def process_image_row(self, text: str) -> str:
        def repl(m):
            block = m.group(1)
            caption = ''
            for line in block.splitlines():
                l = line.strip()
                if l.startswith('caption:'):
                    caption = l.split(':', 1)[1].strip().rstrip(';')
                    break
            block_no_caption = '\n'.join(
                l for l in block.splitlines() if not l.strip().startswith('caption:')
            )
            inner = self.process_image(block_no_caption)
            caption_html = f'<figcaption>{caption}</figcaption>' if caption else ''
            if caption:
                return f'<figure class="mdtx-row-figure"><div class="mdtx-image-row">{inner}</div>{caption_html}</figure>'
            return f'<div class="mdtx-image-row">{inner}</div>'
        return re.sub(r'image-row:\s*\n(.*?)\nend image-row;?', repl, text, flags=re.DOTALL)

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
            
            # If the source starts with research/, posts/, or assets/, ensure it has a leading slash
            for prefix in ['research/', 'posts/', 'assets/']:
                if src.startswith(prefix):
                    src = '/' + src
                    break

            inner_style = f' style="width:{width}"' if width else ''
            img_html = f'<img src="{src}" alt="{alt}">'
            caption_html = f'<figcaption>{caption}</figcaption>' if caption else ''
            return (
                f'<figure class="mdtx-figure">'
                f'<div class="mdtx-figure-inner"{inner_style}>'
                f'{img_html}{caption_html}'
                f'</div>'
                f'</figure>'
            )
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
            body = self.process_table(body)
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

    def process_environments(self, text: str) -> str:
        # Phase 1: Build ID map and assign numbers
        # Only scan numbered environments (not proof)
        numbered_env_names = ['lemma', 'theorem', 'definition', 'remark', 'corollary', 'proposition', 'claim']

        # Find all numbered environments in document order
        # Support syntax: env[id][name]: or env[id]: or env:
        temp_pattern = re.compile(
            rf'(?P<env_name>{"|".join(numbered_env_names)})(?:\[(?P<env_id>.*?)\])?(?:\[(?P<env_name_display>.*?)\])?:\s*\n',
            re.IGNORECASE
        )

        self._env_id_map = {}
        counter = 1
        for match in temp_pattern.finditer(text):
            env_name = match.group('env_name').lower()
            env_id = match.group('env_id')
            if env_id:
                self._env_id_map[env_id] = (env_name, counter)
            counter += 1

        # Phase 2: Process all environments with a single pattern
        all_env_names = ['proof', 'lemma', 'theorem', 'definition', 'remark', 'corollary', 'proposition', 'claim']
        pattern = re.compile(
            rf'(?P<env_name>{"|".join(all_env_names)})(?:\[(?P<env_id>.*?)\])?(?:\[(?P<env_name_display>.*?)\])?:\s*\n'
            r'(?P<body>[\s\S]*?)'
            r'\nend (?P=env_name);?',
            re.DOTALL | re.IGNORECASE
        )

        self._env_counter = 1

        def env_replacer(match):
            env_name = match.group('env_name').lower()
            env_id = match.group('env_id')
            env_name_display = match.group('env_name_display')
            body = match.group('body').strip()

            # Determine number for numbered environments
            number = None
            if env_name in numbered_env_names:
                number = self._env_counter
                self._env_counter += 1

            return self._create_env_replacement(env_name, env_id, env_name_display, body, number)

        text = pattern.sub(env_replacer, text)
        return text

    def _create_env_replacement(self, env_name: str, env_id: str, env_name_display: str, body: str, number: int) -> str:
        """Create HTML for an environment with numbering and linking support"""

        # Save state for recursive processing (in case of nested environments)
        saved_id_map = getattr(self, '_env_id_map', {})
        saved_counter = getattr(self, '_env_counter', 1)

        # Run all processing except paragraphs on the body first
        body = self.apply_emphasis(body)
        body = self.process_inline_code(body)
        body = self.replace_display_math(body)
        body = self.process_code(body)
        body = self.process_image(body)
        body = self.process_example(body)
        body = self.process_env_refs(body)    # resolve lem@id etc. while outer map is live
        body = self.process_environments(body)  # Recursive
        body = self.process_lists(body)
        body = self.process_table(body)
        body = self.process_headings(body)
        body = self.replace_inline_math(body)

        # Restore state after recursive processing
        self._env_id_map = saved_id_map
        self._env_counter = saved_counter

        if env_name == 'proof':
            # Handle proof (not numbered)
            title_text = f'<em>Proof.</em>'

            # Check if env_id is a reference like "thm@my-id"
            if env_id and '@' in env_id:
                ref_display, ref_anchor = self._resolve_proof_reference(env_id)
                if ref_display and ref_anchor:
                    title_text = f'<em>Proof of <a href="#{ref_anchor}">{ref_display}</a>.</em>'
                elif env_id:
                    # Couldn't resolve reference, treat as plain label
                    title_text = f'<em>Proof ({env_id}).</em>'
            elif env_id:
                # Just a label, not a reference
                title_text = f'<em>Proof ({env_id}).</em>'

            body = self.process_paragraphs(body)

            return (
                f'<div class="proof-box {env_name}-box env-box">\n'
                f'  <div class="{env_name}-box-title env-box-title">{title_text}<div class="qed-box"></div></div>\n'
                f'  <div class="{env_name}-box-content env-box-content">{body}</div>\n'
                '</div>'
            )

        # Handle numbered environments (theorem, lemma, etc.)
        anchor_html = f' id="env-{env_id}"' if env_id else ''

        # Build title with number and optional display name
        title_parts = [f'{env_name.capitalize()} {number}']
        if env_name_display:
            title_parts.append(f'({env_name_display})')
        title_text = f'<strong>{" ".join(title_parts)}.</strong> '

        # Process body fully, including paragraphs
        body = self.process_paragraphs(body)

        if body.startswith('<p>'):
            # Inject title into the first paragraph
            body = body.replace('<p>', f'<p>{title_text}', 1)
        else:
            # If the body doesn't start with a paragraph (e.g., a list),
            # put the title in its own paragraph before the content.
            body = f'<p>{title_text}</p>\n{body}' if body else f'<p>{title_text}</p>'

        return (
            f'<div class="{env_name}-box env-box"{anchor_html}>\n'
            f'  {body}\n'
            '</div>'
        )

    def process_env_refs(self, text: str) -> str:
        """Replace inline env references like lem@pair-count-lb with hyperlinks."""
        if not getattr(self, '_env_id_map', None):
            return text

        abbrev_map = {
            'thm': 'theorem', 'theorem': 'theorem',
            'lem': 'lemma', 'lemma': 'lemma',
            'def': 'definition', 'definition': 'definition',
            'rem': 'remark', 'remark': 'remark',
            'cor': 'corollary', 'corollary': 'corollary',
            'prop': 'proposition', 'proposition': 'proposition',
            'claim': 'claim',
        }

        # Sort longest first so e.g. 'theorem' matches before 'thm' doesn't swallow it
        abbrevs = sorted(abbrev_map.keys(), key=len, reverse=True)
        pattern = re.compile(
            r'\b(' + '|'.join(re.escape(a) for a in abbrevs) + r')@([\w-]+)',
            re.IGNORECASE
        )

        def repl(m):
            abbrev = m.group(1).lower()
            env_id = m.group(2)
            env_type = abbrev_map.get(abbrev)
            if env_type and env_id in self._env_id_map:
                stored_type, number = self._env_id_map[env_id]
                if stored_type == env_type:
                    return f'<a href="#env-{env_id}">{env_type.capitalize()} {number}</a>'
            return m.group(0)

        # Only process outside HTML tags to avoid mangling attributes
        parts = re.split(r'(<[^>]*>)', text)
        for i in range(len(parts)):
            if not parts[i].startswith('<'):
                parts[i] = pattern.sub(repl, parts[i])
        return ''.join(parts)

    def _resolve_proof_reference(self, ref: str) -> tuple:
        """Resolve a proof reference like 'thm@my-id' to ('Theorem 3', 'env-my-id')"""
        if '@' not in ref:
            return None, None

        abbrev, env_id = ref.split('@', 1)
        abbrev = abbrev.strip().lower()
        env_id = env_id.strip()

        # Map abbreviations to full names
        abbrev_map = {
            'thm': 'theorem',
            'lem': 'lemma',
            'def': 'definition',
            'rem': 'remark',
            'cor': 'corollary',
            'prop': 'proposition',
            'claim': 'claim',
            # Also support full names
            'theorem': 'theorem',
            'lemma': 'lemma',
            'definition': 'definition',
            'remark': 'remark',
            'corollary': 'corollary',
            'proposition': 'proposition'
        }

        env_type = abbrev_map.get(abbrev)
        if not env_type or env_id not in self._env_id_map:
            return None, None

        stored_type, number = self._env_id_map[env_id]
        if stored_type != env_type:
            return None, None

        return f"{env_type.capitalize()} {number}", f"env-{env_id}"

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
        """Process lists in example boxes, handling both explicit 'end list;' and bare list blocks"""
        pattern = re.compile(
            r'list\[([^\]]+)\]:\s*\n'
            r'((?:[ \t]*-[ \t]*[^\n]*(?:\n[ \t]+[^\n]*)*\n?)*)'
            r'(?:[ \t]*end list;?)?',  # consume optional end list; marker
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

    def _parse_col_spec(self, spec: str) -> list:
        """Parse LaTeX-style column spec like 'l|c|r' or '|l|c|r|'.
        Returns list of dicts with 'align', 'left_border', 'right_border'.
        """
        align_map = {'l': 'left', 'c': 'center', 'r': 'right'}
        tokens = [c for c in spec.strip() if c in 'lcr|']
        cols = []
        for i, tok in enumerate(tokens):
            if tok in 'lcr':
                left_border = (i > 0 and tokens[i-1] == '|')
                # right_border only for trailing | (not followed by another col)
                right_border = (
                    i + 1 < len(tokens) and tokens[i+1] == '|' and
                    (i + 2 >= len(tokens) or tokens[i+2] not in 'lcr')
                )
                cols.append({
                    'align': align_map[tok],
                    'left_border': left_border,
                    'right_border': right_border,
                })
        return cols

    def process_table(self, text: str) -> str:
        pattern = re.compile(
            r'table\[([^\]]+)\](?:\[([^\]]*)\])?:\s*\n'
            r'([\s\S]*?)'
            r'\nend table;?',
            re.DOTALL
        )

        def repl(m):
            col_spec_str = m.group(1).strip()
            caption      = (m.group(2) or '').strip()
            content      = m.group(3)

            cols = self._parse_col_spec(col_spec_str)

            # Parse lines into ('row', [cells]) or ('sep',)
            elements = []
            for line in content.split('\n'):
                stripped = line.strip()
                if not stripped:
                    continue
                if re.match(r'^-{3,}$', stripped):
                    elements.append(('sep',))
                else:
                    cells = [c.strip() for c in stripped.split('|')]
                    elements.append(('row', cells))

            # Rows before first '---' are header; rest are body
            header_rows, body_elements = [], []
            found_sep = False
            for el in elements:
                if not found_sep:
                    if el[0] == 'sep':
                        found_sep = True
                    else:
                        header_rows.append(el[1])
                else:
                    body_elements.append(el)
            if not found_sep:
                body_elements = elements

            def cell_style(col_idx):
                if col_idx >= len(cols):
                    return ''
                col = cols[col_idx]
                styles = [f'text-align: {col["align"]}']
                if col['left_border']:
                    styles.append('border-left: 1px solid #d0d0d0')
                if col['right_border']:
                    styles.append('border-right: 1px solid #d0d0d0')
                return f' style="{"; ".join(styles)}"'

            def render_cell(content, tag, col_idx):
                return f'<{tag}{cell_style(col_idx)}>{content}</{tag}>'

            html = ['<div class="mdtx-table-wrapper"><table class="mdtx-table">']

            if caption:
                html.append(f'<caption>{caption}</caption>')

            if header_rows:
                html.append('<thead>')
                for row in header_rows:
                    html.append('<tr>' + ''.join(render_cell(c, 'th', i) for i, c in enumerate(row)) + '</tr>')
                html.append('</thead>')

            html.append('<tbody>')
            prev_sep = False
            for el in body_elements:
                if el[0] == 'sep':
                    prev_sep = True
                else:
                    row = el[1]
                    row_class = ' class="mdtx-row-sep"' if prev_sep else ''
                    html.append(f'<tr{row_class}>' + ''.join(render_cell(c, 'td', i) for i, c in enumerate(row)) + '</tr>')
                    prev_sep = False
            html.append('</tbody>')
            html.append('</table></div>')
            return '\n'.join(html)

        return pattern.sub(repl, text)

    def replace_display_math(self, text: str) -> str:
        # Find { ... } blocks that span multiple lines and convert them to \begin{equation} ... \end{equation}.
        # Prepend \n so the pattern works even when { appears at the very start of the text.
        text = '\n' + text
        pat = re.compile(
            r'(.*?)\n[ \t]*\{[ \t]*\n'   # content up to newline, then { on its own line
            r'([\s\S]*?)'                  # math content (non-greedy)
            r'\n[ \t]*\}',                 # closing } on its own line
            re.DOTALL
        )
        def sub(m):
            preceding = m.group(1)
            math_content = m.group(2)
            return f"{preceding}\n\\begin{{equation}}\n{math_content}\n\\end{{equation}}"
        result = pat.sub(sub, text)
        # Strip the leading \n we added
        if result.startswith('\n'):
            result = result[1:]
        return result



    def replace_inline_math(self, text: str) -> str:
        # Protect existing math blocks with placeholders before any splitting,
        # so HTML-tag-like content inside equations (e.g. < and > in \cases)
        # doesn't get treated as HTML tags and split the block.
        protected = {}
        _ctr = [0]

        def _protect(m):
            _ctr[0] += 1
            key = f'__MATHBLOCK_{_ctr[0]}__'
            protected[key] = m.group(0)
            return key

        # Protect display math blocks first
        text = re.sub(r'\\begin\{equation\}[\s\S]*?\\end\{equation\}', _protect, text)
        # Protect existing inline math \( ... \)
        text = re.sub(r'\\\([\s\S]*?\\\)', _protect, text)

        def process_math_in_content(content: str) -> str:
            out, i, n = [], 0, len(content)
            while i < n:
                if content[i] == '{':
                    # Find matching closing brace, handling nested braces
                    depth, j = 1, i + 1
                    while j < n and depth > 0:
                        if   content[j] == '{': depth += 1
                        elif content[j] == '}': depth -= 1
                        j += 1
                    if depth == 0:
                        inner = content[i+1:j-1]
                        out.append(f'\\({inner}\\)')
                        i = j
                        continue
                out.append(content[i])
                i += 1
            return ''.join(out)

        # Split by HTML tags and process only non-tag parts.
        # Use <[a-zA-Z/] so LaTeX operators like "< \infty" don't get treated as tag opens.
        parts = re.split(r'(<[a-zA-Z/][^>]*>)', text)
        for i in range(len(parts)):
            if not parts[i].startswith('<'):
                parts[i] = process_math_in_content(parts[i])

        text = ''.join(parts)

        # Restore protected math blocks
        for key, val in protected.items():
            text = text.replace(key, val)

        return text

    def process_abstract(self, text: str) -> str:
        pattern = re.compile(
            r'abstract:\s*\n(?P<body>[\s\S]*?)\nend abstract;?',
            re.IGNORECASE
        )

        def repl(match):
            body = match.group('body').strip()
            prefix_pattern = re.compile(r'^(?:\*\*|<strong>|<b>)?\s*Abstract\b\.?\s*(?:\*\*|</strong>|</b>)?\s*', re.IGNORECASE)
            body_content = prefix_pattern.sub('', body).strip()
            return f'<div class="abstract-text">\n<strong>Abstract.</strong> {body_content}\n</div>'

        return pattern.sub(repl, text)

    def process_main_results(self, text: str) -> str:
        def repl(m):
            items = [l.strip()[1:].strip() for l in m.group(1).splitlines() if l.strip().startswith('-')]
            lis = ''.join(f'<li>{item}</li>' for item in items)
            return f'<div class="main-results"><strong>Main results.</strong><ul>{lis}</ul></div>'
        return re.sub(r'main-results:\s*\n(.*?)\nend main-results;?', repl, text, flags=re.DOTALL)

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
            if not chunk:
                continue  # Skip empty blocks

            # If it's already HTML or a placeholder, keep it as is
            if (chunk.startswith('<') and chunk.endswith('>')) or chunk.startswith('__PROTECTED_BLOCK_'):
                out.append(chunk)
            else:
                # Otherwise, wrap it in a paragraph tag
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
            html_link = f'<a href="{link_url}" target="_blank" rel="noopener noreferrer">{link_text}</a>'
            # Use exact replacement to avoid partial matches
            text = text.replace(placeholder, html_link)
        return text

    def update_research_index(self):
        """Update research/index.html to automatically insert or remove TLDR links based on metadata."""
        pass

    def generate_blog_index(self):
        """Generate the blog index page from all MDTX files"""
        is_tldr = "research" in str(self.source_dir) or "tldr" in str(self.source_dir)
        if is_tldr:
            self.update_research_index()
            return
            
        mdtx_files = list(self.source_dir.glob("*.mdtx"))
        posts = []
        
        for mdtx_file in mdtx_files:
            try:
                raw = mdtx_file.read_text(encoding='utf8')
                raw = self.remove_comments(raw)
                _, body = self.process_requires(raw)
                meta, _ = self.parse_metadata(body)
                
                # Visibility gate: default visible, hide if explicitly set to hidden
                visibility = meta.get('visibility', 'visible').strip().lower()
                if visibility not in ('visible', 'hidden'):
                    visibility = 'visible'
                if visibility == 'hidden':
                    continue
                
                # Skip files that don't have required fields
                if not meta.get('title') or not meta.get('desc'):
                    continue
                
                posts.append({
                    'filename': mdtx_file.stem,
                    'title': meta.get('title', 'Untitled'),
                    'date': meta.get('date', ''),
                    'desc': meta.get('desc', ''),
                    'tags': meta.get('tags', ''),
                    'emoji': meta.get('emoji', '')
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
        tag_order = ['stats', 'physics', 'math', 'ml', 'misc']

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

            # Process title and desc for inline math
            title_processed = self.replace_inline_math(post['title'])
            desc_processed = self.replace_inline_math(post['desc']) if post.get('desc') else ''

            posts_html.append(f'''            <div class="blog-post-item" data-tags="{post['tags']}" data-emoji="{post['emoji']}">
                <span class="post-date">{post['date']}</span>
                <div class="post-content">
                    <h3><a href="/posts/{post['filename']}">{title_processed}</a>{tags_html}</h3>
                    <p class="post-description">{desc_processed}</p>
                </div>
            </div>''')

        posts_section = self.prerender_math('\n'.join(posts_html))

        # Read the current blog index template
        index_path = self.root_dir / "index.html"
        if index_path.exists():
            current_content = index_path.read_text(encoding='utf8')

            # Replace the posts section while preserving tag filters and other content
            import re
            if '<div class="tag-filters">' in current_content:
                # Replace all blog-post-items after tag-filters, before </section>
                # Match: tag-filters div, then any blog-post-items (including none), up to </section>
                pattern = r'(<div class="tag-filters">.*?</div>)\s*(?:<div class="blog-post-item".*?</div>\s*)*(?=\s*</section>)'
                def replacement(m):
                    return m.group(1) + '\n' + posts_section + '\n        '
            else:
                # No tag filters yet, check for <h2>Posts</h2> or <section class="blog-posts">
                if '<h2>Posts</h2>' in current_content:
                    pattern = r'(<h2>Posts</h2>)\s*(.*?)(?=\s*</section>)'
                    tag_filters = '''            <div class="tag-filters">
                <button class="tag-filter active" data-filter="all">all</button>
                <button class="tag-filter" data-filter="stats">stats</button>
                <button class="tag-filter" data-filter="physics">physics</button>
                <button class="tag-filter" data-filter="math">math</button>
                <button class="tag-filter" data-filter="ml">ml</button>
                <button class="tag-filter" data-filter="misc">misc</button>
            </div>
'''
                    def replacement(m):
                        return m.group(1) + '\n' + tag_filters + posts_section + '\n        '
                elif '<section class="blog-posts">' in current_content:
                    # Handle the original structure: <section class="blog-posts"> with tag-filters inside
                    pattern = r'(<section class="blog-posts">\s*<div class="tag-filters">.*?</div>)\s*(?:<div class="blog-post-item".*?</div>\s*)*(?=\s*</section>)'
                    def replacement(m):
                        return m.group(1) + '\n' + posts_section + '\n        '
                else:
                    # Fallback: try to find any section and add content
                    pattern = r'(<section[^>]*>)\s*(.*?)(?=\s*</section>)'
                    tag_filters = '''            <div class="tag-filters">
                <button class="tag-filter active" data-filter="all">all</button>
                <button class="tag-filter" data-filter="stats">stats</button>
                <button class="tag-filter" data-filter="physics">physics</button>
                <button class="tag-filter" data-filter="math">math</button>
                <button class="tag-filter" data-filter="ml">ml</button>
                <button class="tag-filter" data-filter="misc">misc</button>
            </div>
'''
                    def replacement(m):
                        return m.group(1) + '\n' + tag_filters + posts_section + '\n        '

            new_content = re.sub(pattern, replacement, current_content, flags=re.DOTALL)

            # Write the updated index
            index_path.write_text(new_content, encoding='utf8')
            print(f"Updated blog index with {len(posts)} posts")
        else:
            print("Warning: blog/index.html not found")

    def prerender_math(self, html: str) -> str:
        """Replace all LaTeX math blocks with pre-rendered KaTeX HTML."""
        render_script = Path(__file__).resolve().parent / 'render_math.js'

        # Collect (start, end, latex, display) for every math block
        blocks = []
        for m in re.finditer(r'\\\(([\s\S]+?)\\\)', html):
            blocks.append((m.start(), m.end(), m.group(1), False))
        for m in re.finditer(r'\\begin\{equation\}([\s\S]*?)\\end\{equation\}', html):
            blocks.append((m.start(), m.end(), m.group(1), True))

        if not blocks:
            return html

        blocks.sort(key=lambda b: b[0])

        equations = [{'latex': _expand_physics_macros(latex), 'display': display}
                     for _, _, latex, display in blocks]

        proc = subprocess.run(
            ['node', str(render_script)],
            input=json.dumps(equations),
            capture_output=True,
            text=True,
            encoding='utf8',
        )
        if proc.returncode != 0:
            print(f'  [warn] render_math.js failed: {proc.stderr[:300]}', file=sys.stderr)
            return html

        rendered = json.loads(proc.stdout)

        # Substitute in reverse order to keep positions valid
        for (start, end, _, _), katex_html in reversed(list(zip(blocks, rendered))):
            html = html[:start] + katex_html + html[end:]

        return html

    def compile_file(self, path: Path):
        is_tldr = "research" in str(path) or "tldr" in str(path)
        raw  = path.read_text(encoding='utf8')
        
        # Extract ALL URLs IMMEDIATELY after reading, before any processing
        raw, url_map = self.extract_all_urls(raw)
        
        raw  = self.remove_comments(raw)
        reqs, body = self.process_requires(raw)
        meta, body = self.parse_metadata(body)
        
        # Extract bibliography block
        bib_content, body = self.extract_bibliography(body)
        
        # Honor visibility flag when compiling single files; default visible
        visibility = meta.get('visibility', 'visible').strip().lower()
        if visibility not in ('visible', 'hidden'):
            visibility = 'visible'
        fns,  body = self.extract_footnotes(body)
        footnote_numbers = self.build_footnote_numbers(body, fns)
        
        # Parse bibliography entries
        bib_entries = {}
        if 'bib' in meta:
            bib_file = self.source_dir / meta['bib']
            if bib_file.exists():
                try:
                    ext_content = bib_file.read_text(encoding='utf8')
                    bib_entries.update(self.parse_bibtex(ext_content))
                except Exception as e:
                    print(f"Warning: Failed to read external bibliography {meta['bib']}: {e}")
            else:
                print(f"Warning: Bibliography file {meta['bib']} not found in {self.source_dir}")
        if bib_content:
            try:
                bib_entries.update(self.parse_bibtex(bib_content))
            except Exception as e:
                print(f"Warning: Failed to parse embedded bibliography: {e}")
                
        # Resolve alpha keys and handle collisions
        alpha_keys = {}
        if bib_entries:
            temp_alpha_groups = {}
            for key, entry in bib_entries.items():
                base_key = self.generate_alpha_key(entry)
                if base_key not in temp_alpha_groups:
                    temp_alpha_groups[base_key] = []
                temp_alpha_groups[base_key].append(key)
                
            for base_key, keys in temp_alpha_groups.items():
                if len(keys) == 1:
                    alpha_keys[keys[0]] = base_key
                else:
                    sorted_keys = sorted(keys)
                    for idx, key in enumerate(sorted_keys):
                        suffix = chr(ord('a') + idx)
                        alpha_keys[key] = f"{base_key}{suffix}"
        
        # ←── minimal fix: strip any leftover 'desc:' or 'tags:' lines 
        body = re.sub(r'(?m)^(?:desc|tags):.*\n', '', body)

        # now build date + desc blocks from meta, with emphasis and math processing
        date_html = f'            <p class="date">{self.apply_emphasis(meta["date"])}</p>\n' if (not is_tldr and meta.get("date")) else ""
        desc_raw = meta.get("desc", "")
        if desc_raw:
            desc_processed = self.replace_inline_math(desc_raw)
            desc_html = f'            <p class="desc">{self.apply_emphasis(desc_processed)}</p>\n'
        else:
            desc_html = ""

        paper_link = meta.get('paper_link', '').strip()
        if paper_link and desc_html:
            label = 'arXiv' if 'arxiv' in paper_link.lower() else 'paper'
            link_tag = f' <a class="tldr-paper-link" href="{paper_link}" target="_blank" rel="noopener noreferrer">[{label}]</a>'
            desc_html = desc_html.replace('</p>\n', f'{link_tag}</p>\n', 1)
        paper_link_html = ''

        # Process emphasis and inline code first
        body = self.apply_emphasis(body)
        body = self.process_inline_code(body)

        # Process display math BEFORE block-level elements so it's available in example boxes
        body = self.replace_display_math(body)

        # Process all block-level elements first (before paragraphs)
        body = self.process_code(body)
        body = self.process_image_row(body)
        body = self.process_image(body)
        body = self.process_example(body)
        body = self.process_environments(body)
        body = self.process_env_refs(body)    # resolve lem@id, thm@id, etc.
        body = self.process_lists(body)
        body = self.process_table(body)
        body = self.process_headings(body)


        # Process citations
        if bib_entries:
            body = self.process_citations(body, bib_entries, alpha_keys)

        # Process footnotes
        body = self.replace_footrefs(body, fns, footnote_numbers)
        
        # Process abstract
        body = self.process_abstract(body)
        body = self.process_main_results(body)
        
        # Process paragraphs last (after all other blocks are processed)
        body = self.process_paragraphs(body)
        
        # Restore all URLs as HTML links at the very end (skip convert_links entirely)
        body = self.restore_urls_as_html(body, url_map)

        # Process inline math last (after display math and paragraphs)
        body = self.replace_inline_math(body)

        # append footnotes (restore URLs and math here since fn_html is built after body processing)
        fn_html = self.footnotes_html(fns, footnote_numbers, bib_entries, alpha_keys)
        if fn_html:
            fn_html = self.restore_urls_as_html(fn_html, url_map)
            body += "\n" + fn_html

        # append bibliography
        bib_html = self.bibliography_html(bib_entries, alpha_keys)
        if bib_html:
            bib_html = self.restore_urls_as_html(bib_html, url_map)
            body += "\n" + bib_html

        head_reqs = ""  # \require{} directives not needed with KaTeX pre-rendering
        title_raw = meta.get('title','Untitled')
        # HTML title for on-page heading, plain title for the document <title>
        title     = self.replace_inline_math(title_raw)
        doc_title = _plain_title_text(title_raw)
        tags      = meta.get('tags', '')

        # Generate tags HTML for the post
        tags_html = ''
        if not is_tldr and tags and tags.strip():
            tag_order = ['stats', 'physics', 'math', 'ml', 'misc']
            tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
            # Sort tags by canonical order
            tag_list.sort(key=lambda t: tag_order.index(t) if t in tag_order else 999)
            if tag_list:
                tags_html = '<div class="post-tags">' + ''.join([f'<span class="tag" data-tag="{tag}">{tag}</span>' for tag in tag_list]) + '</div>'

        emoji = meta.get('emoji', '')
        if emoji:
            favicon_html = f'    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>{emoji}</text></svg>">\n'
        else:
            favicon_html = ''

        # Get current timestamp for footer
        compile_time = datetime.now().strftime("%b %d, %Y at %H:%M")
        
        # Create output directory structure
        # For file "a.mdtx" -> create "a/index.html"
        output_dir = self.root_dir / path.stem
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / "index.html"

        # Navigation header customization
        if is_tldr:
            header_html = """    <header>
        <div class="monogram"><a href="/">DR</a></div>
        <nav>
            <a href="/research/tldr">TL;DRs</a>
        </nav>
    </header>"""
        else:
            header_html = """    <header>
        <div class="monogram"><a href="/">DR</a></div>
        <nav>
            <a href="/posts">Posts</a>
        </nav>
    </header>"""

        # Determine main wrapper class based on post type
        main_class = "blog-post tldr-post" if is_tldr else "blog-post"

        # Pre-title labels for TLDR pages
        tldr_header_pre = ""

        html = f"""<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <script src="/theme.js"></script>
    <link rel="preconnect" href="https://cdn.jsdelivr.net">
    <link rel="stylesheet" href="/style.css">
    <link rel="stylesheet" href="/posts/posts.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{doc_title}</title>
{favicon_html}</head>

<body>
{header_html}
    <main class="{main_class}">
        <section class="intro">
            {tldr_header_pre}<h1>{title}</h1>
            {tags_html}
{date_html}{desc_html}{paper_link_html}        </section>

{body}
    </main>

    <footer class="footer">
        <div class="last-updated">
            <p>Compiled {compile_time} | <a href="../src/{path.name}" target="_blank">source</a></p>
        </div>
    </footer>

    <script src="/posts/toc-generator.js"></script>
    <script src="/posts/footnote-sidebar.js"></script>
    <script src="/posts/collapsible-proofs.js"></script>
    <script src="/posts/citations.js"></script>
</body>
</html>"""

        html = self.prerender_math(html)
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
