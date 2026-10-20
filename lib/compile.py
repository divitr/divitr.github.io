#!/usr/bin/env python3
import os, re, sys, time, subprocess, json, html
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple


def _extract_braced_arg(s: str, i: int):
    if i >= len(s) or s[i] != '{':
        return None, i
    depth, j = 0, i
    while j < len(s):
        if s[j] == '\\' and j + 1 < len(s):
            j += 2
            continue
        if s[j] == '{':
            depth += 1
        elif s[j] == '}':
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return None, i


def _expand_physics_macros(latex: str) -> str:
    result = []
    i, n = 0, len(latex)

    def skip_spaces(pos):
        while pos < n and latex[pos] in ' \t\n':
            pos += 1
        return pos

    while i < n:
        if latex[i] == '\\' and i + 1 < n:
            if latex[i + 1].isalpha():
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
                            result.append(f'\\frac{{\\partial {arg1}}}{{\\partial {arg2}}}')
                            i = k2
                        else:
                            result.append(f'\\frac{{\\partial}}{{\\partial {arg1}}}')
                            i = k
                        continue

                result.append(cmd)
                i = j
                continue
            else:
                result.append(latex[i:i + 2])
                i += 2
                continue

        result.append(latex[i])
        i += 1

    return ''.join(result)


def _plain_title_text(text: str) -> str:
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
        self.source_dir = Path(source_dir).resolve()
        self.root_dir = self.source_dir.parent
        self._mtimes  = {}
        self._heading_slugs = {}
        self._missing_cites = []
        self.problems = []

    def scan(self) -> List[Path]:
        return list(self.source_dir.glob("*.mdtx"))

    def changed(self, p: Path) -> bool:
        m, k = p.stat().st_mtime, str(p)
        if k not in self._mtimes or m > self._mtimes[k]:
            self._mtimes[k] = m
            return True
        return False

    def remove_comments(self, text: str) -> str:
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
        parts = text.split('\n\n', 1)
        meta_block = parts[0]
        body       = parts[1] if len(parts) > 1 else ''
        
        meta = {}
        for line in meta_block.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.endswith(';'):
                line = line[:-1].strip()
            if ':' not in line:
                continue
            k, v = line.split(':', 1)
            meta[k.strip()] = v.strip()
        
        if 'emoji' not in meta:
            meta['emoji'] = ''
        
        return meta, body

    def apply_emphasis(self, text: str) -> str:
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        return text

    def process_inline_code(self, text: str) -> str:
        def repl(m):
            code = m.group(1)
            code = code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            return f'<code>{code}</code>'
        return re.sub(r'`([^`\n]+)`', repl, text)

    def apply_typography(self, text: str) -> str:
        protected = {}
        counter = 0

        def protect(m):
            nonlocal counter
            key = f'__TYPOGRAPHY_PROTECTED_{counter}__'
            protected[key] = m.group(0)
            counter += 1
            return key

        protected_pattern = re.compile(
            r'<pre[\s\S]*?</pre>'
            r'|<code[\s\S]*?</code>'
            r'|<script[\s\S]*?</script>'
            r'|<style[\s\S]*?</style>'
            r'|\\begin\{equation\}[\s\S]*?\\end\{equation\}'
            r'|\\\([\s\S]*?\\\)',
            re.IGNORECASE
        )
        text = protected_pattern.sub(protect, text)

        parts = re.split(r'(<[^>]*>)', text)
        for i, part in enumerate(parts):
            if part.startswith('<'):
                continue
            parts[i] = re.sub(r'(?<!-)--(?!-)', '&mdash;', part)

        text = ''.join(parts)
        for key, value in protected.items():
            text = text.replace(key, value)
        return text

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
        bib_match = re.search(r'bibliography:\s*(.*?)\s*end bibliography;?', text, re.DOTALL)
        if bib_match:
            bib_content = bib_match.group(1)
            clean_text = text[:bib_match.start()] + text[bib_match.end():]
            return bib_content, clean_text
        return "", text

    def _clean_latex_accents(self, text: str) -> str:
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
            
        text = re.sub(r'\{\\([`\'"~^Hc])([a-zA-Z])\}', repl_braced, text)
        text = re.sub(r'\\([`\'"~^Hc])\{([a-zA-Z])\}', repl_braced, text)
        text = re.sub(r'\\([`\'"~^Hc])([a-zA-Z])', repl_braced, text)
        
        return text

    def parse_bibtex(self, bib_text: str) -> Dict[str, Dict[str, str]]:
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
        citation_instances = {}
        
        pattern_multiple = re.compile(r'\brefs@([\w\-]+(?:\s*,\s*[\w\-]+)*)', re.IGNORECASE)
        pattern_single = re.compile(r'\bref@([\w\-]+)', re.IGNORECASE)
        
        def repl_multiple(match):
            raw_keys = match.group(1)
            keys = [k.strip() for k in raw_keys.split(',')]
            
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
                    self._missing_cites.append(key)
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
        if not bib_entries:
            return ""
            
        parts = [
            '<div class="references">',
            '<h2 id="references">References'
            '<a class="heading-anchor" href="#references" '
            'aria-label="Permalink to this section">#</a></h2>',
            '<ul>',
        ]
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
        def repl(m):
            lang, code = m.group(1), m.group(2)
            code = code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            return f'<pre><code class="language-{lang}">{code}</code></pre>'
        
        pattern = re.compile(
            r'code\[([^\]]+)\]:\s*\n'
            r'([\s\S]*?)'
            r'\nend code;?',
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

            for prefix in ['research/', 'assets/']:
                if src.startswith(prefix):
                    src = '/' + src
                    break

            inner_style = f' style="width:{width}"' if width else ''
            img_html = f'<img loading="lazy" decoding="async" src="{src}" alt="{alt}">'
            caption_html = f'<figcaption>{caption}</figcaption>' if caption else ''
            return (
                f'<figure class="mdtx-figure">'
                f'<div class="mdtx-figure-inner"{inner_style}>'
                f'{img_html}{caption_html}'
                f'</div>'
                f'</figure>'
            )
        return re.sub(r'image:\s*\n(.*?)\nend image;?', repl, text, flags=re.DOTALL)

    def process_example(self, text: str) -> str:
        pattern = re.compile(
            r'example:\s*\n'
            r'([\s\S]*?)'
            r'\nend example;?',
            re.DOTALL
        )
        def repl(m):
            block   = m.group(1)
            t_m     = re.search(r'title:\s*(.+?)(?:;|\n)',      block)
            title   = t_m.group(1).strip()   if t_m   else ''
            
            content_start = block.find('content: {')
            if content_start != -1:
                content_start += len('content: {')
                brace_count = 1
                content_end = content_start
                
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
                content_start = block.find('content: \\begin{equation}')
                if content_start != -1:
                    content_start += len('content: \\begin{equation}')
                    content_end = block.find('\\end{equation}', content_start)
                    if content_end != -1:
                        body = block[content_start:content_end].strip()
                    else:
                        body = ''
                else:
                    body = ''
            
            body = self.replace_display_math(body)
            body = self.replace_inline_math(body)
            body = self.process_image(body)
            body = self.process_table(body)
            body = self.process_lists_in_example(body)
            body = self.apply_emphasis(body)
            
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
        numbered_env_names = ['lemma', 'theorem', 'definition', 'remark', 'corollary', 'proposition', 'claim']

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

            number = None
            if env_name in numbered_env_names:
                number = self._env_counter
                self._env_counter += 1

            return self._create_env_replacement(env_name, env_id, env_name_display, body, number)

        text = pattern.sub(env_replacer, text)
        return text

    def _create_env_replacement(self, env_name: str, env_id: str, env_name_display: str, body: str, number: int) -> str:
        saved_id_map = getattr(self, '_env_id_map', {})
        saved_counter = getattr(self, '_env_counter', 1)

        body = self.apply_emphasis(body)
        body = self.process_inline_code(body)
        body = self.replace_display_math(body)
        body = self.process_code(body)
        body = self.process_image(body)
        body = self.process_example(body)
        body = self.process_env_refs(body)
        body = self.process_environments(body)
        body = self.process_lists(body)
        body = self.process_table(body)
        body = self.process_headings(body)
        body = self.replace_inline_math(body)

        self._env_id_map = saved_id_map
        self._env_counter = saved_counter

        if env_name == 'proof':
            title_text = f'<em>Proof.</em>'

            if env_id and '@' in env_id:
                ref_display, ref_anchor = self._resolve_proof_reference(env_id)
                if ref_display and ref_anchor:
                    title_text = f'<em>Proof of <a href="#{ref_anchor}">{ref_display}</a>.</em>'
                elif env_id:
                    title_text = f'<em>Proof ({env_id}).</em>'
            elif env_id:
                title_text = f'<em>Proof ({env_id}).</em>'

            body = self.process_paragraphs(body)

            return (
                f'<div class="proof-box {env_name}-box env-box">\n'
                f'  <div class="{env_name}-box-title env-box-title">{title_text}<div class="qed-box"></div></div>\n'
                f'  <div class="{env_name}-box-content env-box-content">{body}</div>\n'
                '</div>'
            )

        anchor_html = f' id="env-{env_id}"' if env_id else ''

        title_parts = [f'{env_name.capitalize()} {number}']
        if env_name_display:
            title_parts.append(f'({env_name_display})')
        title_text = f'<strong>{" ".join(title_parts)}.</strong> '

        body = self.process_paragraphs(body)

        if body.startswith('<p>'):
            body = body.replace('<p>', f'<p>{title_text}', 1)
        else:
            body = f'<p>{title_text}</p>\n{body}' if body else f'<p>{title_text}</p>'

        return (
            f'<div class="{env_name}-box env-box"{anchor_html}>\n'
            f'  {body}\n'
            '</div>'
        )

    def process_env_refs(self, text: str) -> str:
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

        parts = re.split(r'(<[^>]*>)', text)
        for i in range(len(parts)):
            if not parts[i].startswith('<'):
                parts[i] = pattern.sub(repl, parts[i])
        return ''.join(parts)

    def _resolve_proof_reference(self, ref: str) -> tuple:
        if '@' not in ref:
            return None, None

        abbrev, env_id = ref.split('@', 1)
        abbrev = abbrev.strip().lower()
        env_id = env_id.strip()

        abbrev_map = {
            'thm': 'theorem',
            'lem': 'lemma',
            'def': 'definition',
            'rem': 'remark',
            'cor': 'corollary',
            'prop': 'proposition',
            'claim': 'claim',
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
        pattern_with_end = re.compile(
            r'list\[([^\]]+)\]:\s*\n'
            r'((?:\s*-\s*[^\n]*\n(?:[^\n]*\n)*?)+)'
            r'\s*end list;?',
            re.DOTALL
        )

        pattern_without_end = re.compile(
            r'list\[([^\]]+)\]:\s*\n'
            r'((?:[ \t]*-[ \t]*[^\n]*(?:\n[ \t]+[^\n]*)*\n?)+)',
            re.DOTALL
        )
        def repl(m):
            list_type = m.group(1)
            content = m.group(2)

            def parse_nested_list(lines):
                items = []
                i = 0
                while i < len(lines):
                    line = lines[i]
                    if not line.strip():
                        i += 1
                        continue

                    if line.strip().startswith('- '):
                        item_text = line.strip()[2:].strip()
                        sub_items = []

                        j = i + 1
                        while j < len(lines):
                            next_line = lines[j]
                            if not next_line.strip():
                                j += 1
                                continue

                            current_indent = len(line) - len(line.lstrip())
                            next_indent = len(next_line) - len(next_line.lstrip())

                            if next_indent > current_indent and next_line.strip().startswith('- '):
                                nested_text = next_line.strip()[2:].strip()
                                nested_sub_items = []

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
                                break
                            else:
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

        text = pattern_with_end.sub(repl, text)
        text = pattern_without_end.sub(repl, text)
        return text

    def process_lists_in_example(self, text: str) -> str:
        pattern = re.compile(
            r'list\[([^\]]+)\]:\s*\n'
            r'((?:[ \t]*-[ \t]*[^\n]*(?:\n[ \t]+[^\n]*)*\n?)*)'
            r'(?:[ \t]*end list;?)?',
            re.DOTALL
        )
        def repl(m):
            list_type = m.group(1)
            content = m.group(2)
            
            def parse_list_items(text_content):
                lines = text_content.splitlines()
                items = []
                i = 0
                
                while i < len(lines):
                    line = lines[i]
                    if not line.strip():
                        i += 1
                        continue
                    
                    if line.strip().startswith('- '):
                        base_indent = len(line) - len(line.lstrip())
                        item_content = [line.strip()[2:].strip()]
                        
                        j = i + 1
                        sub_items = []
                        
                        while j < len(lines):
                            next_line = lines[j]
                            
                            if not next_line.strip():
                                j += 1
                                continue
                            
                            next_indent = len(next_line) - len(next_line.lstrip())
                            
                            if next_indent <= base_indent and next_line.strip().startswith('- '):
                                break
                            
                            if next_indent > base_indent and next_line.strip().startswith('- '):
                                sub_item_text = next_line.strip()[2:].strip()
                                sub_items.append(f'<li>{self.apply_emphasis(sub_item_text)}</li>')
                                j += 1
                            elif next_indent > base_indent:
                                item_content.append(next_line.strip())
                                j += 1
                            else:
                                break
                        
                        full_item = " ".join(filter(None, item_content))
                        if sub_items:
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
        align_map = {'l': 'left', 'c': 'center', 'r': 'right'}
        tokens = [c for c in spec.strip() if c in 'lcr|']
        cols = []
        for i, tok in enumerate(tokens):
            if tok in 'lcr':
                left_border = (i > 0 and tokens[i-1] == '|')
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
        text = '\n' + text
        pat = re.compile(
            r'(.*?)\n[ \t]*\{[ \t]*\n'
            r'([\s\S]*?)'
            r'\n[ \t]*\}',
            re.DOTALL
        )
        def sub(m):
            preceding = m.group(1)
            math_content = m.group(2)
            return f"{preceding}\n\\begin{{equation}}\n{math_content}\n\\end{{equation}}"
        result = pat.sub(sub, text)
        if result.startswith('\n'):
            result = result[1:]
        return result



    def replace_inline_math(self, text: str) -> str:
        protected = {}
        _ctr = [0]

        def _protect(m):
            _ctr[0] += 1
            key = f'__MATHBLOCK_{_ctr[0]}__'
            protected[key] = m.group(0)
            return key

        text = re.sub(r'\\begin\{equation\}[\s\S]*?\\end\{equation\}', _protect, text)
        text = re.sub(r'\\\([\s\S]*?\\\)', _protect, text)

        def process_math_in_content(content: str) -> str:
            out, i, n = [], 0, len(content)
            while i < n:
                if content[i] == '{':
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

        parts = re.split(r'(<[a-zA-Z/][^>]*>)', text)
        for i in range(len(parts)):
            if not parts[i].startswith('<'):
                parts[i] = process_math_in_content(parts[i])

        text = ''.join(parts)

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

    _SLUG_TEX_NOISE = re.compile(
        r'\\(?:mathcal|mathbb|mathbf|mathrm|mathsf|mathfrak|boldsymbol|operatorname'
        r'|text(?:rm|bf|it)?|displaystyle|left|right|bigg?l?|quad|qquad)\b'
    )

    def slugify_heading(self, text: str) -> str:
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'__URL_PLACEHOLDER_\d+__', '', text)
        text = re.sub(r'\bref@\S+', '', text)
        text = self._SLUG_TEX_NOISE.sub('', text)
        text = text.replace('^', '')
        text = text.replace('\\', '')
        text = re.sub(r'[^A-Za-z0-9]+', '-', text)
        return text.strip('-').lower() or 'section'

    def unique_slug(self, base: str) -> str:
        count = self._heading_slugs.get(base, 0) + 1
        self._heading_slugs[base] = count
        return base if count == 1 else f'{base}-{count}'

    def process_headings(self, text: str) -> str:
        out = []
        for L in text.splitlines():
            if L.startswith('#'):
                lvl = min(len(L) - len(L.lstrip('#')), 6)
                content = L.lstrip('#').strip()
                override = re.search(r'\s*\{#([A-Za-z][\w-]*)\}\s*$', content)
                if override:
                    content = content[:override.start()].rstrip()
                    slug = self.unique_slug(override.group(1).lower())
                else:
                    slug = self.unique_slug(self.slugify_heading(content))
                if 2 <= lvl <= 4:
                    out.append(
                        f'<h{lvl} id="{slug}">{content}'
                        f'<a class="heading-anchor" href="#{slug}" '
                        f'aria-label="Permalink to this section">#</a></h{lvl}>'
                    )
                else:
                    out.append(f'<h{lvl}>{content}</h{lvl}>')
            else:
                out.append(L)
        return "\n".join(out)

    def process_paragraphs(self, text: str) -> str:
        protected_blocks = {}
        placeholder_counter = 0
        
        for tag in ['pre', 'div', 'ol', 'ul']:
            pattern = re.compile(f'<{tag}[^>]*>.*?</{tag}>', re.DOTALL)
            def protect_block(m):
                nonlocal placeholder_counter
                placeholder = f'__PROTECTED_BLOCK_{placeholder_counter}__'
                protected_blocks[placeholder] = m.group(0)
                placeholder_counter += 1
                return placeholder
            text = pattern.sub(protect_block, text)
        
        blocks = re.split(r'\n\s*\n', text.strip())
        out    = []
        for blk in blocks:
            chunk = blk.strip()
            if not chunk:
                continue

            if (chunk.startswith('<') and chunk.endswith('>')) or chunk.startswith('__PROTECTED_BLOCK_'):
                out.append(chunk)
            else:
                line = ' '.join(l.strip() for l in blk.splitlines())
                if line:
                    line = self.apply_emphasis(line)
                    out.append(f'<p>{line}</p>')
        
        result = "\n".join(out)
        for placeholder, original in protected_blocks.items():
            result = result.replace(placeholder, original)
        
        return result


    
    def extract_all_urls(self, text: str) -> tuple[str, dict[str, tuple[str, str]]]:
        url_map = {}
        url_counter = 0
        
        def replace_url(match):
            nonlocal url_counter
            url_counter += 1
            placeholder = f'__URL_PLACEHOLDER_{url_counter}__'
            link_text = match.group(1)
            link_url = match.group(2)
            url_map[placeholder] = (link_text, link_url)
            return placeholder
        
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', replace_url, text, flags=re.DOTALL)
        
        return text, url_map
    
    def restore_urls_as_html(self, text: str, url_map: dict[str, tuple[str, str]]) -> str:
        sorted_items = sorted(url_map.items(), key=lambda x: int(x[0].split('_')[-2]) if x[0].split('_')[-2].isdigit() else 0, reverse=True)
        
        for placeholder, (link_text, link_url) in sorted_items:
            link_url = re.sub(r'\s+', '', link_url.strip())
            html_link = f'<a href="{link_url}" target="_blank" rel="noopener noreferrer">{link_text}</a>'
            text = text.replace(placeholder, html_link)
        return text

    def update_research_index(self):
        mdtx_files = list(self.source_dir.glob("*.mdtx"))
        tldrs = []
        
        for mdtx_file in mdtx_files:
            try:
                raw = mdtx_file.read_text(encoding='utf8')
                raw = self.remove_comments(raw)
                _, body = self.process_requires(raw)
                meta, _ = self.parse_metadata(body)
                
                visibility = meta.get('visibility', 'visible').strip().lower()
                if visibility == 'hidden':
                    continue
                
                if not meta.get('title') or not meta.get('desc'):
                    continue

                tldrs.append({
                    'filename': mdtx_file.stem,
                    'title': meta.get('title', 'Untitled'),
                    'date': meta.get('date', ''),
                    'desc': meta.get('desc', ''),
                    'emoji': meta.get('emoji', '📄'),
                    'paper_link': meta.get('paper_link', '')
                })
            except Exception as e:
                print(f"Warning: Could not parse {mdtx_file.name}: {e}")
                continue

        def sort_key(tldr):
            date_str = tldr['date'].strip()
            if date_str == '[In Progress]':
                return datetime(1800, 1, 1)
            
            patterns = [
                r'(\w+) (\d+), (\d+)',
                r'(\w+)\.? (\d+), (\d+)',
                r'(\w+) (\d+) (\d+)'
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
            return datetime(1900, 1, 1)
            
        tldrs.sort(key=sort_key, reverse=True)
        
        tldrs_html = []
        for tldr in tldrs:
            title_processed = self.replace_inline_math(tldr['title'])
            desc_processed = self.replace_inline_math(tldr['desc']) if tldr.get('desc') else ''
            
            paper_html = ''
            if tldr.get('paper_link'):
                label = 'arXiv' if 'arxiv.org' in tldr['paper_link'].lower() else 'paper'
                paper_html = f' <span class="post-arxiv">[<a href="{tldr["paper_link"]}" target="_blank" rel="noopener noreferrer">{label}</a>]</span>'
            
            tldrs_html.append(f'''            <div class="blog-post-item" data-emoji="{tldr['emoji']}">
                <span class="post-date">{tldr['emoji']}</span>
                <div class="post-content">
                    <h3><a href="/research/tldr/{tldr['filename']}/">{title_processed}</a>{paper_html}</h3>
                    <p class="post-description">{desc_processed}</p>
                </div>
            </div>''')
            
        tldrs_section = self.prerender_math('\n'.join(tldrs_html))
        
        index_path = self.root_dir / "index.html"
        if index_path.exists():
            current_content = index_path.read_text(encoding='utf8')
            
            pattern = r'(<section class="blog-posts">)\s*(?:<div class="blog-post-item".*?</div>\s*)*(?=\s*</section>)'
            def replacement(m):
                return m.group(1) + '\n' + tldrs_section + '\n        '
                
            new_content = re.sub(pattern, replacement, current_content, flags=re.DOTALL)
            index_path.write_text(new_content, encoding='utf8')
            print(f"Updated TL;DR index with {len(tldrs)} writeups")
        else:
            print(f"Warning: TL;DR index not found at {index_path}")

    def prerender_math(self, html: str) -> str:
        render_script = Path(__file__).resolve().parent / 'render_math.js'

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

        for (start, end, _, _), katex_html in reversed(list(zip(blocks, rendered))):
            html = html[:start] + katex_html + html[end:]

        return html

    def check_output(self, page: str, output_file: Path) -> List[str]:
        problems = []
        text = re.sub(r'<(code|pre|math|script|style)\b[\s\S]*?</\1>', '', page)
        text = re.sub(r'<span [^>]*color:#cc0000;[^>]*>[^<]*</span>', '', text)
        text = re.sub(r'<[^>]+>', '', text)

        for m in re.finditer(r'\brefs?@[\w\-]+(?:\s*,\s*[\w\-]+)*', text):
            problems.append(f"unresolved citation {m.group(0)}")
        for key in self._missing_cites:
            problems.append(f"unknown citation key {key}")
        for key in re.findall(r'<li id="cite-([^"]+)">', page):
            if f'id="cite-ref-{key}-1"' not in page:
                problems.append(f"bibliography entry {key} is never cited")

        for label in re.findall(r'\[\^([^\]]+)\]', text):
            problems.append(f"footnote [^{label}] has no definition")
        for number, body in re.findall(r'<li id="fn(\d+)">([\s\S]*?)</li>', page):
            if f'id="fnref{number}"' not in page:
                body = re.sub(r'<a [^>]*class="footnote-backref"[\s\S]*?</a>', '', body)
                snippet = html.unescape(re.sub(r'<[^>]+>', '', body)).strip()[:50]
                problems.append(f'footnote "{snippet}..." is never referenced')

        for tag in re.findall(r'<span class="katex-error"[^>]*>', page):
            title = re.search(r'title="([^"]*)"', tag)
            problems.append(f"math error: {html.unescape(title.group(1)) if title else tag}")
        for command in re.findall(r'<mstyle mathcolor="#cc0000"><mtext>([^<]*)</mtext>', page):
            problems.append(f"unknown LaTeX command {html.unescape(command)}")
        if 'class="math-error"' in page or re.search(r'\\\(|\\begin\{equation\}', text):
            problems.append("math was not rendered (check node and lib/node_modules)")
        else:
            for m in re.finditer(r'\\[a-zA-Z]+', html.unescape(text)):
                context = html.unescape(text)[max(0, m.start() - 20):m.end() + 20].replace('\n', ' ')
                problems.append(f'raw LaTeX outside math: "...{context}..."')

        site_root = Path(__file__).resolve().parent.parent
        for src in re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', page):
            if re.match(r'(https?:|data:|//)', src):
                continue
            target = site_root / src.lstrip('/') if src.startswith('/') else output_file.parent / src
            if not target.exists():
                problems.append(f"image not found: {src}")

        return list(dict.fromkeys(problems))

    def exit_status(self) -> int:
        if self.problems:
            print(f"{len(self.problems)} problem(s) found")
            return 1
        return 0

    def compile_file(self, path: Path):
        raw  = path.read_text(encoding='utf8')
        self._heading_slugs = {}
        self._missing_cites = []
        
        raw, url_map = self.extract_all_urls(raw)
        
        raw  = self.remove_comments(raw)
        _, body = self.process_requires(raw)
        meta, body = self.parse_metadata(body)

        bib_content, body = self.extract_bibliography(body)

        fns,  body = self.extract_footnotes(body)
        footnote_numbers = self.build_footnote_numbers(body, fns)
        
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

        body = self.apply_emphasis(body)
        body = self.process_inline_code(body)

        body = self.replace_display_math(body)

        body = self.process_code(body)
        body = self.process_image_row(body)
        body = self.process_image(body)
        body = self.process_example(body)
        body = self.process_environments(body)
        body = self.process_env_refs(body)
        body = self.process_lists(body)
        body = self.process_table(body)
        body = self.process_headings(body)


        if bib_entries:
            body = self.process_citations(body, bib_entries, alpha_keys)

        body = self.replace_footrefs(body, fns, footnote_numbers)
        
        body = self.process_abstract(body)
        body = self.process_main_results(body)
        
        body = self.process_paragraphs(body)
        
        body = self.restore_urls_as_html(body, url_map)

        body = self.replace_inline_math(body)

        fn_html = self.footnotes_html(fns, footnote_numbers, bib_entries, alpha_keys)
        if fn_html:
            fn_html = self.restore_urls_as_html(fn_html, url_map)
            body += "\n" + fn_html

        bib_html = self.bibliography_html(bib_entries, alpha_keys)
        if bib_html:
            bib_html = self.restore_urls_as_html(bib_html, url_map)
            body += "\n" + bib_html

        title_raw = meta.get('title','Untitled')
        title     = self.replace_inline_math(title_raw)
        doc_title = _plain_title_text(title_raw)

        emoji = meta.get('emoji', '')
        if emoji:
            favicon_html = f'    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>{emoji}</text></svg>">\n'
        else:
            favicon_html = ''

        compile_time = datetime.now().strftime("%b %d, %Y at %H:%M")
        
        output_dir = self.root_dir / path.stem
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / "index.html"

        html = f"""<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <script src="/theme.js"></script>
    <link rel="preconnect" href="https://cdn.jsdelivr.net">
    <link rel="stylesheet" href="/style.css">
    <link rel="stylesheet" href="/lib/mdtx.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.40/dist/katex.min.css">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{doc_title}</title>
{favicon_html}</head>

<body>
    <header>
        <div class="monogram"><a href="/">DR</a></div>
        <nav>
            <a href="/research/tldr">TLDRs</a>
        </nav>
    </header>
    <main class="blog-post tldr-post">
        <section class="intro">
            <h1>{title}</h1>
{desc_html}            <p class="tldr-series-note">(Part of a <a href="/research/tldr/">series</a> of short writeups covering recent work.)</p>
        </section>

{body}
    </main>

    <footer class="footer">
        <div class="last-updated">
            <p>compiled {compile_time} | <a href="../src/{path.name}" target="_blank">source</a></p>
        </div>
    </footer>

    <script src="/lib/toc-generator.js"></script>
    <script src="/lib/footnote-sidebar.js"></script>
    <script src="/lib/collapsible-proofs.js"></script>
    <script src="/lib/citations.js"></script>
</body>
</html>"""

        html = self.apply_typography(html)
        html = self.prerender_math(html)
        output_file.write_text(html, encoding='utf8')
        print("Compiled →", path.name, "→", output_file.relative_to(self.root_dir))
        for problem in self.check_output(html, output_file):
            print(f"  [problem] {path.name}: {problem}")
            self.problems.append(f"{path.name}: {problem}")

    def watch(self):
        print(f"Watching {self.source_dir} …")
        try:
            while True:
                files_changed = []
                for f in self.scan():
                    if self.changed(f):
                        self.compile_file(f)
                        files_changed.append(f)
                
                if files_changed:
                    self.update_research_index()
                    
                time.sleep(1)
        except KeyboardInterrupt:
            print("Stopped.")

if __name__=="__main__":
    once = "--once" in sys.argv[1:]
    args = [a for a in sys.argv[1:] if a != "--once"]

    if len(args) < 1:
        print("Usage: python3 -m compile [--once] <src_dir> OR python3 -m compile [--once] <file.mdtx> OR python3 -m compile --index <src_dir>")
        sys.exit(1)

    if args[0] == "--index":
        if len(args) != 2:
            print("Usage: python3 -m compile --index <src_dir>")
            sys.exit(1)
        source_dir = args[1]
        if not os.path.isdir(source_dir):
            print(f"Error: {source_dir} is not a directory")
            sys.exit(1)
        compiler = MDTXCompiler(source_dir)
        compiler.update_research_index()
        sys.exit(0)
    
    path_arg = args[0]

    if path_arg.endswith('.mdtx'):
        file_path = Path(path_arg)
        if not file_path.exists():
            print(f"Error: File {file_path} not found")
            sys.exit(1)
        
        source_dir = file_path.parent
        compiler = MDTXCompiler(source_dir)
        
        print(f"Compiling {file_path.name}...")
        compiler.compile_file(file_path)
        
        compiler.update_research_index()

        if once:
            sys.exit(compiler.exit_status())

        print(f"Watching {file_path.name} for changes...")
        try:
            while True:
                if compiler.changed(file_path):
                    print(f"Changes detected in {file_path.name}, recompiling...")
                    compiler.compile_file(file_path)
                    compiler.update_research_index()
                time.sleep(1)
        except KeyboardInterrupt:
            print("Stopped.")
            
    else:
        if not os.path.isdir(path_arg):
            print(f"Error: {path_arg} is not a directory")
            sys.exit(1)
        compiler = MDTXCompiler(path_arg)
        if once:
            for f in sorted(compiler.scan()):
                compiler.compile_file(f)
            compiler.update_research_index()
            sys.exit(compiler.exit_status())
        compiler.update_research_index()
        compiler.watch()
