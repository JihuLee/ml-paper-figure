#!/usr/bin/env python3
"""tex_math.py - real LaTeX math for hand-written SVG figures.

Every $...$ segment inside a <text> is typeset by LaTeX in the paper's own math setup. The rest of the line stays in
the figure's sans font. render_svg.py calls this module automatically; the CLI is for inspecting the setup.

  python tex_math.py --check-env                   which TeX tools are installed
  python tex_math.py --paper main.tex --show       the preamble a figure for this paper would use
  python tex_math.py --paper main.tex --math newtx --show

Pipeline per snippet (one latex run and one pdflatex run for all snippets of a figure)
  latex    -> DVI -> dvisvgm --no-fonts : glyph outlines for the SVG, the PNG previews and the lint
  pdflatex -> one cropped PDF page each : real Type 1 math fonts (CMMI6, CMR5, ...) stamped onto the exported PDF
Box metrics (width, height, depth) come from TeX itself, so the math sits on the baseline of the surrounding text.

Sizes: a snippet is compiled at the printed size of its <text> (font-size in user units x printed pt per unit), so
LaTeX picks the matching design sizes (cmmi6 at 6pt) and the LaTeX script sizes (\\DeclareMathSizes: 6pt -> 5pt).
"""
from __future__ import annotations

import argparse
import hashlib
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# LaTeX defaults (fontmath.ltx): text size -> (script, scriptscript)
LATEX_MATH_SIZES = {5: (5, 5), 6: (5, 5), 7: (5, 5), 8: (6, 5), 9: (6, 5), 10: (7, 5), 10.95: (8, 6), 12: (9, 7),
                    14.4: (10.95, 8), 17.28: (12, 10), 20.74: (14.4, 12), 24.88: (20.74, 17.28)}
MIN_SCRIPT_PT = 5.0

# Math font setups. Keys are accepted by --math; anything containing a backslash is used verbatim.
MATH_SETUPS = {
    "cm": "",                                    # Computer Modern (LaTeX default; cvpr/iccv/neurips/icml/iclr bodies)
    "lmodern": r"\usepackage{lmodern}",
    "newtx": r"\usepackage{newtxmath}",          # Times-like math (acl, many IEEE/Springer setups)
    "newtx-libertine": r"\usepackage[libertine]{newtxmath}",
    "mathptmx": r"\usepackage{mathptmx}",
    "newpx": r"\usepackage{newpxmath}",          # Palatino-like
    "mathpazo": r"\usepackage{mathpazo}",
    "libertinust1": r"\usepackage{libertinust1math}",
    "stix2": r"\usepackage{stix2}",
    "fourier": r"\usepackage{fourier}",
    "kpfonts": r"\usepackage{kpfonts}",
    "euler": r"\usepackage{eulervm}",
}
# packages whose presence (in the paper preamble or its local .sty/.cls) selects the math setup, in priority order
MATH_PACKAGE_RULES = [
    ("newtxmath", "newtx"), ("mathptmx", "mathptmx"), ("newpxmath", "newpx"), ("mathpazo", "mathpazo"),
    ("libertinust1math", "libertinust1"), ("stix2", "stix2"), ("fourier", "fourier"), ("kpfonts", "kpfonts"),
    ("eulervm", "euler"), ("lmodern", "lmodern"),
]
# math-related packages copied from the paper so its macros work (the text-font packages are not copied: only math
# goes through LaTeX; \usepackage{times} changes the text font only, the math stays Computer Modern)
MATH_HELPER_PACKAGES = {"amsmath", "amssymb", "amsfonts", "mathtools", "bm", "bbm", "dsfont", "mathrsfs", "upgreek",
                        "esint", "nicefrac", "xfrac", "siunitx", "physics", "cancel", "stmaryrd", "mathbbol",
                        "bbold", "accents", "units", "xspace", "amsthm", "commath", "braket", "eucal", "calrsfs"}
_DEF_CMDS = ("newcommand", "renewcommand", "providecommand", "DeclareMathOperator", "DeclareRobustCommand",
             "def", "newcommand*", "renewcommand*", "providecommand*", "DeclareMathOperator*", "DeclarePairedDelimiter",
             "DeclareMathAlphabet", "SetMathAlphabet", "DeclareSymbolFont", "DeclareMathSymbol", "DeclareMathSizes")


class TexError(RuntimeError):
    pass


# ----------------------------------------------------------------------------- environment


def tex_env():
    """Installed TeX tools and Python helpers (None when missing)."""
    env = {k: shutil.which(k) for k in ("latex", "pdflatex", "dvisvgm", "dvipng", "kpsewhich", "pdffonts")}
    try:
        import pymupdf  # noqa: F401
        env["pymupdf"] = "python module pymupdf"
    except Exception:
        try:
            import fitz  # noqa: F401
            env["pymupdf"] = "python module fitz"
        except Exception:
            env["pymupdf"] = None
    return env


def env_problems(env, need_pdf=False):
    """Human-readable list of what is missing for typesetting (empty = fine)."""
    out = []
    if not env.get("latex"):
        out.append("latex not found: install a TeX distribution (TeX Live, MiKTeX or TinyTeX) to typeset $...$ math")
    if not env.get("dvisvgm") and not (env.get("pdflatex") and env.get("pymupdf")):
        out.append("dvisvgm not found (TeX Live package 'dvisvgm'); without it the SVG glyphs need pdflatex + PyMuPDF")
    if need_pdf and not (env.get("pdflatex") and env.get("pymupdf")):
        out.append("pdflatex + PyMuPDF (pip install pymupdf) are needed to embed real Type 1 math fonts in the PDF; "
                   "without them the math in the PDF stays as glyph outlines")
    return out


def get_pymupdf():
    try:
        import pymupdf
        return pymupdf
    except Exception:
        import fitz
        return fitz


def texmf_font_dirs():
    """OpenType/TrueType font directories of the TeX tree (for Chromium via fontconfig)."""
    kp = shutil.which("kpsewhich")
    if not kp:
        return []
    dirs = []
    for var in ("TEXMFDIST", "TEXMFLOCAL", "TEXMFHOME"):
        try:
            r = subprocess.run([kp, f"-var-value={var}"], capture_output=True, text=True, timeout=20)
        except Exception:
            continue
        root = r.stdout.strip()
        for sub in ("fonts/opentype", "fonts/truetype"):
            p = Path(root) / sub if root else None
            if p and p.is_dir() and str(p) not in dirs:
                dirs.append(str(p))
    return dirs


def fontconfig_env(td):
    """Environment with a temporary FONTCONFIG_FILE that adds the TeX font dirs to the system configuration.

    Chromium only sees fontconfig fonts, so a figure set in e.g. 'TeX Gyre Heros' would otherwise be measured and
    drawn with a fallback font (wrong widths, false overflow errors). Returns (env, dirs); env is None when there is
    nothing to add.
    """
    dirs = texmf_font_dirs()
    if not dirs:
        return None, []
    conf = Path(td) / "fonts.conf"
    base = os.environ.get("FONTCONFIG_FILE")
    include = base if base and Path(base).exists() else "/etc/fonts/fonts.conf"
    body = "\n".join(f"  <dir>{html.escape(d)}</dir>" for d in dirs)
    conf.write_text('<?xml version="1.0"?>\n<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n<fontconfig>\n'
                    f'  <include ignore_missing="yes">{html.escape(include)}</include>\n{body}\n</fontconfig>\n',
                    encoding="utf-8")
    env = dict(os.environ)
    env["FONTCONFIG_FILE"] = str(conf)
    return env, dirs


# ----------------------------------------------------------------------------- paper preamble


def _strip_comments(s):
    return re.sub(r"(?<!\\)%.*", "", s)


def _balanced(s, i):
    """s[i] == '{' -> index just past the matching '}' (or -1)."""
    depth = 0
    for j in range(i, len(s)):
        c = s[j]
        if c == "\\":
            continue
        if c == "{" and (j == 0 or s[j - 1] != "\\"):
            depth += 1
        elif c == "}" and (j == 0 or s[j - 1] != "\\"):
            depth -= 1
            if depth == 0:
                return j + 1
    return -1


def _extract_definitions(src):
    r"""Macro definitions (\newcommand, \DeclareMathOperator, \def, ...) with balanced arguments."""
    out = []
    pat = re.compile(r"\\(" + "|".join(re.escape(c) for c in sorted(_DEF_CMDS, key=len, reverse=True)) + r")(?![A-Za-z])")
    pos = 0
    while True:
        m = pat.search(src, pos)
        if not m:
            break
        cmd, i = m.group(1), m.end()
        start = m.start()
        if cmd == "def":
            m2 = re.match(r"\s*(\\[A-Za-z@]+|\\.)([^{]*)", src[i:])
            if not m2:
                pos = i
                continue
            j = i + m2.end()
            if j < len(src) and src[j] == "{":
                k = _balanced(src, j)
                if k > 0:
                    out.append(src[start:k])
                    pos = k
                    continue
            pos = i
            continue
        j, args, ok = i, 0, True
        need = {"DeclareMathSizes": 4, "DeclareMathSymbol": 4, "DeclareSymbolFont": 5, "DeclareMathAlphabet": 5,
                "SetMathAlphabet": 6, "DeclarePairedDelimiter": 3}.get(cmd.rstrip("*"), 2)
        while args < need:
            while j < len(src) and src[j] in " \t\n":
                j += 1
            if j < len(src) and src[j] == "*" and args == 0:
                j += 1
                continue
            if j < len(src) and src[j] == "[":
                k = src.find("]", j)
                if k < 0:
                    ok = False
                    break
                j = k + 1
                continue
            if j < len(src) and src[j] == "{":
                k = _balanced(src, j)
                if k < 0:
                    ok = False
                    break
                j, args = k, args + 1
                continue
            if j < len(src) and src[j] == "\\" and args == 0:     # \newcommand\foo{...}
                m3 = re.match(r"\\[A-Za-z@]+|\\.", src[j:])
                j, args = j + m3.end(), 1
                continue
            ok = args >= 2 or (args >= 1 and cmd.startswith("Declare"))
            break
        if ok and args >= 1:
            out.append(src[start:j])
        pos = max(j, i)
    return out


def _safe_definition(d):
    r"""Make \newcommand / \renewcommand work whether or not the macro already exists in the snippet document."""
    m = re.match(r"\\(new|renew|provide)command(\*?)\s*(\{\s*(\\[A-Za-z@]+)\s*\}|(\\[A-Za-z@]+))", d)
    if m:
        name = m.group(4) or m.group(5)
        rest = d[m.end():]
        return f"\\providecommand{{{name}}}{{}}\\renewcommand{m.group(2)}{{{name}}}{rest}"
    m = re.match(r"\\DeclareRobustCommand(\*?)\s*(\{\s*(\\[A-Za-z@]+)\s*\}|(\\[A-Za-z@]+))", d)
    if m:
        name = m.group(3) or m.group(4)
        return f"\\providecommand{{{name}}}{{}}\\let{name}\\relax" + d
    return d


def _read(p):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def paper_preamble(paper=None, math=None, macros=True):
    """Build the snippet preamble from the paper source.

    paper : main .tex (its preamble, \\input/\\include'd macro files and local .sty/.cls files are read)
    math  : None (detect), a key of MATH_SETUPS, or verbatim LaTeX (contains a backslash)
    macros: copy the paper's \\newcommand/\\DeclareMathOperator/... definitions so figure notation equals body notation
    Returns (preamble, info).
    """
    info = {"paper": str(paper) if paper else None, "sources": [], "math": None, "macros": 0, "packages": []}
    texts = []
    if paper:
        p = Path(paper).resolve()
        if not p.exists():
            raise TexError(f"paper file {p} not found")
        main = _strip_comments(_read(p))
        cut = main.find(r"\begin{document}")
        pre = main[:cut] if cut >= 0 else main
        texts.append(pre)
        info["sources"].append(p.name)
        seen = {p}
        queue = [(p.parent, pre)]
        while queue:
            base, txt = queue.pop()
            names = []
            for m in re.finditer(r"\\(?:input|include)\s*\{([^}]+)\}", txt):
                names.append((m.group(1).strip(), (".tex", "")))
            for m in re.finditer(r"\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", txt):
                for n in m.group(1).split(","):
                    names.append((n.strip(), (".sty",)))
            for m in re.finditer(r"\\documentclass\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", txt):
                names.append((m.group(1).strip(), (".cls",)))
            for n, exts in names:
                for ext in exts:
                    q = (base / (n if (not ext or n.endswith(ext)) else n + ext)).resolve()
                    if q.is_file() and q not in seen:
                        seen.add(q)
                        t = _strip_comments(_read(q))
                        texts.append(t)
                        info["sources"].append(q.name)
                        queue.append((q.parent, t))
                        break
    alltext = "\n".join(texts)
    pkgs = []
    for m in re.finditer(r"\\(?:usepackage|RequirePackage)\s*(\[[^\]]*\])?\s*\{([^}]+)\}", alltext):
        for n in m.group(2).split(","):
            pkgs.append((n.strip(), m.group(1) or ""))
    names = [n for n, _ in pkgs]
    if math is None:
        key = "cm"
        for pkg, k in MATH_PACKAGE_RULES:
            if pkg in names:
                key = k
                break
        if key in ("newtx", "newtx-libertine"):
            opt = next((o for n, o in pkgs if n == "newtxmath"), "")
            math_line = f"\\usepackage{opt}{{newtxmath}}"
        else:
            math_line = MATH_SETUPS[key]
        info["math"] = key + (" (detected)" if paper else " (default)")
    elif "\\" in math:
        math_line, info["math"] = math, "custom"
    else:
        if math not in MATH_SETUPS:
            raise TexError(f"unknown math setup '{math}'. Use one of {', '.join(MATH_SETUPS)} or verbatim LaTeX")
        math_line, info["math"] = MATH_SETUPS[math], math + " (override)"
    lines = []
    helpers = []
    for n, o in pkgs:
        if n in MATH_HELPER_PACKAGES and n not in helpers:
            helpers.append(n)
            lines.append(f"\\usepackage{o}{{{n}}}")
    # amsmath (\text, \operatorname, ...) is always available; amssymb too unless the math font package brings
    # its own symbols. Both go before the math font package, as newtxmath and friends require.
    if "amsmath" not in helpers:
        lines.insert(0, r"\usepackage{amsmath}")
    if "amssymb" not in helpers and math_line in ("", MATH_SETUPS["lmodern"]):
        lines.insert(1, r"\usepackage{amssymb}")
    if math_line:
        lines.append(math_line)
    info["packages"] = helpers
    if macros and alltext:
        defs = [_safe_definition(d) for d in _extract_definitions(alltext)]
        lines += defs
        info["macros"] = len(defs)
    return "\n".join(lines), info


# ----------------------------------------------------------------------------- sizes


def math_sizes(pt):
    """(script, scriptscript) LaTeX uses for text size pt; non-standard sizes follow 0.7/0.5 with a 5pt floor."""
    for k, v in LATEX_MATH_SIZES.items():
        if abs(k - pt) < 0.005:
            return v
    return (max(MIN_SCRIPT_PT, round(0.7 * pt, 2)), max(MIN_SCRIPT_PT, round(0.5 * pt, 2)))


def _declared_sizes(preamble):
    out = {}
    for m in re.finditer(r"\\DeclareMathSizes\s*\{([\d.]+)\}\s*\{([\d.]+)\}\s*\{([\d.]+)\}\s*\{([\d.]+)\}", preamble):
        out[round(float(m.group(1)), 2)] = (float(m.group(3)), float(m.group(4)))
    return out


def effective_sizes(pt, preamble):
    d = _declared_sizes(preamble)
    return d.get(round(pt, 2)) or math_sizes(pt)


# ----------------------------------------------------------------------------- compile


def _fmt(v):
    return f"{v:.4f}".rstrip("0").rstrip(".")


def build_document(snippets, preamble):
    r"""One page per snippet, cropped to its TeX box; \typeout logs the box metrics."""
    sizes = sorted({round(s["pt"], 2) for s in snippets})
    declared = _declared_sizes(preamble)
    decl = []
    for pt in sizes:
        if pt not in declared and not any(abs(k - pt) < 0.005 for k in LATEX_MATH_SIZES):
            sc, ssc = math_sizes(pt)
            decl.append(f"\\DeclareMathSizes{{{_fmt(pt)}}}{{{_fmt(pt)}}}{{{_fmt(sc)}}}{{{_fmt(ssc)}}}")
    body = []
    for s in snippets:
        col = s.get("color") or "000000"
        body.append(f"\\tmsnip{{{_fmt(s['pt'])}}}{{{col}}}{{{s['tex']}}}")
    return "\n".join([
        r"\RequirePackage{fix-cm}",
        r"\documentclass{article}",
        r"\usepackage{xcolor}",
        "\n".join(decl),
        preamble,
        r"\pagestyle{empty}",
        r"\newbox\tmbox",
        r"\makeatletter",
        r"\newcommand\tmsnip[3]{\setbox\tmbox\hbox{\fontsize{#1}{#1}\selectfont\color[HTML]{#2}$#3$}%",
        r"  \typeout{TMBOX:\the\wd\tmbox,\the\ht\tmbox,\the\dp\tmbox}%",
        r"  \ifdim\wd\tmbox<0.01pt \setbox\tmbox\hbox to 0.01pt{\hss}\fi",
        r"  \pdfpagewidth=\wd\tmbox \pdfpageheight=\dimexpr\ht\tmbox+\dp\tmbox+0.01pt\relax",
        r"  \shipout\vbox{\kern0pt\box\tmbox}}",
        r"\makeatother",
        r"\begin{document}",
        r"\hoffset=-1in \voffset=-1in",
        "\n".join(body),
        r"\end{document}",
    ])


def _tex_errors(log, snippets):
    errs = []
    lines = log.splitlines()
    for i, l in enumerate(lines):
        if l.startswith("! "):
            ctx = " ".join(x.strip() for x in lines[i + 1:i + 3])
            errs.append(f"{l[2:].strip()} {ctx}".strip())
    return errs


def compile_snippets(snippets, preamble, workdir=None, svg=True, pdf=True):
    """Typeset snippets [{tex, pt, color}] -> dict(metrics=[(wd, ht, dp) in bp], svgs=[inner svg], pdf=path).

    svg bodies are glyph paths in bp with the box's baseline-left corner at (0, 0).
    """
    env = tex_env()
    probs = env_problems(env)
    if probs:
        raise TexError("; ".join(probs))
    td = Path(workdir or tempfile.mkdtemp(prefix="texmath_"))
    td.mkdir(parents=True, exist_ok=True)
    (td / "m.tex").write_text(build_document(snippets, preamble), encoding="utf-8")
    res = {"metrics": [], "svgs": [], "pdf": None, "dir": str(td)}
    use_dvisvgm = svg and bool(env.get("dvisvgm"))

    def run_tex(engine):
        r = subprocess.run([env[engine], "-interaction=nonstopmode", "-halt-on-error", "m.tex"], cwd=td,
                           capture_output=True, text=True, timeout=180)
        log = _read(td / "m.log")
        if r.returncode != 0:
            errs = _tex_errors(log, snippets) or [(r.stdout or r.stderr).strip()[-400:]]
            msg = errs[0][:400]
            m = re.search(r"File `([^']+)\.sty' not found", msg)
            if m:
                msg += (f" -> install the TeX package that provides {m.group(1)}.sty (e.g. tlmgr install "
                        f"{m.group(1).replace('math', '')}), or choose another setup with --math")
            raise TexError(f"{engine} failed: {msg}")
        return log

    log = None
    if use_dvisvgm:
        log = run_tex("latex")
        r = subprocess.run([env["dvisvgm"], "--no-fonts=1", "--exact-bbox", "-d", "3", "-p", "1-", "-o", "p%p.svg",
                            "m.dvi"], cwd=td, capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            raise TexError(f"dvisvgm failed: {(r.stderr or r.stdout).strip()[-400:]}")
    if pdf or (svg and not use_dvisvgm):
        if not env.get("pdflatex"):
            if not use_dvisvgm:
                raise TexError("neither dvisvgm nor pdflatex is available")
        else:
            log = run_tex("pdflatex")
            res["pdf"] = str(td / "m.pdf")
    mets = []
    for m in re.finditer(r"TMBOX:([-\d.]+)pt,([-\d.]+)pt,([-\d.]+)pt", log or ""):
        mets.append(tuple(float(v) * 72.0 / 72.27 for v in m.groups()))
    if len(mets) != len(snippets):
        raise TexError(f"expected {len(snippets)} boxes, LaTeX reported {len(mets)}")
    res["metrics"] = mets
    if svg:
        n = len(snippets)
        width = len(str(n))
        for i in range(n):
            if use_dvisvgm:
                cand = [td / f"p{i + 1}.svg", td / f"p{i + 1:0{width}d}.svg"]
                f = next((c for c in cand if c.exists()), None)
                if f is None:
                    raise TexError(f"dvisvgm wrote no page {i + 1}")
                res["svgs"].append(_dvisvgm_body(_read(f), mets[i]))
            else:
                res["svgs"].append(_pdf_page_svg_body(res["pdf"], i, mets[i]))
    return res


def _dvisvgm_body(svg_text, met):
    """Inner content of a dvisvgm page, shifted so the box's baseline-left corner is (0, 0).

    With \\hoffset = \\voffset = -1in the box's top-left corner is at (-72, -72) bp in dvisvgm coordinates.
    """
    m = re.search(r"<g id='page\d+'>(.*)</g>\s*</svg>", svg_text, re.S)
    inner = m.group(1).strip() if m else ""
    inner = re.sub(r"\s*\n\s*", "", inner)
    return f'<g transform="translate(72 {_fmt(72 - met[1])})">{inner}</g>'


def _pdf_page_svg_body(pdf, i, met):
    """Fallback without dvisvgm: glyph paths of the cropped PDF page via PyMuPDF (top-left origin, bp)."""
    fz = get_pymupdf()
    doc = fz.open(pdf)
    s = doc[i].get_svg_image(text_as_path=True)
    doc.close()
    s = re.sub(r"<\?xml[^>]*>", "", s)
    body = re.sub(r"^.*?<svg[^>]*>", "", s, flags=re.S)
    body = re.sub(r"</svg>\s*$", "", body.strip())
    tag = hashlib.sha1(s.encode()).hexdigest()[:6]
    body = re.sub(r'id="([^"]+)"', lambda m: f'id="tm{tag}-{m.group(1)}"', body)
    body = re.sub(r'(xlink:href|href)="#([^"]+)"', lambda m: f'{m.group(1)}="#tm{tag}-{m.group(2)}"', body)
    body = re.sub(r"\s*\n\s*", "", body)
    return f'<g transform="translate(0 {_fmt(-met[1])})">{body}</g>'


# ----------------------------------------------------------------------------- segments


def split_math(s):
    r"""'scores $S[i,v,p]$' -> [('scores ', False), ('S[i,v,p]', True)]. \$ is a literal dollar sign."""
    out, buf, i, inmath = [], "", 0, False
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s) and s[i + 1] == "$":
            buf += "\\$" if inmath else "$"
            i += 2
            continue
        if c == "$":
            if buf or inmath:
                out.append((buf, inmath))
            buf, inmath = "", not inmath
            i += 1
            continue
        buf += c
        i += 1
    if inmath:
        raise TexError(f"unbalanced $ in {s!r}")
    if buf:
        out.append((buf, False))
    return [(t, m) for t, m in out if t or m]


def has_math(s):
    try:
        return any(m for _, m in split_math(s))
    except TexError:
        return True


# ----------------------------------------------------------------------------- PDF stamping


def stamp_pdf(pdf_path, placements, snippet_pdf):
    """Draw page i of snippet_pdf into rect placements[i] = (x0, y0, x1, y1) pt (top-left origin) of pdf_path."""
    fz = get_pymupdf()
    src = fz.open(snippet_pdf)
    doc = fz.open(pdf_path)
    page = doc[0]
    for i, rect in enumerate(placements):
        if rect is None:
            continue
        page.show_pdf_page(fz.Rect(*rect), src, i, keep_proportion=False, overlay=True)
    tmp = str(pdf_path) + ".stamp.pdf"
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    src.close()
    os.replace(tmp, pdf_path)


def pdf_fonts(pdf_path):
    """[(basefont, type)] of all fonts in page 1 (including form XObjects), via PyMuPDF."""
    fz = get_pymupdf()
    doc = fz.open(pdf_path)
    out = []
    try:
        for f in doc.get_page_fonts(0, full=True):
            out.append((re.sub(r"^[A-Z]{6}\+", "", f[3]), f[2]))
    finally:
        doc.close()
    return out


def pdf_text_spans(pdf_path):
    """[(font, size_pt, origin_y, text)] of page 1, via PyMuPDF."""
    fz = get_pymupdf()
    doc = fz.open(pdf_path)
    out = []
    try:
        for b in doc[0].get_text("rawdict")["blocks"]:
            for ln in b.get("lines", []):
                for sp in ln["spans"]:
                    out.append((re.sub(r"^[A-Z]{6}\+", "", sp["font"]), sp["size"], sp["origin"][1],
                                "".join(c["c"] for c in sp["chars"])))
    finally:
        doc.close()
    return out


# ----------------------------------------------------------------------------- CLI


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paper", help="paper's main .tex (preamble, macros and local .sty/.cls are read)")
    ap.add_argument("--math", help="math setup override: " + ", ".join(MATH_SETUPS) + " or verbatim LaTeX")
    ap.add_argument("--no-macros", action="store_true", help="do not copy the paper's macro definitions")
    ap.add_argument("--show", action="store_true", help="print the preamble snippets are compiled with")
    ap.add_argument("--check-env", action="store_true", help="list the TeX tools found")
    ap.add_argument("--test", metavar="TEX", help="typeset one snippet (e.g. 'c_{FA}') and print its box")
    ap.add_argument("--pt", type=float, default=6.0, help="size for --test (default 6pt)")
    a = ap.parse_args(argv)
    if a.check_env or not (a.show or a.test):
        env = tex_env()
        for k, v in env.items():
            print(f"  {k:9s} {v or '-'}")
        for p in env_problems(env, need_pdf=True):
            print("  note:", p)
        if not (a.show or a.test):
            return 0
    pre, info = paper_preamble(a.paper, a.math, not a.no_macros)
    if a.show:
        print(f"% math: {info['math']}; packages: {', '.join(info['packages']) or '-'}; macros: {info['macros']}; "
              f"read: {', '.join(info['sources']) or '-'}")
        print(pre)
    if a.test:
        r = compile_snippets([{"tex": a.test, "pt": a.pt, "color": "000000"}], pre)
        wd, ht, dp = r["metrics"][0]
        sc, ssc = effective_sizes(a.pt, pre)
        print(f"box {wd:.3f} x {ht:.3f} + {dp:.3f} bp; script {sc}pt, scriptscript {ssc}pt; files in {r['dir']}")
        if r.get("pdf"):
            print("fonts:", ", ".join(f"{n} ({t})" for n, t in pdf_fonts(r["pdf"])) if tex_env()["pymupdf"] else "-")
    return 0


if __name__ == "__main__":
    sys.exit(main())
