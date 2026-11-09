#!/usr/bin/env python3
"""Build a self-contained HTML version of WEBAPP-TECHNICAL.md with all source
code embedded.

    python3 docs/build_html.py

Output: docs/WEBAPP-TECHNICAL.html  (no external dependencies)
"""
import html
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MD = os.path.join(HERE, "WEBAPP-TECHNICAL.md")
OUT = os.path.join(HERE, "WEBAPP-TECHNICAL.html")

# (path relative to project root, language label)
CODE_FILES = [
    ("webapp/index.html", "html"),
    ("webapp/test.html", "html"),
    ("webapp/manifest.json", "json"),
    ("webapp/sw.js", "javascript"),
    ("webapp/make_icons.py", "python"),
    ("webapp/serve.sh", "bash"),
    ("citinav_landscape.py", "python"),
    ("citinav_send.py", "python"),
    ("citinav.py", "python"),
    ("main.py", "python"),
    ("deploy.sh", "bash"),
    ("st7789py.py", "python"),
]

_toc = []
_slugs = {}


def slug(text):
    s = re.sub(r"[`*_\[\]()]", "", text)
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower() or "section"
    if s in _slugs:
        _slugs[s] += 1
        s = "%s-%d" % (s, _slugs[s])
    else:
        _slugs[s] = 0
    return s


def plain(text):
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text


def inline(text):
    codes = []

    def stash(m):
        codes.append(m.group(1))
        return "\x00%d\x00" % (len(codes) - 1)

    t = re.sub(r"`([^`]+)`", stash, text)
    t = html.escape(t, quote=False)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
               lambda m: '<a href="%s">%s</a>' % (m.group(2), m.group(1)), t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", t)

    def restore(m):
        return "<code>" + html.escape(codes[int(m.group(1))], quote=False) + "</code>"

    return re.sub(r"\x00(\d+)\x00", restore, t)


def indent_of(line):
    return len(line) - len(line.lstrip())


def split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def is_table_sep(line):
    return bool(re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", line)) and "-" in line


def is_block_start(lines, i):
    l = lines[i]
    if l.startswith("```"):
        return True
    if re.match(r"^#{1,6}\s", l):
        return True
    if re.match(r"^\s*([-*]|\d+\.)\s", l):
        return True
    if l.lstrip().startswith(">"):
        return True
    if re.match(r"^(-{3,}|\*{3,}|_{3,})$", l.strip()):
        return True
    if "|" in l and i + 1 < len(lines) and is_table_sep(lines[i + 1]):
        return True
    return False


def render_table(header, rows):
    h = "".join("<th>%s</th>" % inline(c) for c in header)
    body = ""
    for r in rows:
        r = (r + [""] * len(header))[:len(header)]
        body += "<tr>" + "".join("<td>%s</td>" % inline(c) for c in r) + "</tr>"
    return "<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (h, body)


def parse_list(lines, i):
    ordered = bool(re.match(r"^\s*\d+\.\s", lines[i]))
    base = indent_of(lines[i])
    items = []  # [text, [child_html...]]
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            if (i + 1 < n and indent_of(lines[i + 1]) > base
                    and re.match(r"^\s*([-*]|\d+\.)\s", lines[i + 1])):
                i += 1
                continue
            break
        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if not m:
            break
        ind = len(m.group(1))
        if ind < base:
            break
        if ind > base:
            sub, i = parse_list(lines, i)
            if items:
                items[-1][1].append(sub)
            continue
        items.append([m.group(3), []])
        i += 1
        while (i < n and lines[i].strip() and indent_of(lines[i]) > base
               and not re.match(r"^\s*([-*]|\d+\.)\s", lines[i])):
            items[-1][0] += " " + lines[i].strip()
            i += 1
    tag = "ol" if ordered else "ul"
    out = []
    for text, children in items:
        inner = inline(text) + "".join(children)
        out.append("<li>%s</li>" % inner)
    return "<%s>%s</%s>" % (tag, "".join(out), tag), i


def convert(md):
    lines = md.split("\n")
    out = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if line.startswith("```"):
            lang = line[3:].strip()
            i += 1
            buf = []
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append('<pre class="md-code"><code class="lang-%s">%s</code></pre>'
                       % (lang, html.escape("\n".join(buf))))
            continue
        if not line.strip():
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            raw = m.group(2)
            anchor = slug(raw)
            if level in (2, 3):
                _toc.append((level, plain(raw), anchor))
            out.append('<h%d id="%s">%s</h%d>' % (level, anchor, inline(raw), level))
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", line.strip()):
            out.append("<hr>")
            i += 1
            continue
        if line.lstrip().startswith(">"):
            buf = []
            while i < n and lines[i].lstrip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append("<blockquote>%s</blockquote>" % convert("\n".join(buf)))
            continue
        if "|" in line and i + 1 < n and is_table_sep(lines[i + 1]):
            header = split_row(line)
            i += 2
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(split_row(lines[i]))
                i += 1
            out.append(render_table(header, rows))
            continue
        if re.match(r"^\s*([-*]|\d+\.)\s", line):
            block, i = parse_list(lines, i)
            out.append(block)
            continue
        buf = []
        while i < n and lines[i].strip() and not is_block_start(lines, i):
            buf.append(lines[i].strip())
            i += 1
        out.append("<p>%s</p>" % inline(" ".join(buf)))
    return "\n".join(out)


def code_sections():
    parts = []
    for path, lang in CODE_FILES:
        full = os.path.join(ROOT, path)
        with open(full, "r", encoding="utf-8") as f:
            src = f.read()
        size = len(src.encode("utf-8"))
        parts.append(
            '<details class="file" id="file-%s">'
            '<summary><span class="fname">%s</span>'
            '<span class="fmeta">%s · %d bytes</span></summary>'
            '<div class="codewrap"><button class="copy" type="button">copy</button>'
            '<pre><code class="lang-%s">%s</code></pre></div>'
            "</details>"
            % (slug(path), html.escape(path), lang, size, lang, html.escape(src))
        )
    return "\n".join(parts)


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CitiNav — Web App Technical Reference</title>
<style>
  :root{--bg:#1b1b1b;--panel:#242424;--panel2:#2e2e2e;--text:#e6e6e6;--muted:#9a9a9a;
    --green:#00dc50;--yellow:#ffd700;--line:#3a3a3a;--code:#141414;}
  *{box-sizing:border-box}
  html{scroll-behavior:smooth}
  body{margin:0;background:var(--bg);color:var(--text);
    font:16px/1.6 -apple-system,system-ui,Segoe UI,Roboto,sans-serif;}
  a{color:var(--green);text-decoration:none} a:hover{text-decoration:underline}
  .layout{display:flex;max-width:1400px;margin:0 auto}
  nav.toc{position:sticky;top:0;align-self:flex-start;width:290px;height:100vh;overflow:auto;
    padding:22px 16px;border-right:1px solid var(--line);background:var(--panel)}
  nav.toc h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:0 0 10px}
  nav.toc a{display:block;color:var(--text);font-size:13.5px;padding:4px 8px;border-radius:6px}
  nav.toc a.lvl3{padding-left:22px;color:var(--muted);font-size:12.5px}
  nav.toc a:hover{background:var(--panel2);text-decoration:none}
  nav.toc .brand{color:var(--yellow);font-weight:700;font-size:18px;margin-bottom:14px;display:block}
  main{flex:1;min-width:0;padding:34px 44px 120px;max-width:1000px}
  h1{color:var(--yellow);font-size:30px;margin:0 0 6px}
  h2{margin-top:44px;padding-top:10px;border-top:1px solid var(--line);font-size:23px}
  h3{margin-top:28px;font-size:18px;color:#cfcfcf}
  p{margin:12px 0}
  code{background:var(--code);border:1px solid var(--line);border-radius:5px;
    padding:1px 5px;font:13.5px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;color:#d7ffd7}
  pre{margin:14px 0;background:var(--code);border:1px solid var(--line);border-radius:10px;
    padding:14px 16px;overflow:auto}
  pre code{background:none;border:0;padding:0;color:#d7ffd7;font-size:13px;line-height:1.5}
  table{border-collapse:collapse;width:100%;margin:16px 0;font-size:14px}
  th,td{border:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}
  th{background:var(--panel2);color:#fff}
  tr:nth-child(even) td{background:#202020}
  blockquote{margin:16px 0;padding:10px 16px;border-left:3px solid var(--yellow);
    background:#26241a;color:#e8e2c0;border-radius:0 8px 8px 0}
  hr{border:0;border-top:1px solid var(--line);margin:30px 0}
  ul,ol{margin:12px 0;padding-left:24px} li{margin:5px 0}
  .lead{color:var(--muted);font-size:15px}
  .toolbar{display:flex;gap:10px;margin:18px 0 6px;flex-wrap:wrap}
  .toolbar button{font:inherit;font-size:13px;color:var(--text);background:var(--panel2);
    border:1px solid var(--line);border-radius:8px;padding:7px 12px;cursor:pointer}
  .toolbar button:hover{border-color:var(--green)}
  details.file{border:1px solid var(--line);border-radius:10px;margin:12px 0;background:var(--panel)}
  details.file>summary{cursor:pointer;padding:12px 16px;display:flex;justify-content:space-between;
    gap:12px;align-items:center;list-style:none}
  details.file>summary::-webkit-details-marker{display:none}
  details.file>summary::before{content:"▸";color:var(--green);margin-right:8px}
  details.file[open]>summary::before{content:"▾"}
  .fname{font:13.5px ui-monospace,Menlo,monospace;color:var(--yellow)}
  .fmeta{color:var(--muted);font-size:12px;white-space:nowrap}
  .codewrap{position:relative;border-top:1px solid var(--line)}
  .codewrap pre{margin:0;border:0;border-radius:0 0 10px 10px;max-height:70vh}
  .copy{position:absolute;top:8px;right:10px;z-index:2;font:12px inherit;color:var(--text);
    background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:4px 9px;cursor:pointer}
  .copy:hover{border-color:var(--green)}
  @media(max-width:900px){nav.toc{display:none}main{padding:22px 18px 100px}}
</style>
</head>
<body>
<div class="layout">
  <nav class="toc">
    <span class="brand">CitiNav</span>
    <h2>Contents</h2>
    __TOC__
    <h2 style="margin-top:18px">Source code</h2>
    <a href="#source-code">All files</a>
  </nav>
  <main>
    __BODY__
    <h2 id="source-code">Source code</h2>
    <p class="lead">Every project source file, embedded verbatim. (The vendored
    font data modules <code>vga1_8x16.py</code> / <code>vga2_bold_16x32.py</code>
    are omitted for size; they are unchanged third-party assets.)</p>
    <div class="toolbar">
      <button id="expandAll" type="button">Expand all</button>
      <button id="collapseAll" type="button">Collapse all</button>
    </div>
    __CODE__
  </main>
</div>
<script>
  document.querySelectorAll('.copy').forEach(function(btn){
    btn.addEventListener('click', function(){
      var code = btn.parentElement.querySelector('code');
      navigator.clipboard.writeText(code.innerText).then(function(){
        var t = btn.textContent; btn.textContent = 'copied'; 
        setTimeout(function(){ btn.textContent = t; }, 1200);
      });
    });
  });
  document.getElementById('expandAll').addEventListener('click', function(){
    document.querySelectorAll('details.file').forEach(function(d){ d.open = true; });
  });
  document.getElementById('collapseAll').addEventListener('click', function(){
    document.querySelectorAll('details.file').forEach(function(d){ d.open = false; });
  });
</script>
</body>
</html>
"""


def main():
    with open(MD, "r", encoding="utf-8") as f:
        md = f.read()
    body = convert(md)
    toc = "\n".join(
        '<a class="lvl%d" href="#%s">%s</a>' % (lvl, anchor, html.escape(text))
        for lvl, text, anchor in _toc
    )
    doc = (TEMPLATE
           .replace("__TOC__", toc)
           .replace("__BODY__", body)
           .replace("__CODE__", code_sections()))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print("wrote", OUT, "(%d bytes)" % len(doc.encode("utf-8")))


if __name__ == "__main__":
    main()
