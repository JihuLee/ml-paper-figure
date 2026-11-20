#!/usr/bin/env python3
"""render_svg.py - lint, render and export ML-paper figures (SVG -> PNG / PDF).

Runs fully offline with whatever renderer is installed locally:
  chromium (Playwright for Python or Node) > rsvg-convert > inkscape > cairosvg > resvg (PNG only)

Modes
  python render_svg.py fig.svg            review: lint + fig.png + fig.debug.png + fig.preview.png
  python render_svg.py fig.svg --export   export: lint + hi-res fig.png + vector fig.pdf + PDF checks
  python render_svg.py fig.svg --check    lint only (no image files)
  python render_svg.py --list-backends    show detected renderers

Math
  Write math as $...$ inside an ordinary single-line <text> (e.g. <text ...>scores $S[i,v,p]$</text>). Before each run
  the script typesets every $...$ segment with LaTeX (tex_math.py: latex -> dvisvgm glyph paths, in the paper's math
  setup with --paper main.tex or --math cm|newtx|...) and writes the result back into the SVG: the source <text> is
  kept, hidden, as data-tex="src", followed by a generated <g data-tex="out" class="tex-line"> holding the sans
  segments and one <g class="tex-math"> per math segment on the same baseline. Edit the source <text>, never the
  generated group. The exported PDF gets the real Type 1 math fonts (pdflatex snippets stamped with PyMuPDF).

Review images
  fig.debug.png    figure + coordinate grid (user units) + numbered boxes around every issue (E1, W2 ...)
  fig.preview.png  figure at its printed size (target width at --preview-dpi) for a legibility check

Lint (exact geometry when Chromium is available, approximate otherwise)
  XML validity, viewBox, self-containment (no external files / web fonts / scripts / foreignObject),
  broken url(#id) refs, emoji glyphs, renderer-portability hazards (filters, dominant-baseline, ...),
  elements outside the canvas, text overflowing / crowding its box, overlapping labels,
  connectors running through modules or labels, crossing / overlapping connectors,
  arrowheads that float or dig into their target, near-misaligned boxes and baselines,
  font sizes in printed points at the target paper width, math groups (one text box each; printed base and script
  sizes, script >= 5pt), math baseline vs the adjacent sans text.

Exit status: 0 = no errors (and no warnings with --strict), 1 = issues found, 2 = fatal (parse error, no renderer).
"""
from __future__ import annotations

import argparse
import atexit
import hashlib
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
try:  # shared Inter width table (used by the approximate geometry fallback)
    from svg_geom import text_width as _text_width
except Exception:  # pragma: no cover
    _text_width = None
import tex_math  # noqa: E402

SVG_NS = "http://www.w3.org/2000/svg"

# Printed widths of common venues (inches) -> points (1/72 in).
TARGETS = {
    "neurips": (5.5, "NeurIPS / ICLR / COLM \\textwidth (5.5in)"),
    "iclr": (5.5, "ICLR \\textwidth (5.5in)"),
    "icml": (6.75, "ICML \\textwidth, figure* (6.75in)"),
    "icml-col": (3.25, "ICML \\columnwidth (3.25in)"),
    "cvpr": (6.875, "CVPR / ICCV / WACV \\textwidth, figure* (6.875in)"),
    "cvpr-col": (3.281, "CVPR / ICCV \\columnwidth (3.28in)"),
    "eccv": (4.803, "ECCV / LNCS \\textwidth (12.2cm)"),
    "acl": (6.3, "ACL / EMNLP \\textwidth, figure* (16cm)"),
    "acl-col": (3.03, "ACL / EMNLP \\columnwidth (7.7cm)"),
    "aaai": (7.0, "AAAI \\textwidth, figure* (7in)"),
    "aaai-col": (3.3, "AAAI \\columnwidth (3.3in)"),
}
COMPARE_TARGETS = ["neurips", "cvpr", "icml-col"]

EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")
GENERIC_FAMILIES = {"sans-serif", "serif", "monospace", "system-ui", "cursive", "fantasy", "ui-sans-serif", "ui-serif", "ui-monospace"}

# ----------------------------------------------------------------------------- utils


def issue(sev, code, msg, bbox=None):
    return {"sev": sev, "code": code, "msg": msg, "bbox": bbox}


def tag_issues(issues, start=None):
    counts = dict(start or {"error": 0, "warn": 0, "info": 0})
    for it in issues:
        if it.get("tag"):
            continue
        counts[it["sev"]] = counts.get(it["sev"], 0) + 1
        it["tag"] = {"error": "E", "warn": "W"}.get(it["sev"], "I") + str(counts[it["sev"]])
    return counts


def local(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


def parse_length(v):
    """SVG length -> CSS px (None for %, auto or missing)."""
    if v is None:
        return None
    m = re.fullmatch(r"\s*([-+]?[\d.]+(?:e[-+]?\d+)?)\s*(px|pt|pc|in|cm|mm)?\s*", v, re.I)
    if not m:
        return None
    val = float(m.group(1))
    unit = (m.group(2) or "px").lower()
    return val * {"px": 1, "pt": 96 / 72, "pc": 16, "in": 96, "cm": 96 / 2.54, "mm": 96 / 25.4}[unit]


def parse_target(s):
    s = s.strip().lower()
    if s in TARGETS:
        inch, desc = TARGETS[s]
        return s, inch * 72.0, desc
    m = re.fullmatch(r"([\d.]+)\s*(in|pt|cm|mm|bp)", s)
    if not m:
        sys.exit(f"unknown --target '{s}'. Use one of {', '.join(TARGETS)} or a length like 5.5in / 397pt / 12cm")
    v, u = float(m.group(1)), m.group(2)
    ptv = {"in": v * 72, "pt": v * 72 / 72.27, "bp": v, "cm": v / 2.54 * 72, "mm": v / 25.4 * 72}[u]
    return s, ptv, f"custom width {s}"


def run(cmd, timeout=180, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)


def r1(v):
    return round(v * 10) / 10


# ----------------------------------------------------------------------------- static lint


def static_lint(svg_path: Path):
    text = svg_path.read_text(encoding="utf-8")
    issues, meta = [], {"text": text}
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as e:
        line, col = getattr(e, "position", (0, 0))
        src = text.splitlines()
        ctx = src[line - 1].strip()[:120] if 0 < line <= len(src) else ""
        issues.append(issue("error", "xml-parse", f"not well-formed XML at line {line}, col {col}: {e}. Line: {ctx!r}"))
        meta["fatal"] = True
        return issues, meta

    if local(root.tag) != "svg":
        issues.append(issue("error", "not-svg", f"root element is <{local(root.tag)}>, expected <svg>"))
        meta["fatal"] = True
        return issues, meta
    if not root.tag.startswith("{" + SVG_NS + "}"):
        issues.append(issue("error", "svg-namespace", 'root <svg> lacks xmlns="http://www.w3.org/2000/svg" - standalone renderers will draw nothing'))

    vb = root.get("viewBox")
    if vb:
        try:
            x, y, w, h = [float(t) for t in re.split(r"[\s,]+", vb.strip())]
            meta["vb"] = (x, y, w, h)
        except ValueError:
            issues.append(issue("error", "bad-viewbox", f"viewBox='{vb}' is not four numbers"))
    else:
        issues.append(issue("error", "no-viewbox", "root <svg> has no viewBox; the figure cannot be scaled reliably"))
    wpx, hpx = parse_length(root.get("width")), parse_length(root.get("height"))
    meta["size_px"] = (wpx, hpx)
    if "vb" not in meta and wpx and hpx:
        meta["vb"] = (0.0, 0.0, wpx, hpx)
    if "vb" in meta:
        _, _, w, h = meta["vb"]
        if w <= 0 or h <= 0:
            issues.append(issue("error", "bad-viewbox", "viewBox width/height must be positive"))
            meta["fatal"] = True
        if wpx is None or hpx is None:
            issues.append(issue("warn", "no-size", f'set width="{w:g}" height="{h:g}" on the root <svg> (some viewers default to 100%)'))
        elif abs(wpx / hpx - w / h) > 0.01 * (w / h):
            issues.append(issue("warn", "aspect-mismatch", f"width/height aspect {wpx / hpx:.3f} differs from viewBox aspect {w / h:.3f}"))
    elif not meta.get("fatal"):
        meta["fatal"] = True

    ids, dup = set(), set()
    refs = []
    hazards = {}
    families = []
    style_text = ""
    has_text = False

    def hazard(key, msg):
        hazards.setdefault(key, [0, msg])[0] += 1

    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        tg = local(el.tag)
        i = el.get("id")
        if i:
            (dup if i in ids else ids).add(i)
        if tg in ("script", "foreignObject", "iframe", "video", "audio", "canvas"):
            issues.append(issue("error", "forbidden-element", f"<{tg}> is not allowed: it breaks PDF export and non-browser renderers"))
        if tg == "style":
            style_text += (el.text or "") + "\n"
        if tg in ("filter", "feDropShadow", "feGaussianBlur"):
            hazard("filter", "filters (drop shadows / blur) are rasterised in Chromium PDFs and ignored by cairosvg; use an offset shadow rect instead")
        if tg == "text":
            has_text = True
            content = "".join(el.itertext())
            if EMOJI_RE.search(content):
                issues.append(issue("warn", "emoji", f"text {content.strip()[:40]!r} contains emoji/dingbat glyphs; they render as bitmaps or tofu in PDF. Use the vector badges from svg-primitives.md"))
            if el.get("data-tex") != "src" and tex_math.has_math(content):
                issues.append(issue("error", "math-untypeset", f"text {content.strip()[:50]!r} has $...$ math that was not typeset "
                                    "(see the 'math' note); never fake it with italic tspans"))
        for k, v in el.attrib.items():
            lk = local(k)
            if lk == "href":
                if v.startswith("#"):
                    refs.append(v[1:])
                elif v.startswith("data:"):
                    if tg == "image" and re.match(r"data:image/(png|jpe?g|webp|gif)", v):
                        issues.append(issue("warn", "raster-image", "embedded raster <image>; prefer vector shapes (rasters blur in print and bloat the PDF)"))
                else:
                    issues.append(issue("error", "external-ref", f"<{tg}> references external resource '{v[:60]}' - the SVG must be self-contained"))
            for u in re.findall(r"url\(\s*['\"]?([^)'\"]+)['\"]?\s*\)", v):
                if u.startswith("#"):
                    refs.append(u[1:])
                elif not u.startswith("data:"):
                    issues.append(issue("error", "external-ref", f"url({u[:60]}) points outside the file"))
            if lk == "filter" or (lk == "style" and "filter:" in v):
                hazard("filter", "filters (drop shadows / blur) are rasterised in Chromium PDFs and ignored by cairosvg; use an offset shadow rect instead")
            if lk in ("dominant-baseline", "alignment-baseline") or (lk == "style" and "baseline" in v):
                hazard("baseline", "dominant-/alignment-baseline renders inconsistently across renderers; place text with y = centre + 0.35*font-size instead")
            if "context-stroke" in v or "context-fill" in v:
                hazard("context", "context-stroke/context-fill markers are unsupported in rsvg/cairosvg/PDF; define one marker per colour")
            if v == "auto-start-reverse":
                hazard("asr", "orient='auto-start-reverse' is SVG2-only; use a separate start marker")
            if "var(--" in v:
                hazard("cssvar", "CSS custom properties (var(--x)) are unsupported outside browsers; write literal colours")
            if lk == "textLength":
                hazard("textlength", "textLength distorts glyphs and varies by renderer; size the box to the text instead")
            if lk in ("mix-blend-mode",) or (lk == "style" and "mix-blend-mode" in v):
                hazard("blend", "mix-blend-mode forces rasterisation in PDF")
            if lk == "font-family":
                families.append(v)
            if lk == "style":
                m = re.search(r"font-family\s*:\s*([^;]+)", v)
                if m:
                    families.append(m.group(1))

    # <style> content
    if style_text:
        for u in re.findall(r"url\(\s*['\"]?([^)'\"]+)['\"]?\s*\)", style_text):
            if u.startswith("#"):
                refs.append(u[1:])
            elif not u.startswith("data:"):
                issues.append(issue("error", "external-ref", f"<style> url({u[:60]}) points outside the file"))
        if re.search(r"@import|@font-face", style_text):
            issues.append(issue("error", "web-font", "<style> uses @import/@font-face; rely on the system font stack instead"))
        for m in re.finditer(r"font-family\s*:\s*([^;}]+)", style_text):
            families.append(m.group(1))
        if re.search(r"font-size\s*:\s*[\d.]+\s*(;|}|$)", style_text, re.M):
            issues.append(issue("warn", "css-unitless", "unitless font-size inside <style> is invalid CSS and is ignored; write e.g. font-size: 14px"))
        if "filter" in style_text:
            hazard("filter", "filters (drop shadows / blur) are rasterised in Chromium PDFs and ignored by cairosvg; use an offset shadow rect instead")
        if "var(--" in style_text:
            hazard("cssvar", "CSS custom properties (var(--x)) are unsupported outside browsers; write literal colours")
        if "dominant-baseline" in style_text:
            hazard("baseline", "dominant-baseline renders inconsistently across renderers; place text with y = centre + 0.35*font-size instead")

    for i in sorted(dup):
        issues.append(issue("error", "duplicate-id", f"id '{i}' is defined more than once"))
    for r in sorted(set(refs)):
        if r not in ids:
            issues.append(issue("error", "missing-ref", f"reference to #{r} but no element has id='{r}'"))
    for key, (n, msg) in hazards.items():
        issues.append(issue("warn", f"portability-{key}", f"{msg} ({n} use{'s' if n > 1 else ''})"))

    if has_text and not families:
        issues.append(issue("warn", "no-font-family", "no font-family declared; renderers fall back to different serif fonts. Set the stack from design-system.md on the root <svg> or in <style>"))
    first_family = None
    for fam in families:
        toks = [t.strip().strip("'\"") for t in fam.split(",") if t.strip()]
        if toks and first_family is None:
            first_family = toks[0]
        if toks and not any(t.lower() in GENERIC_FAMILIES for t in toks):
            issues.append(issue("warn", "font-fallback", f"font-family '{fam.strip()[:60]}' has no generic fallback (append sans-serif)"))
            break
    meta["first_family"] = first_family

    # background check (first painted child)
    bg_ok = False
    for el in root:
        if not isinstance(el.tag, str):
            continue
        tg = local(el.tag)
        if tg in ("defs", "style", "title", "desc", "metadata"):
            continue
        if tg == "rect" and (el.get("width") in ("100%",) or (meta.get("vb") and parse_length(el.get("width")) and parse_length(el.get("width")) >= meta["vb"][2] - 0.5)):
            bg_ok = (el.get("fill") or "").lower() in ("#fff", "#ffffff", "white")
        break
    if not bg_ok:
        issues.append(issue("info", "no-background", 'no full-canvas white <rect> as first element; PNGs from some renderers will be transparent'))
    meta["root"] = root
    return issues, meta


# ----------------------------------------------------------------------------- in-page JS (Chromium)

SKELETON = ('<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;padding:0;background:#fff}'
            'svg{display:block}</style></head><body></body></html>')

JS_MOUNT = r"""({ svgText, w, h }) => {
  const doc = new DOMParser().parseFromString(svgText, 'image/svg+xml');
  const pe = doc.querySelector('parsererror');
  if (pe) return 'XML parse error: ' + pe.textContent.slice(0, 300);
  const svg = document.importNode(doc.documentElement, true);
  document.body.innerHTML = '';
  document.body.appendChild(svg);
  svg.style.width = w + 'px'; svg.style.height = h + 'px';
  return null;
}"""

JS_ANALYZE = r"""async (opt) => {
  const svg = document.querySelector('body > svg');
  const issues = [];
  const R = v => Math.round(v * 10) / 10;
  const add = (sev, code, msg, b) => issues.push({ sev, code, msg, bbox: b ? [R(b.x0), R(b.y0), R(b.x1), R(b.y1)] : null });
  const vbv = svg.viewBox && svg.viewBox.baseVal;
  let VB;
  if (vbv && vbv.width > 0 && vbv.height > 0) VB = { x0: vbv.x, y0: vbv.y, x1: vbv.x + vbv.width, y1: vbv.y + vbv.height };
  else { const r = svg.getBoundingClientRect(); VB = { x0: 0, y0: 0, x1: r.width, y1: r.height }; }
  const VW = VB.x1 - VB.x0, VH = VB.y1 - VB.y0;
  const rootInv = svg.getScreenCTM().inverse();
  const matOf = el => { const s = el.getScreenCTM(); return s ? rootInv.multiply(s) : null; };
  const tp = (m, x, y) => { const p = new DOMPoint(x, y).matrixTransform(m); return [p.x, p.y]; };
  const bboxPts = pts => { let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const [x, y] of pts) { if (x < x0) x0 = x; if (y < y0) y0 = y; if (x > x1) x1 = x; if (y > y1) y1 = y; } return { x0, y0, x1, y1 }; };
  const corners = b => [[b.x, b.y], [b.x + b.width, b.y], [b.x, b.y + b.height], [b.x + b.width, b.y + b.height]];
  const area = b => Math.max(0, b.x1 - b.x0) * Math.max(0, b.y1 - b.y0);
  const isect = (a, b) => ({ x0: Math.max(a.x0, b.x0), y0: Math.max(a.y0, b.y0), x1: Math.min(a.x1, b.x1), y1: Math.min(a.y1, b.y1) });
  const overlaps = (a, b, e = 0) => a.x0 < b.x1 - e && b.x0 < a.x1 - e && a.y0 < b.y1 - e && b.y0 < a.y1 - e;
  const inBox = (b, x, y, p = 0) => x >= b.x0 - p && x <= b.x1 + p && y >= b.y0 - p && y <= b.y1 + p;
  const grow = (b, p) => ({ x0: b.x0 - p, y0: b.y0 - p, x1: b.x1 + p, y1: b.y1 + p });
  const union = (a, b) => ({ x0: Math.min(a.x0, b.x0), y0: Math.min(a.y0, b.y0), x1: Math.max(a.x1, b.x1), y1: Math.max(a.y1, b.y1) });
  const near = (p, q, d) => Math.hypot(p[0] - q[0], p[1] - q[1]) <= d;
  const SKIP = 'defs, marker, symbol, clipPath, mask, pattern, title, desc, metadata, [data-lint="ignore"], #__lint_overlay';
  const shown = el => { if (el.closest(SKIP)) return false;
    for (let a = el; a && a !== svg; a = a.parentElement) { const cs = getComputedStyle(a);
      if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false; } return true; };
  const label = el => {
    let s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    else {
      const c = (el.getAttribute('class') || '').trim(); if (c) s += '.' + c.split(/\s+/).join('.');
      const g = el.parentElement && el.parentElement.closest('[id]'); if (g && g !== svg && svg.contains(g)) s += ' in #' + g.id;
    }
    if (el.tagName.toLowerCase() === 'text') { const t = (el.textContent || '').replace(/\s+/g, ' ').trim(); s += ' "' + (t.length > 36 ? t.slice(0, 35) + '…' : t) + '"'; }
    return s;
  };
  const scaleOf = m => Math.sqrt(Math.abs(m.a * m.d - m.b * m.c)) || 1;
  const paintOn = v => !!v && v !== 'none' && !/rgba\([^)]*,\s*0\)$/.test(v);
  const isEdgeEl = (el, cs) => cs.markerEnd !== 'none' || cs.markerStart !== 'none' || el.matches('.edge, .arrow, .connector, [data-role="edge"]');

  // ---- shapes (filled geometry + <use>/<image>)
  const shapes = [];
  for (const el of svg.querySelectorAll('rect, circle, ellipse, polygon, path, use, image')) {
    if (!shown(el) || el.closest('.tex-math')) continue;
    const tag = el.tagName.toLowerCase();
    const cs = getComputedStyle(el);
    const geom = !(tag === 'use' || tag === 'image');
    if (geom && (isEdgeEl(el, cs) || !(paintOn(cs.fill) && parseFloat(cs.fillOpacity) * parseFloat(cs.opacity) > 0.04))) continue;
    let bb; try { bb = el.getBBox(); } catch (e) { continue; }
    if (!(bb.width > 0 || bb.height > 0)) continue;
    const m = matOf(el); if (!m) continue;
    const box = bboxPts(corners(bb).map(([x, y]) => tp(m, x, y)));
    const sw = paintOn(cs.stroke) ? (parseFloat(cs.strokeWidth) || 0) * scaleOf(m) : 0;
    shapes.push({ el, tag, geom, box, vis: grow(box, sw / 2), m, inv: m.inverse(), area: area(box), name: label(el), bg: area(box) >= 0.9 * VW * VH });
  }
  const inside = (S, x, y) => {
    if (!inBox(S.box, x, y)) return false;
    if (!S.geom) return true;
    try { const [lx, ly] = tp(S.inv, x, y); return S.el.isPointInFill(new DOMPoint(lx, ly)); } catch (e) { return true; }
  };

  // ---- texts with ink boxes (canvas metrics per glyph)
  const cvs = document.createElement('canvas').getContext('2d');
  const mcache = new Map();
  const fontStr = cs => `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
  const ink = (ch, font) => { const k = font + '\u0000' + ch; let v = mcache.get(k);
    if (!v) { cvs.font = font; const mt = cvs.measureText(ch); v = { a: mt.actualBoundingBoxAscent, d: mt.actualBoundingBoxDescent }; mcache.set(k, v); } return v; };
  const charsOf = (t, mode) => {
    const raw = []; const tw = document.createTreeWalker(t, NodeFilter.SHOW_TEXT); let nd;
    while ((nd = tw.nextNode())) { if (nd.parentElement.closest('title, desc')) continue; for (let i = 0; i < nd.data.length; i++) raw.push([nd.data[i], nd.parentElement]); }
    if (getComputedStyle(t).whiteSpace.startsWith('pre') || t.getAttribute('xml:space') === 'preserve') return raw;
    const out = []; let prevSp = true;
    for (let [c, e] of raw) {
      if (c === '\n' || c === '\r') { if (mode === 1) continue; c = ' '; }
      if (c === '\t') c = ' ';
      if (c === ' ') { if (prevSp) continue; prevSp = true; } else prevSp = false;
      out.push([c, e]);
    }
    while (out.length && out[out.length - 1][0] === ' ') out.pop();
    return out;
  };
  const texts = [];
  for (const t of svg.querySelectorAll('text')) {
    if (!shown(t)) continue;
    let n = 0; try { n = t.getNumberOfChars(); } catch (e) {}
    if (!n) continue;
    let chars = charsOf(t, 0); if (chars.length !== n) chars = charsOf(t, 1);
    const exact = chars.length === n;
    const m = matOf(t); if (!m) continue;
    const pts = []; let minFs = Infinity; let base = null;
    for (let i = 0; i < n; i++) {
      const c = exact ? chars[i][0] : 'x';
      if (c === ' ') continue;
      let ext, pos; try { ext = t.getExtentOfChar(i); pos = t.getStartPositionOfChar(i); } catch (e) { continue; }
      if (!ext || (ext.width === 0 && ext.height === 0)) continue;
      const fe = exact ? chars[i][1] : t; const cs = getComputedStyle(fe);
      minFs = Math.min(minFs, parseFloat(cs.fontSize));
      let top, bot;
      if (exact) { const k = ink(c, fontStr(cs)); if (k.a + k.d <= 0.01) continue; top = pos.y - k.a; bot = pos.y + k.d; }
      else { top = ext.y + 0.2 * ext.height; bot = ext.y + 0.8 * ext.height; }
      if (base === null) base = tp(m, pos.x, pos.y)[1];
      pts.push(tp(m, ext.x, top), tp(m, ext.x + ext.width, top), tp(m, ext.x, bot), tp(m, ext.x + ext.width, bot));
    }
    if (!pts.length) continue;
    const box = bboxPts(pts);
    texts.push({ el: t, box, fs: minFs * scaleOf(m), base, name: label(t), cx: (box.x0 + box.x1) / 2, cy: (box.y0 + box.y1) / 2,
      onEdge: t.matches('.on-edge'), line: t.closest('.tex-line') });
  }
  // ---- LaTeX math groups: one text box each (ink of the glyphs), base size and script size from the typesetter
  const maths = [];
  for (const g of svg.querySelectorAll('g.tex-math')) {
    if (!shown(g)) continue;
    const pm = matOf(g.parentElement), m = matOf(g); if (!pm || !m) continue;
    let bb; try { bb = g.getBBox(); } catch (e) { continue; }
    if (!(bb.width > 0 || bb.height > 0)) continue;
    const box = bboxPts(corners(bb).map(([x, y]) => tp(m, x, y)));
    const ps = scaleOf(pm), d = g.dataset;
    const tex = (d.tex || '').replace(/\s+/g, ' ');
    const T = { el: g, box, fs: parseFloat(d.size) * ps, script: parseFloat(d.scriptSize) * ps, base: tp(pm, parseFloat(d.x), parseFloat(d.y))[1],
      name: 'math "$' + (tex.length > 34 ? tex.slice(0, 33) + '…' : tex) + '$"', cx: (box.x0 + box.x1) / 2, cy: (box.y0 + box.y1) / 2,
      onEdge: g.matches('.on-edge') || !!g.closest('.on-edge'), line: g.closest('.tex-line'), math: true };
    texts.push(T); maths.push(T);
  }

  // ---- connectors
  const edges = [];
  for (const el of svg.querySelectorAll('path, line, polyline')) {
    if (!shown(el)) continue;
    const cs = getComputedStyle(el);
    if (!isEdgeEl(el, cs)) continue;
    const m = matOf(el); if (!m) continue;
    let L = 0; try { L = el.getTotalLength(); } catch (e) { continue; }
    if (!(L > 0)) continue;
    const N = Math.max(2, Math.ceil(L / opt.step));
    const pts = []; for (let k = 0; k <= N; k++) { const p = el.getPointAtLength(L * k / N); pts.push(tp(m, p.x, p.y)); }
    const sc = scaleOf(m), sw = (parseFloat(cs.strokeWidth) || 0) * sc, box = bboxPts(pts), name = label(el);
    if (el.tagName.toLowerCase() !== 'line' && paintOn(cs.fill) && parseFloat(cs.fillOpacity) > 0.04)
      add('error', 'edge-filled', `${name} is a connector but has fill ${cs.fill}; add fill="none" (it renders as a filled wedge)`, box);
    if (!paintOn(cs.stroke)) continue;
    edges.push({ el, name, pts, L: L * sc, box, vis: grow(box, sw / 2), start: pts[0], end: pts[pts.length - 1], mEnd: cs.markerEnd !== 'none' && !el.closest('.legend') });
  }

  // ---- canvas bounds
  const outBy = b => Math.max(VB.x0 - b.x0, VB.y0 - b.y0, b.x1 - VB.x1, b.y1 - VB.y1);
  const bounds = (b, name) => { const o = outBy(b);
    if (o > 0.5) add('error', 'out-of-bounds', `${name} extends ${R(o)}u beyond the canvas`, b);
    else if (-o < opt.edgeMargin) add('warn', 'near-edge', `${name} is only ${R(Math.max(0, -o))}u from the canvas edge (want >= ${opt.edgeMargin}u)`, b); };
  for (const S of shapes) if (!S.bg) bounds(S.vis, S.name);
  for (const T of texts) bounds(T.box, T.name);
  for (const E of edges) bounds(E.vis, E.name);

  // ---- printed font size
  for (const T of texts) {
    const p = T.fs * opt.targetPt / VW;
    if (p < opt.errPt - 1e-6) add('error', 'font-too-small', `${T.name}: ${R(T.fs)}u = ${p.toFixed(1)}pt at ${opt.targetName} width (min ${opt.errPt}pt)`, T.box);
    else if (p < opt.minPt - 1e-6) add('warn', 'font-small', `${T.name}: ${R(T.fs)}u = ${p.toFixed(1)}pt at ${opt.targetName} width (want >= ${opt.minPt}pt)`, T.box);
  }
  const mathInfo = [];
  for (const T of maths) {
    const k = opt.targetPt / VW, p = T.fs * k, sp = T.script * k;
    mathInfo.push({ tex: T.el.dataset.tex, pt: Math.round(p * 100) / 100, scriptPt: Math.round(sp * 100) / 100, hasScripts: /[_^]|\\(frac|sum|prod|int|lim|sqrt)/.test(T.el.dataset.tex || '') });
    if (!mathInfo[mathInfo.length - 1].hasScripts) continue;
    if (sp < opt.mathScriptErrPt - 0.01) add('error', 'math-script-too-small', `${T.name}: scripts print at ${sp.toFixed(2)}pt (min ${opt.mathScriptErrPt}pt). Raise the base size or declare larger script sizes (\\DeclareMathSizes); never shrink or fake scripts`, T.box);
    else if (sp < opt.minPt - 0.01) add('warn', 'math-script-small', `${T.name}: scripts print at ${sp.toFixed(2)}pt (LaTeX script size for ${p.toFixed(1)}pt text; want >= ${opt.minPt}pt where space allows)`, T.box);
  }
  // math baseline = baseline of the sans text on the same line
  for (const T of maths) {
    if (!T.line) continue;
    for (const U of texts) {
      if (U.math || U.line !== T.line || U.base === null) continue;
      const d = Math.abs(U.base - T.base) * opt.targetPt / VW;
      if (d > 0.2) add('warn', 'math-baseline', `${T.name} sits ${d.toFixed(2)}pt off the baseline of ${U.name}`, union(T.box, U.box));
    }
  }

  // ---- text inside its container
  const solids = shapes.filter(S => !S.bg && S.geom);
  const ring = b => { const xs = [0, .25, .5, .75, 1].map(t => b.x0 + (b.x1 - b.x0) * t), ys = [0, .5, 1].map(t => b.y0 + (b.y1 - b.y0) * t);
    const p = []; for (const x of xs) p.push([x, b.y0], [x, b.y1]); for (const y of ys) p.push([b.x0, y], [b.x1, y]); return p; };
  for (const T of texts) {
    const ta = area(T.box);
    const chain = solids.filter(S => S.area > ta * 1.15 && inside(S, T.cx, T.cy)).sort((a, b) => a.area - b.area);
    T.chain = new Set(chain);
    const C = chain[0];
    if (!C) continue;
    T.container = C;
    const bad = ring(T.box).filter(([x, y]) => !inside(C, x, y));
    if (bad.length) {
      const sides = new Set();
      for (const [x, y] of bad) { if (x <= T.box.x0 + 1e-6) sides.add('left'); if (x >= T.box.x1 - 1e-6) sides.add('right'); if (y <= T.box.y0 + 1e-6) sides.add('top'); if (y >= T.box.y1 - 1e-6) sides.add('bottom'); }
      add('error', 'text-overflow', `${T.name} sticks out of its container ${C.name} (${[...sides].join('/')} side)`, T.box);
      continue;
    }
    let clear = 0;
    for (const p of [0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 6]) { if (ring(grow(T.box, p)).every(([x, y]) => inside(C, x, y))) clear = p; else break; }
    if (clear < opt.minPad) add('warn', 'tight-padding', `${T.name} is only ~${clear}u from the border of ${C.name} (want >= ${opt.minPad}u)`, T.box);
  }

  // ---- text vs text
  for (let i = 0; i < texts.length; i++) for (let j = i + 1; j < texts.length; j++) {
    const A = texts[i], B = texts[j];
    if (A.el.contains(B.el) || B.el.contains(A.el) || (A.line && A.line === B.line)) continue;
    const I = isect(A.box, B.box);
    if (I.x1 - I.x0 > 0.3 && I.y1 - I.y0 > 0.3) add('error', 'text-overlap', `${A.name} overlaps ${B.name}`, union(A.box, B.box));
    else if (overlaps(grow(A.box, opt.textGap / 2), grow(B.box, opt.textGap / 2))) add('warn', 'text-crowded', `${A.name} and ${B.name} are less than ${opt.textGap}u apart`, union(A.box, B.box));
  }

  // ---- text vs foreign shapes
  for (const T of texts) for (const S of shapes) {
    if (S.bg || (T.chain && T.chain.has(S)) || !overlaps(S.box, T.box, 0.2)) continue;
    if (T.onEdge && S.el.matches('.on-edge')) continue;
    let hit = null;
    for (let gx = 0; gx <= 6 && !hit; gx++) for (let gy = 0; gy <= 2 && !hit; gy++) {
      const x = T.box.x0 + (T.box.x1 - T.box.x0) * gx / 6, y = T.box.y0 + (T.box.y1 - T.box.y0) * gy / 2;
      if (inside(S, x, y)) hit = [x, y]; }
    if (hit) add('warn', 'text-over-shape', `${T.name} overlaps ${S.name}`, isect(T.box, S.box));
  }

  // ---- connectors vs shapes / texts
  for (const E of edges) {
    const ends = [E.start, E.end];
    const exempt = new Set(shapes.filter(S => ends.some(([x, y]) => inBox(grow(S.vis, 4), x, y))));
    const N = E.pts.length - 1, sAt = k => E.L * k / N, mid = k => sAt(k) >= opt.endSkip && sAt(k) <= E.L - opt.endSkip;
    for (const S of shapes) {
      if (S.bg || exempt.has(S) || S.el.matches('.on-edge') || !overlaps(E.box, S.box, -0.5)) continue;
      for (let k = 0; k <= N; k++) { if (!mid(k)) continue; const [x, y] = E.pts[k];
        if (inside(S, x, y)) { add('warn', 'edge-through-shape', `${E.name} runs through ${S.name}`, { x0: x - 5, y0: y - 5, x1: x + 5, y1: y + 5 }); break; } }
    }
    for (const T of texts) {
      if (T.onEdge || !overlaps(grow(E.box, 1.5), T.box)) continue;
      const tb = grow(T.box, 1);
      for (let k = 0; k <= N; k++) { if (!mid(k)) continue; const [x, y] = E.pts[k];
        if (inBox(tb, x, y)) { add('warn', 'edge-through-text', `${E.name} crosses or touches ${T.name}`, T.box); break; } }
    }
  }

  // ---- connector vs connector
  const segX = (p1, p2, p3, p4) => {
    const d = (p2[0] - p1[0]) * (p4[1] - p3[1]) - (p2[1] - p1[1]) * (p4[0] - p3[0]);
    if (Math.abs(d) < 1e-9) return null;
    const t = ((p3[0] - p1[0]) * (p4[1] - p3[1]) - (p3[1] - p1[1]) * (p4[0] - p3[0])) / d;
    const u = ((p3[0] - p1[0]) * (p2[1] - p1[1]) - (p3[1] - p1[1]) * (p2[0] - p1[0])) / d;
    return (t >= 0 && t <= 1 && u >= 0 && u <= 1) ? [p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1])] : null; };
  for (let i = 0; i < edges.length; i++) for (let j = i + 1; j < edges.length; j++) {
    const A = edges[i], B = edges[j];
    if (!overlaps(grow(A.box, 2), grow(B.box, 2))) continue;
    const ends = [A.start, A.end, B.start, B.end], nearEnd = p => ends.some(q => near(p, q, 6));
    let cross = null;
    outer: for (let a = 0; a < A.pts.length - 1; a++) for (let b = 0; b < B.pts.length - 1; b++) {
      const X = segX(A.pts[a], A.pts[a + 1], B.pts[b], B.pts[b + 1]); if (X && !nearEnd(X)) { cross = X; break outer; } }
    if (cross) add('warn', 'edge-crossing', `${A.name} crosses ${B.name}`, { x0: cross[0] - 5, y0: cross[1] - 5, x1: cross[0] + 5, y1: cross[1] + 5 });
    const shared = near(A.start, B.start, 2) || near(A.end, B.end, 2) || near(A.start, B.end, 2) || near(A.end, B.start, 2);
    if (!shared) {
      const stepA = A.L / (A.pts.length - 1); let run = 0, best = 0, at = null;
      for (const p of A.pts) { if (nearEnd(p)) { run = 0; continue; }
        if (B.pts.some(q => near(p, q, 1.5))) { run += stepA; if (run > best) { best = run; at = p; } } else run = 0; }
      if (best >= 12) add('warn', 'edge-overlap', `${A.name} runs on top of ${B.name} for ~${R(best)}u`, { x0: at[0] - 6, y0: at[1] - 6, x1: at[0] + 6, y1: at[1] + 6 });
    }
  }

  // ---- arrowheads must land on a border
  for (const E of edges) {
    if (!E.mEnd) continue;
    const n = E.pts.length; const [ex, ey] = E.end; let k = n - 2;
    while (k > 0 && near(E.pts[k], E.end, 1.5)) k--;
    let dx = ex - E.pts[k][0], dy = ey - E.pts[k][1]; const dl = Math.hypot(dx, dy) || 1; dx /= dl; dy /= dl;
    const lo = -3, hi = opt.tipOffset + 6; let best = null;
    for (const S of shapes) {
      if (S.bg || !inBox(grow(S.vis, hi + 2), ex, ey)) continue;
      let prev = inside(S, ex + dx * lo, ey + dy * lo);
      for (let s = lo + 0.5; s <= hi + 1e-9; s += 0.5) { const cur = inside(S, ex + dx * s, ey + dy * s);
        if (cur !== prev) { const at = s - 0.25; if (best === null || Math.abs(at - opt.tipOffset) < Math.abs(best - opt.tipOffset)) best = at; break; } prev = cur; }
    }
    const tip = [ex + dx * opt.tipOffset, ey + dy * opt.tipOffset], tb = { x0: tip[0] - 5, y0: tip[1] - 5, x1: tip[0] + 5, y1: tip[1] + 5 };
    if (best === null) add('warn', 'arrow-tip-gap', `${E.name}: arrowhead ends in open space (no shape border within ${hi}u of the path end)`, tb);
    else if (Math.abs(best - opt.tipOffset) > 1.5) {
      if (best > opt.tipOffset) add('warn', 'arrow-tip-gap', `${E.name}: target border is ${R(best)}u past the path end (expected ${opt.tipOffset}u) - visible gap at the arrowhead`, tb);
      else add('warn', 'arrow-tip-overlap', `${E.name}: target border is only ${R(best)}u past the path end (expected ${opt.tipOffset}u) - arrowhead digs into the target`, tb);
    }
  }

  // ---- near-misalignment (things that are almost, but not exactly, aligned)
  const al = [];
  const bx = shapes.filter(S => !S.bg && Math.min(S.box.x1 - S.box.x0, S.box.y1 - S.box.y0) >= 8 && !S.el.closest('.stack, .cuboid, .badge, .legend, [class*="mini"]'));
  for (let i = 0; i < bx.length; i++) for (let j = i + 1; j < bx.length; j++) {
    const a = bx[i].box, b = bx[j].box, ha = a.y1 - a.y0, hb = b.y1 - b.y0, wa = a.x1 - a.x0, wb = b.x1 - b.x0;
    const xo = Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0), yo = Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0);
    if (xo < 0 && Math.max(ha, hb) / Math.min(ha, hb) <= 2) { const d = Math.abs((a.y0 + a.y1) / 2 - (b.y0 + b.y1) / 2);
      if (d > 0.5 && d <= opt.alignTol) al.push([d, `${bx[j].name} vs ${bx[i].name}: vertical centres differ by ${R(d)}u`, b]); }
    if (yo < 0 && Math.max(wa, wb) / Math.min(wa, wb) <= 2) { const d = Math.abs((a.x0 + a.x1) / 2 - (b.x0 + b.x1) / 2);
      if (d > 0.5 && d <= opt.alignTol) al.push([d, `${bx[j].name} vs ${bx[i].name}: horizontal centres differ by ${R(d)}u`, b]); }
  }
  for (let i = 0; i < texts.length; i++) for (let j = i + 1; j < texts.length; j++) {
    const A = texts[i], B = texts[j];
    if (Math.abs(A.fs - B.fs) > 0.1 || A.base === null || B.base === null) continue;
    const ca = A.container ? A.container.area : VW * VH, cb = B.container ? B.container.area : VW * VH;
    if (Math.max(ca, cb) / Math.max(1, Math.min(ca, cb)) > 2.5) continue;   // e.g. edge label vs module label
    const xo = Math.min(A.box.x1, B.box.x1) - Math.max(A.box.x0, B.box.x0), d = Math.abs(A.base - B.base);
    if (xo < 0 && d > 0.5 && d <= 2.5) al.push([d, `${B.name} vs ${A.name}: baselines differ by ${R(d)}u`, B.box]);
  }
  al.sort((p, q) => p[0] - q[0]).slice(0, 10).forEach(([d, msg, b]) => add('warn', 'near-misaligned', msg, b));

  const sizes = [...new Set(texts.map(T => Math.round(T.fs * 2) / 2))].sort((a, b) => a - b);
  if (sizes.length > 5) add('warn', 'font-tiers', `${sizes.length} distinct font sizes (${sizes.join(', ')}u); use 3-5 tiers for a clear hierarchy`, null);
  return { issues, stats: { vb: [VB.x0, VB.y0, VW, VH], nTexts: texts.length, nShapes: shapes.length, nEdges: edges.length, fontSizes: sizes, math: mathInfo } };
}"""

JS_MEASURE = r"""({ items }) => {
  const svg = document.querySelector('body > svg');
  const rootInv = svg.getScreenCTM().inverse();
  const out = [];
  for (const it of items) {
    const t = svg.querySelector('[data-tm-i="' + it.i + '"]');
    if (!t) { out.push(null); continue; }
    const cs = getComputedStyle(t);
    const widths = it.segs.map(s => {
      const c = t.cloneNode(false);
      for (const a of ['id', 'display', 'data-tm-i', 'data-tex', 'transform']) c.removeAttribute(a);
      c.style.display = 'inline'; c.style.visibility = 'visible';
      c.textContent = s; t.parentNode.insertBefore(c, t);
      let w = 0; try { w = c.getComputedTextLength(); } catch (e) {}
      c.remove(); return w; });
    const p = t.parentNode, sm = p.getScreenCTM ? p.getScreenCTM() : null;
    let scale = 1;
    if (sm) { const m = rootInv.multiply(sm); scale = Math.sqrt(Math.abs(m.a * m.d - m.b * m.c)) || 1; }
    out.push({ widths, fs: parseFloat(cs.fontSize), fill: cs.fill, anchor: cs.textAnchor, scale });
  }
  return out;
}"""

JS_OVERLAY = r"""({ issues, grid }) => {
  const svg = document.querySelector('body > svg');
  const NS = 'http://www.w3.org/2000/svg';
  const vb = svg.viewBox && svg.viewBox.baseVal;
  const r = svg.getBoundingClientRect();
  const X0 = vb && vb.width ? vb.x : 0, Y0 = vb && vb.width ? vb.y : 0, W = vb && vb.width ? vb.width : r.width, H = vb && vb.width ? vb.height : r.height;
  const g = document.createElementNS(NS, 'g'); g.setAttribute('id', '__lint_overlay');
  g.setAttribute('font-family', "'DejaVu Sans Mono', Menlo, Consolas, monospace");
  const mk = (tag, at) => { const e = document.createElementNS(NS, tag); for (const k in at) e.setAttribute(k, at[k]); g.appendChild(e); return e; };
  const fs = Math.max(6, W / 150);
  for (let x = Math.ceil(X0 / grid) * grid; x <= X0 + W + 1e-6; x += grid) {
    const major = Math.round(x / grid) % 2 === 0;
    mk('line', { x1: x, y1: Y0, x2: x, y2: Y0 + H, stroke: '#0FA3B1', 'stroke-width': major ? 0.6 : 0.35, 'stroke-opacity': major ? 0.6 : 0.35 });
    if (major) mk('text', { x: x + 1.5, y: Y0 + fs + 1, 'font-size': fs, fill: '#0B7A85' }).textContent = String(Math.round(x));
  }
  for (let y = Math.ceil(Y0 / grid) * grid; y <= Y0 + H + 1e-6; y += grid) {
    const major = Math.round(y / grid) % 2 === 0;
    mk('line', { x1: X0, y1: y, x2: X0 + W, y2: y, stroke: '#0FA3B1', 'stroke-width': major ? 0.6 : 0.35, 'stroke-opacity': major ? 0.6 : 0.35 });
    if (major && y > Y0) mk('text', { x: X0 + 1.5, y: y - 1.5, 'font-size': fs, fill: '#0B7A85' }).textContent = String(Math.round(y));
  }
  for (const it of issues) {
    if (!it.bbox || it.sev === 'info') continue;
    const [a, b, c, d] = it.bbox, col = it.sev === 'error' ? '#E3005B' : '#F07800';
    mk('rect', { x: a - 1.5, y: b - 1.5, width: Math.max(3, c - a + 3), height: Math.max(3, d - b + 3), fill: col, 'fill-opacity': 0.08,
      stroke: col, 'stroke-width': 1.2, 'stroke-dasharray': it.sev === 'error' ? 'none' : '3 2' });
    const tw = it.tag.length * fs * 0.62 + 4, above = b - 1.5 - fs - 3 >= Y0, ty = above ? b - 1.5 - fs - 3 : d + 1.5;
    mk('rect', { x: a - 1.5, y: ty, width: tw, height: fs + 3, fill: col, rx: 1.5 });
    mk('text', { x: a + 0.5, y: ty + fs, 'font-size': fs, fill: '#FFFFFF', 'font-weight': 700 }).textContent = it.tag;
  }
  svg.appendChild(g);
}"""

NODE_DRIVER = r"""
const fs = require('fs');
let chromium;
try { ({ chromium } = require('playwright')); } catch (e) {
  try { ({ chromium } = require('playwright-core')); } catch (e2) { console.error('NO_PLAYWRIGHT'); process.exit(3); } }
const MOUNT = __MOUNT__;
const ANALYZE = __ANALYZE__;
const OVERLAY = __OVERLAY__;
const MEASURE = __MEASURE__;
const SKELETON = __SKELETON__;
function tagIssues(issues) { const c = { error: 0, warn: 0, info: 0 };
  for (const it of issues) { c[it.sev] = (c[it.sev] || 0) + 1; it.tag = (it.sev === 'error' ? 'E' : it.sev === 'warn' ? 'W' : 'I') + c[it.sev]; } }
(async () => {
  const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const svgText = fs.readFileSync(cfg.svg, 'utf8');
  const pdfText = cfg.pdfSvg ? fs.readFileSync(cfg.pdfSvg, 'utf8') : svgText;
  const browser = await chromium.launch(cfg.executablePath ? { executablePath: cfg.executablePath } : {});
  const res = { files: {} };
  const open = async (scale, w, h, text) => {
    const ctx = await browser.newContext({ viewport: { width: Math.ceil(w), height: Math.ceil(h) }, deviceScaleFactor: scale });
    const page = await ctx.newPage();
    await page.setContent(SKELETON);
    const err = await page.evaluate(MOUNT, { svgText: text || svgText, w, h });
    if (err) throw new Error(err);
    await page.evaluate(() => document.fonts.ready.then(() => true));
    return { ctx, page };
  };
  try {
    const W = cfg.cssW, H = cfg.cssH, clip = { x: 0, y: 0, width: W, height: H };
    if (cfg.measure) { const { ctx, page } = await open(1, W, H);
      res.measure = await page.evaluate(MEASURE, { items: cfg.measure }); await ctx.close();
      process.stdout.write(JSON.stringify(res)); return; }
    { const { ctx, page } = await open(cfg.pngScale || 1, W, H);
      if (cfg.analyze) res.analysis = await page.evaluate(ANALYZE, cfg.analyzeOpts);
      if (cfg.png) { await page.screenshot({ path: cfg.png, clip }); res.files.png = cfg.png; }
      await ctx.close(); }
    const issues = (cfg.staticIssues || []).concat(res.analysis ? res.analysis.issues : []);
    tagIssues(issues); res.issues = issues;
    if (cfg.preview) { const { ctx, page } = await open(cfg.previewScale, W, H);
      await page.screenshot({ path: cfg.preview, clip }); res.files.preview = cfg.preview; await ctx.close(); }
    if (cfg.debug) { const { ctx, page } = await open(cfg.debugScale, W, H);
      await page.evaluate(OVERLAY, { issues, grid: cfg.grid });
      await page.screenshot({ path: cfg.debug, clip }); res.files.debug = cfg.debug; await ctx.close(); }
    if (cfg.pdf) { const { ctx, page } = await open(1, cfg.pdfW, cfg.pdfH, pdfText);
      await page.addStyleTag({ content: `@page { size: ${cfg.pdfW}px ${cfg.pdfH}px; margin: 0 } html, body { width: ${cfg.pdfW}px; height: ${cfg.pdfH}px; overflow: hidden }` });
      await page.pdf({ path: cfg.pdf, width: cfg.pdfW + 'px', height: cfg.pdfH + 'px', printBackground: true, preferCSSPageSize: true,
        margin: { top: '0px', right: '0px', bottom: '0px', left: '0px' }, pageRanges: '1' });
      res.files.pdf = cfg.pdf; await ctx.close(); }
  } finally { await browser.close(); }
  process.stdout.write(JSON.stringify(res));
})().catch(e => { console.error(String((e && e.stack) || e)); process.exit(2); });
"""

# ----------------------------------------------------------------------------- backends


def detect_backends(chromium_path=None):
    found = {}
    for name, exe in (("rsvg", "rsvg-convert"), ("resvg", "resvg"), ("inkscape", "inkscape")):
        p = shutil.which(exe)
        if p:
            found[name] = p
    try:
        import cairosvg  # noqa: F401
        found["cairosvg"] = "python module cairosvg"
    except Exception:
        pass
    chrom = None
    try:
        import playwright.sync_api  # noqa: F401
        chrom = ("py", "python playwright")
    except Exception:
        node = shutil.which("node")
        if node:
            try:
                r = run([node, "-e", "try{require.resolve('playwright')}catch(e){require.resolve('playwright-core')}"], timeout=30)
                if r.returncode == 0:
                    chrom = ("node", f"node playwright ({node})")
            except Exception:
                pass
    if chrom:
        found["chromium"] = chrom
    return found


def run_chromium(kind, cfg, svg_text):
    """Execute the Chromium job. Returns the result dict (raises RuntimeError on failure)."""
    if kind == "node":
        js = (NODE_DRIVER.replace("__MOUNT__", JS_MOUNT).replace("__ANALYZE__", JS_ANALYZE)
              .replace("__OVERLAY__", JS_OVERLAY).replace("__MEASURE__", JS_MEASURE).replace("__SKELETON__", json.dumps(SKELETON)))
        with tempfile.TemporaryDirectory(prefix="mlfig_") as td:
            drv, cfgp = Path(td) / "driver.js", Path(td) / "cfg.json"
            drv.write_text(js, encoding="utf-8")
            if cfg.get("pdfSvgText") is not None:
                (Path(td) / "pdf.svg").write_text(cfg["pdfSvgText"], encoding="utf-8")
                cfg = dict(cfg, pdfSvg=str(Path(td) / "pdf.svg"), pdfSvgText=None)
            if cfg.get("svgText") is not None:
                (Path(td) / "in.svg").write_text(cfg["svgText"], encoding="utf-8")
                cfg = dict(cfg, svg=str(Path(td) / "in.svg"), svgText=None)
            cfgp.write_text(json.dumps(cfg), encoding="utf-8")
            r = run([shutil.which("node"), str(drv), str(cfgp)], timeout=300)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout).strip()[-1500:])
        return json.loads(r.stdout)
    # python playwright
    from playwright.sync_api import sync_playwright
    res = {"files": {}}
    with sync_playwright() as p:
        kw = {"executable_path": cfg["executablePath"]} if cfg.get("executablePath") else {}
        browser = p.chromium.launch(**kw)
        try:
            def open_(scale, w, h, text=None):
                ctx = browser.new_context(viewport={"width": math.ceil(w), "height": math.ceil(h)}, device_scale_factor=scale)
                page = ctx.new_page()
                page.set_content(SKELETON)
                err = page.evaluate(JS_MOUNT, {"svgText": text or svg_text, "w": w, "h": h})
                if err:
                    raise RuntimeError(err)
                page.evaluate("() => document.fonts.ready.then(() => true)")
                return ctx, page
            W, H = cfg["cssW"], cfg["cssH"]
            clip = {"x": 0, "y": 0, "width": W, "height": H}
            if cfg.get("measure"):
                ctx, page = open_(1, W, H)
                res["measure"] = page.evaluate(JS_MEASURE, {"items": cfg["measure"]})
                ctx.close()
                return res
            ctx, page = open_(cfg.get("pngScale") or 1, W, H)
            if cfg.get("analyze"):
                res["analysis"] = page.evaluate(JS_ANALYZE, cfg["analyzeOpts"])
            if cfg.get("png"):
                page.screenshot(path=cfg["png"], clip=clip)
                res["files"]["png"] = cfg["png"]
            ctx.close()
            issues = list(cfg.get("staticIssues") or []) + (res["analysis"]["issues"] if res.get("analysis") else [])
            tag_issues(issues)
            res["issues"] = issues
            if cfg.get("preview"):
                ctx, page = open_(cfg["previewScale"], W, H)
                page.screenshot(path=cfg["preview"], clip=clip)
                res["files"]["preview"] = cfg["preview"]
                ctx.close()
            if cfg.get("debug"):
                ctx, page = open_(cfg["debugScale"], W, H)
                page.evaluate(JS_OVERLAY, {"issues": issues, "grid": cfg["grid"]})
                page.screenshot(path=cfg["debug"], clip=clip)
                res["files"]["debug"] = cfg["debug"]
                ctx.close()
            if cfg.get("pdf"):
                pw, ph = cfg["pdfW"], cfg["pdfH"]
                ctx, page = open_(1, pw, ph, cfg.get("pdfSvgText"))
                page.add_style_tag(content=f"@page {{ size: {pw}px {ph}px; margin: 0 }} html, body {{ width: {pw}px; height: {ph}px; overflow: hidden }}")
                page.pdf(path=cfg["pdf"], width=f"{pw}px", height=f"{ph}px", print_background=True, prefer_css_page_size=True,
                         margin={"top": "0px", "right": "0px", "bottom": "0px", "left": "0px"}, page_ranges="1")
                res["files"]["pdf"] = cfg["pdf"]
                ctx.close()
        finally:
            browser.close()
    return res


def sized_copy(svg_text, wpt, hpt, td):
    """Copy of the SVG whose root width/height are the physical print size (for PDF backends)."""
    m = re.search(r"<svg\b[^>]*>", svg_text)
    tag = m.group(0)
    new = re.sub(r'\s(width|height)\s*=\s*("[^"]*"|\'[^\']*\')', "", tag)
    new = new[:-1].rstrip("/") + f' width="{wpt:.2f}pt" height="{hpt:.2f}pt"' + (" />" if tag.rstrip().endswith("/>") else ">")
    p = Path(td) / "sized.svg"
    p.write_text(svg_text[:m.start()] + new + svg_text[m.end():], encoding="utf-8")
    return p


def render_cli(backend, svg_path, svg_text, png=None, png_px=None, pdf=None, pdf_pt=None):
    """Render with a non-Chromium backend. Returns dict of written files; raises RuntimeError."""
    files = {}
    with tempfile.TemporaryDirectory(prefix="mlfig_") as td:
        if png:
            w, h = png_px
            if backend == "rsvg":
                cmd = [shutil.which("rsvg-convert"), "-f", "png", "-w", str(w), "-h", str(h), "-o", png, str(svg_path)]
            elif backend == "resvg":
                cmd = [shutil.which("resvg"), "-w", str(w), str(svg_path), png]
            elif backend == "inkscape":
                cmd = [shutil.which("inkscape"), str(svg_path), "--export-type=png", f"--export-filename={png}", f"--export-width={w}"]
            elif backend == "cairosvg":
                import cairosvg
                cairosvg.svg2png(url=str(svg_path), write_to=png, output_width=w, output_height=h)
                cmd = None
            else:
                raise RuntimeError(f"backend {backend} cannot write PNG")
            if cmd:
                r = run(cmd)
                if r.returncode != 0:
                    raise RuntimeError(f"{backend} PNG failed: {(r.stderr or r.stdout).strip()[-800:]}")
            files["png"] = png
        if pdf:
            sized = sized_copy(svg_text, pdf_pt[0], pdf_pt[1], td)
            if backend == "rsvg":
                cmd = [shutil.which("rsvg-convert"), "-f", "pdf", "-o", pdf, str(sized)]
            elif backend == "inkscape":
                cmd = [shutil.which("inkscape"), str(sized), "--export-type=pdf", f"--export-filename={pdf}"]
            elif backend == "cairosvg":
                import cairosvg
                cairosvg.svg2pdf(url=str(sized), write_to=pdf)
                cmd = None
            else:
                raise RuntimeError(f"backend {backend} cannot write PDF")
            if cmd:
                r = run(cmd)
                if r.returncode != 0:
                    raise RuntimeError(f"{backend} PDF failed: {(r.stderr or r.stdout).strip()[-800:]}")
            files["pdf"] = pdf
    return files


# ----------------------------------------------------------------------------- approximate geometry (no Chromium)


class Mat:
    __slots__ = ("a", "b", "c", "d", "e", "f")

    def __init__(self, a=1.0, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0):
        self.a, self.b, self.c, self.d, self.e, self.f = a, b, c, d, e, f

    def __mul__(self, o):
        return Mat(self.a * o.a + self.c * o.b, self.b * o.a + self.d * o.b,
                   self.a * o.c + self.c * o.d, self.b * o.c + self.d * o.d,
                   self.a * o.e + self.c * o.f + self.e, self.b * o.e + self.d * o.f + self.f)

    def ap(self, x, y):
        return (self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f)

    def scale(self):
        return math.sqrt(abs(self.a * self.d - self.b * self.c)) or 1.0


def parse_transform(s):
    m = Mat()
    for name, args in re.findall(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)", s or ""):
        v = [float(t) for t in re.split(r"[\s,]+", args.strip()) if t]
        if name == "matrix" and len(v) == 6:
            t = Mat(*v)
        elif name == "translate":
            t = Mat(e=v[0], f=v[1] if len(v) > 1 else 0.0)
        elif name == "scale":
            t = Mat(a=v[0], d=v[1] if len(v) > 1 else v[0])
        elif name == "rotate":
            a = math.radians(v[0])
            t = Mat(math.cos(a), math.sin(a), -math.sin(a), math.cos(a))
            if len(v) == 3:
                t = Mat(e=v[1], f=v[2]) * t * Mat(e=-v[1], f=-v[2])
        elif name == "skewX":
            t = Mat(c=math.tan(math.radians(v[0])))
        else:
            t = Mat(b=math.tan(math.radians(v[0])))
        m = m * t
    return m


def path_points(d):
    toks = re.findall(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", d or "")
    pts, i, cmd = [], 0, None
    cx = cy = sx = sy = 0.0
    npar = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}
    while i < len(toks):
        t = toks[i]
        if re.fullmatch(r"[A-Za-z]", t):
            cmd = t
            i += 1
            if cmd in "Zz":
                cx, cy = sx, sy
                continue
        if cmd is None:
            break
        n = npar[cmd.upper()]
        if n == 0 or i + n > len(toks):
            i += 1
            continue
        try:
            v = [float(x) for x in toks[i:i + n]]
        except ValueError:
            break
        i += n
        rel = cmd.islower()
        C = cmd.upper()
        if C == "H":
            cx = cx + v[0] if rel else v[0]
            pts.append((cx, cy))
        elif C == "V":
            cy = cy + v[0] if rel else v[0]
            pts.append((cx, cy))
        elif C == "A":
            nx, ny = (cx + v[5], cy + v[6]) if rel else (v[5], v[6])
            pts.append((nx, ny))
            cx, cy = nx, ny
        else:
            pairs = [(v[k] + (cx if rel else 0), v[k + 1] + (cy if rel else 0)) for k in range(0, n, 2)]
            pts.extend(pairs)
            cx, cy = pairs[-1]
            if C == "M":
                sx, sy = cx, cy
                cmd = "l" if rel else "L"
    return pts


def approx_geometry(root, vb, opt):
    """Approximate checks without a browser: rect containers, estimated text widths, bounds, overlaps."""
    issues = []
    rules = []
    for st in root.iter(f"{{{SVG_NS}}}style"):
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", st.text or ""):
            d = dict((k.strip().lower(), v.strip()) for k, v in (p.split(":", 1) for p in body.split(";") if ":" in p))
            for s in sel.split(","):
                rules.append((s.strip(), d))
    inherit_keys = ("font-size", "font-family", "font-weight", "text-anchor", "fill", "stroke", "stroke-width", "visibility", "fill-opacity")

    def style(el, inh):
        st = dict(inh)
        for k in inherit_keys + ("display", "marker-end", "marker-start", "opacity"):
            if el.get(k) is not None:
                st[k] = el.get(k)
        tg = local(el.tag)
        classes = (el.get("class") or "").split()
        for sel, d in rules:
            if sel == tg or sel == "*" or (sel.startswith(".") and sel[1:] in classes) or (
                    "." in sel and sel.split(".", 1)[0] == tg and sel.split(".", 1)[1] in classes):
                st.update(d)
        for p in (el.get("style") or "").split(";"):
            if ":" in p:
                k, v = p.split(":", 1)
                st[k.strip().lower()] = v.strip()
        return st

    def fnum(v, default=0.0):
        try:
            return float(re.sub(r"(px|pt)$", "", str(v).strip()))
        except (TypeError, ValueError):
            return default

    shapes, texts, edges = [], [], []
    skip_tags = {"defs", "marker", "symbol", "clipPath", "mask", "pattern", "title", "desc", "metadata", "style"}

    def box_of(pts, M):
        tp_ = [M.ap(x, y) for x, y in pts]
        xs, ys = [p[0] for p in tp_], [p[1] for p in tp_]
        return [min(xs), min(ys), max(xs), max(ys)]

    def walk(el, M, inh):
        tg = local(el.tag) if isinstance(el.tag, str) else ""
        if tg in skip_tags or el.get("data-lint") == "ignore":
            return
        st = style(el, inh)
        if st.get("display") == "none" or st.get("visibility") == "hidden":
            return
        if el.get("data-tex") == "out":
            st["__line"] = id(el)
        if tg == "g" and "tex-math" in (el.get("class") or "").split():
            try:
                x, y = float(el.get("data-x")), float(el.get("data-y"))
                wd, ht, dp = float(el.get("data-wd")), float(el.get("data-ht")), float(el.get("data-dp"))
                b = box_of([(x, y - ht), (x + wd, y + dp)], M)
                texts.append({"box": b, "fs": float(el.get("data-size")) * M.scale(), "line": st.get("__line"),
                              "name": f'math "${(el.get("data-tex") or "")[:34]}$"',
                              "script": float(el.get("data-script-size")) * M.scale() if re.search(r"[_^]", el.get("data-tex") or "") else None})
            except (TypeError, ValueError):
                pass
            return
        M = M * parse_transform(el.get("transform"))
        filled = (st.get("fill", "black") or "black").lower() not in ("none", "transparent") and fnum(st.get("fill-opacity", 1), 1) > 0.04
        name = tg + (f"#{el.get('id')}" if el.get("id") else "")
        has_marker = bool(st.get("marker-end") or st.get("marker-start"))
        if tg in ("rect", "image", "use"):
            x, y = fnum(el.get("x")), fnum(el.get("y"))
            w, h = fnum(el.get("width"), 0), fnum(el.get("height"), 0)
            if tg == "rect" and el.get("width") == "100%":
                w, h = vb[2], vb[3]
            if w > 0 and h > 0 and (filled or tg != "rect"):
                shapes.append({"box": box_of([(x, y), (x + w, y), (x, y + h), (x + w, y + h)], M), "name": name, "rect": tg == "rect" and M.b == 0 and M.c == 0})
        elif tg in ("circle", "ellipse"):
            cx_, cy_ = fnum(el.get("cx")), fnum(el.get("cy"))
            rx = fnum(el.get("r") or el.get("rx"), 0)
            ry = fnum(el.get("r") or el.get("ry"), 0)
            if filled and rx > 0:
                shapes.append({"box": box_of([(cx_ - rx, cy_ - ry), (cx_ + rx, cy_ + ry)], M), "name": name, "rect": False})
        elif tg in ("polygon", "polyline", "path", "line"):
            if tg == "path":
                pts = path_points(el.get("d"))
            elif tg == "line":
                pts = [(fnum(el.get("x1")), fnum(el.get("y1"))), (fnum(el.get("x2")), fnum(el.get("y2")))]
            else:
                nums = [float(t) for t in re.split(r"[\s,]+", (el.get("points") or "").strip()) if t]
                pts = list(zip(nums[0::2], nums[1::2]))
            if pts:
                b = box_of(pts, M)
                is_edge = has_marker or "edge" in (el.get("class") or "").split()
                if is_edge:
                    edges.append({"box": b, "name": name})
                    if tg == "path" and filled:
                        issues.append(issue("error", "edge-filled", f"{name} is a connector without fill=\"none\" (renders as a filled wedge) (approx.)", b))
                elif filled and tg != "line":
                    shapes.append({"box": b, "name": name, "rect": False})
        elif tg == "text":
            fs = fnum(st.get("font-size", 16), 16)
            anchor = st.get("text-anchor", "start")
            x0 = fnum((el.get("x") or "0").split()[0])
            y0 = fnum((el.get("y") or "0").split()[0])
            chunks, cur = [], {"x": x0, "segs": []}
            cy_ = y0
            curx = x0

            def add_seg(s, st_):
                nonlocal curx
                s = re.sub(r"\s+", " ", s)
                if not s.strip():
                    if s:
                        curx += 0.28 * fnum(st_.get("font-size", fs), fs)
                    return
                f_ = fnum(st_.get("font-size", fs), fs)
                w_ = _text_width(s, f_, st_.get("font-weight", 400)) if _text_width else 0.58 * f_ * len(s)
                cur["segs"].append((curx, w_, cy_, f_, s))
                curx += w_

            add_seg(el.text or "", st)
            for ch in el:
                if local(ch.tag) != "tspan":
                    continue
                cst = style(ch, st)
                if ch.get("x") is not None:
                    chunks.append(cur)
                    curx = fnum(ch.get("x").split()[0])
                    cur = {"x": curx, "segs": []}
                if ch.get("y") is not None:
                    cy_ = fnum(ch.get("y").split()[0])
                cy_ += fnum(ch.get("dy"), 0)
                curx += fnum(ch.get("dx"), 0)
                add_seg("".join(ch.itertext()), cst)
                add_seg(ch.tail or "", st)
            chunks.append(cur)
            content = re.sub(r"\s+", " ", "".join(el.itertext())).strip()
            pts, minf = [], fs
            for c in chunks:
                if not c["segs"]:
                    continue
                total = c["segs"][-1][0] + c["segs"][-1][1] - c["x"]
                shift = {"middle": -total / 2, "end": -total}.get(anchor, 0)
                for sx, w_, by, f_, s in c["segs"]:
                    desc = 0.21 if re.search(r"[gjpqy(),;\[\]{}|/]", s) else 0.02
                    pts += [(sx + shift, by - 0.73 * f_), (sx + shift + w_, by + desc * f_)]
                    minf = min(minf, f_)
            if pts:
                b = box_of(pts, M)
                texts.append({"box": b, "fs": minf * M.scale(), "line": st.get("__line"),
                              "name": f'text{"#" + el.get("id") if el.get("id") else ""} "{content[:36]}"'})
            return
        for ch in el:
            if isinstance(ch.tag, str):
                walk(ch, M, st)

    walk(root, Mat(), {})
    X0, Y0, W, H = vb
    canvas = [X0, Y0, X0 + W, Y0 + H]
    area = lambda b: max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    shapes = [s for s in shapes if area(s["box"]) < 0.9 * W * H]
    tgt = opt["targetPt"] / W

    def bounds(b, name):
        o = max(canvas[0] - b[0], canvas[1] - b[1], b[2] - canvas[2], b[3] - canvas[3])
        if o > 0.5:
            issues.append(issue("error", "out-of-bounds", f"{name} extends {r1(o)}u beyond the canvas (approx.)", b))
        elif -o < opt["edgeMargin"]:
            issues.append(issue("warn", "near-edge", f"{name} is only {r1(max(0, -o))}u from the canvas edge (approx.)", b))

    for s in shapes:
        bounds(s["box"], s["name"])
    for e in edges:
        bounds(e["box"], e["name"])
    for t in texts:
        bounds(t["box"], t["name"])
        p = t["fs"] * tgt
        if p < opt["errPt"]:
            issues.append(issue("error", "font-too-small", f"{t['name']}: {r1(t['fs'])}u = {p:.1f}pt at {opt['targetName']} width", t["box"]))
        elif p < opt["minPt"] - 1e-6:
            issues.append(issue("warn", "font-small", f"{t['name']}: {r1(t['fs'])}u = {p:.1f}pt at {opt['targetName']} width (want >= {opt['minPt']}pt)", t["box"]))
        if t.get("script"):
            sp = t["script"] * tgt
            if sp < opt["mathScriptErrPt"] - 0.01:
                issues.append(issue("error", "math-script-too-small", f"{t['name']}: scripts print at {sp:.2f}pt (min {opt['mathScriptErrPt']}pt)", t["box"]))
            elif sp < opt["minPt"] - 0.01:
                issues.append(issue("warn", "math-script-small", f"{t['name']}: scripts print at {sp:.2f}pt (want >= {opt['minPt']}pt where space allows)", t["box"]))
        b = t["box"]
        cx_, cy_ = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        cands = sorted([s for s in shapes if s["box"][0] <= cx_ <= s["box"][2] and s["box"][1] <= cy_ <= s["box"][3] and area(s["box"]) > 1.15 * area(b)], key=lambda s: area(s["box"]))
        if cands:
            c = cands[0]["box"]
            clear = min(b[0] - c[0], c[2] - b[2], b[1] - c[1], c[3] - b[3])
            if clear < 0:
                issues.append(issue("error", "text-overflow", f"{t['name']} sticks out of {cands[0]['name']} by ~{r1(-clear)}u (approx.)", b))
            elif clear < opt["minPad"]:
                issues.append(issue("warn", "tight-padding", f"{t['name']} is only ~{r1(clear)}u from the border of {cands[0]['name']} (approx.)", b))
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            a, b = texts[i]["box"], texts[j]["box"]
            if texts[i].get("line") and texts[i].get("line") == texts[j].get("line"):
                continue
            if min(a[2], b[2]) - max(a[0], b[0]) > 0.3 and min(a[3], b[3]) - max(a[1], b[1]) > 0.3:
                issues.append(issue("error", "text-overlap", f"{texts[i]['name']} overlaps {texts[j]['name']} (approx.)",
                                    [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]))
    sizes = sorted({round(t["fs"] * 2) / 2 for t in texts})
    if len(sizes) > 5:
        issues.append(issue("warn", "font-tiers", f"{len(sizes)} distinct font sizes ({', '.join(f'{s:g}' for s in sizes)}u); use 3-5 tiers"))
    for it in issues:
        if it.get("bbox"):
            it["bbox"] = [r1(v) for v in it["bbox"]]
    stats = {"vb": list(vb), "nTexts": len(texts), "nShapes": len(shapes), "nEdges": len(edges), "fontSizes": sizes}
    return issues, stats


def pil_debug_overlay(png, out, issues, vb, scale, grid):
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return False
    im = Image.open(png).convert("RGB")
    dr = ImageDraw.Draw(im, "RGBA")
    X0, Y0, W, H = vb
    s = scale
    x = math.ceil(X0 / grid) * grid
    while x <= X0 + W:
        dr.line([((x - X0) * s, 0), ((x - X0) * s, H * s)], fill=(15, 163, 177, 110), width=1)
        dr.text(((x - X0) * s + 2, 2), str(int(x)), fill=(11, 122, 133, 255))
        x += grid
    y = math.ceil(Y0 / grid) * grid
    while y <= Y0 + H:
        dr.line([(0, (y - Y0) * s), (W * s, (y - Y0) * s)], fill=(15, 163, 177, 110), width=1)
        dr.text((2, (y - Y0) * s + 2), str(int(y)), fill=(11, 122, 133, 255))
        y += grid
    for it in issues:
        if not it.get("bbox") or it["sev"] == "info":
            continue
        a, b, c, d = it["bbox"]
        col = (227, 0, 91, 255) if it["sev"] == "error" else (240, 120, 0, 255)
        box = [(a - X0 - 1.5) * s, (b - Y0 - 1.5) * s, (c - X0 + 1.5) * s, (d - Y0 + 1.5) * s]
        dr.rectangle(box, outline=col, width=2)
        dr.rectangle([box[0], box[1] - 12, box[0] + 8 * len(it["tag"]) + 4, box[1]], fill=col)
        dr.text((box[0] + 2, box[1] - 11), it["tag"], fill=(255, 255, 255, 255))
    im.save(out)
    return True


# ----------------------------------------------------------------------------- PDF text handling


def pdf_font_types(pdf):
    """List of (name, type) from pdffonts (PyMuPDF as fallback), or None when neither is available."""
    if not shutil.which("pdffonts"):
        if tex_math.tex_env().get("pymupdf"):
            return [(n, "Type 3" if t == "Type3" else t) for n, t in tex_math.pdf_fonts(pdf)]
        return None
    r = run(["pdffonts", pdf])
    out = []
    for line in r.stdout.splitlines()[2:]:
        tok = line.split()
        if len(tok) >= 7:
            out.append((tok[0], " ".join(tok[1:-6]) if len(tok) > 7 else tok[1]))
    return out


def outline_pdf_text(pdf, chromium_kind, chromium_path):
    """Replace the PDF's fonts by vector glyph outlines: pdftocairo -svg, then Chromium prints the outlined SVG.

    Chromium/Skia embeds CFF-flavoured OpenType fonts (e.g. Inter .otf) as Type 3, which many camera-ready
    checkers reject. Outlined text is resolution-independent and font-free.
    """
    with tempfile.TemporaryDirectory(prefix="mlfig_") as td:
        osvg, opdf = Path(td) / "outlined.svg", Path(td) / "outlined.pdf"
        r = run(["pdftocairo", "-svg", pdf, str(osvg)])
        if r.returncode != 0 or not osvg.exists():
            raise RuntimeError(f"pdftocairo -svg failed: {(r.stderr or '').strip()[-300:]}")
        text = osvg.read_text(encoding="utf-8")
        m = re.search(r'<svg[^>]*\swidth="([\d.]+)(?:pt)?"[^>]*\sheight="([\d.]+)(?:pt)?"', text)
        if not m:
            raise RuntimeError("cannot read outlined SVG size")
        wpt, hpt = float(m.group(1)), float(m.group(2))
        wpx, hpx = round(wpt / 0.75, 3), round(hpt / 0.75, 3)
        cfg = {"svg": str(osvg), "cssW": wpx, "cssH": hpx, "analyze": False, "staticIssues": [], "pngScale": 1,
               "png": None, "preview": None, "debug": None, "grid": 50, "pdf": str(opdf), "pdfW": wpx, "pdfH": hpx,
               "executablePath": chromium_path}
        run_chromium(chromium_kind, cfg, text)
        shutil.copyfile(opdf, pdf)


# ----------------------------------------------------------------------------- PDF checks


def check_pdf(pdf, wpt, hpt, png, first_family):
    issues, info = [], {}
    pages, size = None, None
    if shutil.which("pdfinfo"):
        r = run(["pdfinfo", pdf])
        m = re.search(r"Pages:\s+(\d+)", r.stdout)
        pages = int(m.group(1)) if m else None
        m = re.search(r"Page size:\s+([\d.]+) x ([\d.]+) pts", r.stdout)
        size = (float(m.group(1)), float(m.group(2))) if m else None
    else:
        try:
            from pypdf import PdfReader
            rd = PdfReader(pdf)
            pages = len(rd.pages)
            mb = rd.pages[0].mediabox
            size = (float(mb.width), float(mb.height))
        except Exception:
            pass
    info["pages"], info["size_pt"] = pages, size
    if pages is not None and pages != 1:
        issues.append(issue("error", "pdf-pages", f"PDF has {pages} pages (expected 1)"))
    if size and (abs(size[0] - wpt) > 1.5 or abs(size[1] - hpt) > 1.5):
        issues.append(issue("warn", "pdf-size", f"PDF page is {size[0]:.1f}x{size[1]:.1f}pt, expected {wpt:.1f}x{hpt:.1f}pt"))
    fonts = []
    if shutil.which("pdffonts"):
        r = run(["pdffonts", pdf])
        for line in r.stdout.splitlines()[2:]:
            tok = line.split()
            if len(tok) >= 7:
                fonts.append({"name": tok[0], "type": " ".join(tok[1:-6]) if len(tok) > 7 else tok[1], "emb": tok[-5]})
        bad = [f["name"] for f in fonts if f["emb"] != "yes"]
        if bad:
            issues.append(issue("error", "pdf-font-not-embedded", f"fonts not embedded: {', '.join(bad)} (camera-ready checks will fail)"))
    elif tex_math.tex_env().get("pymupdf"):
        fonts = [{"name": n, "type": "Type 3" if t == "Type3" else t, "emb": "?"} for n, t in tex_math.pdf_fonts(pdf)]
    t3 = [f["name"] for f in fonts if "Type 3" in f["type"]]
    if t3:
        issues.append(issue("error", "pdf-type3", f"PDF contains Type 3 fonts ({', '.join(sorted(set(t3)))[:120]}); "
                            "camera-ready checkers reject them. Use --pdf-text auto/outline, or a TrueType/Type 1 font"))
    info["font_types"] = sorted({f"{re.sub(r'^[A-Z]{6}[+]', '', f['name'])} ({f['type']})" for f in fonts})
    info["fonts"] = sorted({re.sub(r"^[A-Z]{6}\+", "", f["name"]) for f in fonts})
    if tex_math.tex_env().get("pymupdf"):
        try:
            sizes = {}
            for font, size, _, _ in tex_math.pdf_text_spans(pdf):
                sizes.setdefault(font, set()).add(round(size, 1))
            info["text_sizes"] = {f: sorted(v) for f, v in sorted(sizes.items())}
        except Exception:
            pass
    if first_family and info["fonts"]:
        key = first_family.replace(" ", "").lower()
        if not any(key in f.replace(" ", "").lower() for f in info["fonts"]):
            issues.append(issue("info", "font-substituted", f"'{first_family}' is not installed here; the PDF uses {', '.join(info['fonts'])}"))
    if shutil.which("pdfimages"):
        r = run(["pdfimages", "-list", pdf])
        n = max(0, len([l for l in r.stdout.splitlines()[2:] if l.strip()]))
        info["raster_images"] = n
        if n:
            issues.append(issue("warn", "pdf-raster", f"PDF contains {n} raster image(s): filters, emoji or <image> were rasterised"))
    if png and shutil.which("pdftoppm"):
        try:
            from PIL import Image, ImageChops, ImageStat
            ref = Image.open(png).convert("L")
            with tempfile.TemporaryDirectory(prefix="mlfig_") as td:
                dpi = ref.width / (wpt / 72.0)
                run(["pdftoppm", "-png", "-singlefile", "-r", f"{dpi:.2f}", pdf, str(Path(td) / "p")])
                got = Image.open(Path(td) / "p.png").convert("L").resize(ref.size)
                diff = ImageStat.Stat(ImageChops.difference(ref, got)).mean[0] / 255.0
            info["png_pdf_diff"] = round(diff, 4)
            if diff > 0.03:
                issues.append(issue("warn", "pdf-mismatch", f"PDF raster differs from the PNG by {diff:.1%} (missing fonts or unsupported features?)"))
        except Exception as e:  # pragma: no cover
            info["png_pdf_diff"] = f"n/a ({e.__class__.__name__})"
    return issues, info


# ----------------------------------------------------------------------------- LaTeX math typesetting

TEXT_RE = re.compile(r"<text\b([^>]*?)(/?)>(.*?)</text>", re.S)
OUT_RE = re.compile(r"[ \t]*<g data-tex=\"out\"[^>]*>.*?</g><!--/tex-->\n?", re.S)
META_RE = re.compile(r"\s*<metadata id=\"tex-setup\"[^>]*>.*?</metadata>", re.S)
MATH_RE = re.compile(r"<g class=\"tex-math\"[^>]*>.*?</g><!--/m-->", re.S)
ATTR_RE = re.compile(r"""([:\w-]+)\s*=\s*("[^"]*"|'[^']*')""")


def _attrs(s):
    return [(k, v[1:-1]) for k, v in ATTR_RE.findall(s)]


def _attr_str(pairs):
    return "".join(f' {k}="{html.escape(v, quote=True)}"' for k, v in pairs)


def _css_hex(c):
    m = re.match(r"rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)", c or "")
    if m:
        return "".join(f"{int(v):02X}" for v in m.groups())
    m = re.fullmatch(r"#([0-9a-fA-F]{6})", (c or "").strip())
    if m:
        return m.group(1).upper()
    m = re.fullmatch(r"#([0-9a-fA-F]{3})", (c or "").strip())
    if m:
        return "".join(ch * 2 for ch in m.group(1)).upper()
    return "000000"


def _num(v, default=0.0):
    try:
        return float(re.sub(r"(px|pt)$", "", str(v).strip().split()[0].rstrip(",")))
    except (TypeError, ValueError, IndexError):
        return default


def read_tex_setup(svg_text):
    m = re.search(r"<metadata id=\"tex-setup\"([^>]*)>(.*?)</metadata>", svg_text, re.S)
    if not m:
        return None, {}
    return html.unescape(m.group(2).strip()), dict(_attrs(m.group(1)))


def _segments_for_measure(text):
    """[(segment, is_math)] with whitespace collapsed; sans segment edges become no-break spaces (they are measured
    and drawn as separate <text> elements, where plain edge spaces would collapse)."""
    segs = tex_math.split_math(re.sub(r"\s+", " ", text).strip())
    out = []
    for t, m in segs:
        if m:
            out.append((t.strip(), True))
        else:
            lead, core, trail = re.match(r"^( ?)(.*?)( ?)$", t, re.S).groups()
            out.append((" " * len(lead) + core + " " * len(trail), False))
    return out


def typeset_math(svg_path, svg_text, target_pt, VW, VH, chromium, chromium_path, a, notes, tex_issues):
    """Typeset every $...$ in the SVG's <text> elements and write the result back. Returns the new SVG text.

    Records problems in notes; raises nothing (the static lint then reports untypeset math as an error)."""
    if a.no_typeset:
        return svg_text
    stored_pre, stored_meta = read_tex_setup(svg_text)
    if a.paper or a.math:
        try:
            preamble, info = tex_math.paper_preamble(a.paper, a.math, not a.no_macros)
        except tex_math.TexError as e:
            notes.append(f"math: {e}")
            return svg_text
        paper_rel = os.path.relpath(info["paper"], svg_path.parent) if info["paper"] else ""
        setup = {"data-paper": paper_rel, "data-math": info["math"] or "", "data-macros": str(info["macros"])}
    elif stored_pre is not None:
        preamble, setup = stored_pre, stored_meta
    else:
        preamble, _ = tex_math.paper_preamble(None, None)
        setup = {"data-paper": "", "data-math": "cm (default)", "data-macros": "0"}
    base = OUT_RE.sub("", svg_text)
    sources = []
    for m in TEXT_RE.finditer(base):
        attrs, selfclose, inner = m.group(1), m.group(2), m.group(3)
        if selfclose:
            continue
        is_src = 'data-tex="src"' in attrs
        if "<" in inner:
            if tex_math.has_math(re.sub(r"<[^>]+>", "", html.unescape(inner))):
                notes.append("math: $...$ inside a <text> with <tspan> children is not typeset; put each line in its own "
                             "<text> without tspans")
            continue
        content = html.unescape(inner)
        if tex_math.has_math(content) or is_src:
            sources.append((m, attrs, content, is_src))
    if not sources:
        return svg_text
    k_print = target_pt / VW                      # printed pt per root user unit
    def hash_of(attrs, content, r):     # source, target, TeX setup and the measured sans layout (fonts, sizes, widths)
        lay = json.dumps([[round(w, 2) for w in r["widths"]], round(r["fs"], 3), r.get("fill"), r.get("anchor"), round(r["scale"], 4)])
        return hashlib.sha1(f"{attrs}|{content}|{k_print:.6f}|{preamble}|{lay}".encode()).hexdigest()[:12]
    old_hashes = re.findall(r'<g data-tex="out"[^>]*data-tex-hash="([0-9a-f]+)"', svg_text)
    old_src = re.findall(r'<g data-tex="out"[^>]*data-tex-src="([0-9a-f]+)"', svg_text)
    # measure the sans segments (exact with Chromium, Inter width table otherwise)
    items, plan = [], []
    for i, (m, attrs, content, is_src) in enumerate(sources):
        if not tex_math.has_math(content):
            plan.append(None)
            continue
        try:
            segs = _segments_for_measure(content)
        except tex_math.TexError as e:
            notes.append(f"math: {e}")
            plan.append(None)
            continue
        plan.append(segs)
        items.append({"i": i, "segs": [t for t, mm in segs if not mm]})
    tagged = base
    for i, (m, attrs, content, is_src) in reversed(list(enumerate(sources))):
        tagged = tagged[:m.start()] + f'<text data-tm-i="{i}"' + tagged[m.start() + 5:]
    meas = {}
    if chromium:
        try:
            cfg = {"svg": str(svg_path), "svgText": tagged, "cssW": VW, "cssH": VH, "measure": items,
                   "executablePath": chromium_path}
            res = run_chromium(chromium[0], cfg, tagged)
            for it, r in zip(items, res.get("measure") or []):
                if r:
                    meas[it["i"]] = r
        except Exception as e:
            notes.append(f"math: chromium measurement failed ({str(e).splitlines()[-1][:160]}); using approximate widths")
    snippets, layout = [], []
    for i, (m, attrs, content, is_src) in enumerate(sources):
        segs = plan[i]
        if segs is None:
            continue
        pairs = [(k, v) for k, v in _attrs(attrs) if k not in ("data-tex", "display", "data-tm-i")]
        ad = dict(pairs)
        r = meas.get(i)
        if r is None:      # approximate: attributes only
            fs = _num(ad.get("font-size"), 16.0)
            mm = re.search(r"font-size\s*:\s*([\d.]+)", ad.get("style", ""))
            fs = float(mm.group(1)) if mm else fs
            wt = ad.get("font-weight", 400)
            widths = [(_text_width(t.replace(" ", " "), fs, wt) if _text_width else 0.58 * fs * len(t)) for t, mm_ in segs if not mm_]
            r = {"widths": widths, "fs": fs, "fill": ad.get("fill", "#000000"), "anchor": ad.get("text-anchor", "start"), "scale": 1.0}
            if not any("widths are approximate" in n for n in notes):
                notes.append("math: sans segment widths are approximate (no Chromium); check the spacing visually")
        p_bp = r["fs"] * r["scale"] * k_print            # printed size of the sans text (bp)
        pt = round(p_bp, 3)                               # LaTeX size the snippet is compiled at (pt)
        # local user units per bp of TeX output, scaled so that `pt` TeX points print at p_bp: the math base size equals
        # the sans size and LaTeX's 5pt scripts print at 5pt
        k_u = (1.0 / (r["scale"] * k_print)) * (p_bp / pt) * (72.27 / 72.0) if pt > 0 else 1.0
        color = _css_hex(r.get("fill"))
        idx = []
        for t, ism in segs:
            if ism:
                idx.append(len(snippets))
                snippets.append({"tex": t, "pt": pt, "color": color})
        clean = re.sub(r'\s(data-tex|display)="[^"]*"', "", attrs)
        h = hash_of(clean, content, r)
        hs = hashlib.sha1(f"{clean}|{content}|{k_print:.6f}|{preamble}".encode()).hexdigest()[:12]
        layout.append((i, pairs, segs, r, pt, k_u, color, idx, h, hs))
    unhide = any(is_src and plan[i] is None for i, (_, _, _, is_src) in enumerate(sources))
    if layout and not unhide and sorted(old_hashes) == sorted(L[-2] for L in layout):
        return svg_text                          # up to date
    if layout and not unhide and len(meas) < len(items) and sorted(old_src) == sorted(L[-1] for L in layout):
        notes[:] = [n for n in notes if "widths are approximate" not in n]
        notes.append("math: kept the existing typesetting (no Chromium to re-measure the sans text)")
        return svg_text                          # sources unchanged; do not replace an exact layout by an approximate one
    probs = tex_math.env_problems(tex_math.tex_env())
    if probs and snippets:
        if old_hashes:
            tex_issues.append(issue("error", "math-stale", "a $...$ source, its font/size, the target width or the TeX setup changed "
                                    "since the math was typeset, and it cannot be re-typeset here (" + probs[0] + ")"))
        else:
            notes.append("math: " + "; ".join(probs))
        return svg_text
    comp = None
    if snippets:
        try:
            with tempfile.TemporaryDirectory(prefix="mlfig_tex_") as ttd:
                comp = tex_math.compile_snippets(snippets, preamble, workdir=ttd, svg=True, pdf=False)
        except tex_math.TexError as e:
            notes.append(f"math: {e}")
            return svg_text
    outs = {}
    for (i, pairs, segs, r, pt, k_u, color, idx, h, hs) in layout:
        m, attrs, content, is_src = sources[i]
        ad = dict(pairs)
        x, y = _num(ad.get("x")), _num(ad.get("y"))
        widths = iter(r["widths"])
        mi = iter(idx)
        pieces, total = [], 0.0
        for t, ism in segs:
            if ism:
                j = next(mi)
                wd, ht, dp = comp["metrics"][j]
                pieces.append(("m", t, j, wd * k_u, ht * k_u, dp * k_u))
                total += wd * k_u
            else:
                w = next(widths)
                pieces.append(("t", t, w))
                total += w
        anchor = (r.get("anchor") or ad.get("text-anchor") or "start").strip()
        cx = x - {"middle": total / 2, "end": total}.get(anchor, 0.0)
        sc, _ = tex_math.effective_sizes(pt, preamble)
        keep = [(k, v) for k, v in pairs if k not in ("id", "x", "y", "dx", "dy", "text-anchor", "transform", "textLength", "lengthAdjust")]
        style = re.sub(r"text-anchor\s*:[^;]*;?", "", dict(keep).get("style", "")).strip().rstrip(";")
        keep = [(k, v) for k, v in keep if k != "style"] + [("style", (style + ";" if style else "") + "text-anchor:start")]
        parts = []
        for pc in pieces:
            if pc[0] == "t":
                if pc[1].strip("  "):
                    parts.append(f"<text{_attr_str(keep)} x=\"{cx:.2f}\" y=\"{y:g}\">{html.escape(pc[1], quote=False)}</text>")
                cx += pc[2]
            else:
                _, t, j, wdu, htu, dpu = pc
                parts.append(
                    f'<g class="tex-math" data-tex="{html.escape(t, quote=True)}" data-pt="{pt:g}" data-script-pt="{sc:g}" '
                    f'data-size="{r["fs"]:g}" data-script-size="{sc * 72 / 72.27 * k_u:.4f}" data-x="{cx:.3f}" data-y="{y:g}" '
                    f'data-wd="{wdu:.3f}" data-ht="{htu:.3f}" data-dp="{dpu:.3f}" fill="#{color}" '
                    f'transform="translate({cx:.3f} {y:g}) scale({k_u:.5f})">{comp["svgs"][j]}</g><!--/m-->')
                cx += wdu
        tr = ad.get("transform")
        outs[i] = (f'<g data-tex="out" class="tex-line" data-tex-hash="{h}" data-tex-src="{hs}"' + (f' transform="{html.escape(tr, quote=True)}"' if tr else "")
                   + ">" + "".join(parts) + "</g><!--/tex-->")
    # rebuild: hide sources, insert outputs after them
    new, pos = [], 0
    for i, (m, attrs, content, is_src) in enumerate(sources):
        new.append(base[pos:m.start()])
        at = re.sub(r'\s(data-tex|display)="[^"]*"', "", attrs)
        if i in outs:
            new.append(f'<text{at} data-tex="src" display="none">{m.group(3)}</text>\n{outs[i]}')
        else:
            new.append(f"<text{at}>{m.group(3)}</text>")
        pos = m.end()
    new.append(base[pos:])
    out = META_RE.sub("", "".join(new))
    meta = (f'\n  <metadata id="tex-setup"{_attr_str(list(setup.items()))}>' + html.escape(preamble, quote=False) + "</metadata>")
    mroot = re.search(r"<svg\b[^>]*>", out)
    root_tag = mroot.group(0)
    if "xlink:" in out[mroot.end():] and "xmlns:xlink" not in root_tag:     # PyMuPDF glyphs use xlink:href
        root_tag = root_tag[:4] + ' xmlns:xlink="http://www.w3.org/1999/xlink"' + root_tag[4:]
    out = out[:mroot.start()] + root_tag + meta + out[mroot.end():]
    svg_path.write_text(out, encoding="utf-8")
    notes.append(f"math: typeset {len(snippets)} snippet(s) in {len(outs)} line(s) "
                 f"({setup.get('data-math') or 'cm'}, {setup.get('data-macros') or 0} paper macros) -> written into {svg_path.name}")
    return out


def math_placements(root, vb, target_pt):
    """[(snippet, rect_pt or None)] for every visible g.tex-math, in document order (root user units -> PDF pt)."""
    X0, Y0, W, _ = vb
    k = target_pt / W
    out = []

    def walk(el, M, hidden):
        tg = local(el.tag) if isinstance(el.tag, str) else ""
        if tg in ("defs", "metadata", "style", "title", "desc"):
            return
        hidden = hidden or el.get("display") == "none" or el.get("visibility") == "hidden"
        if tg == "g" and "tex-math" in (el.get("class") or "").split():
            try:
                x, y = float(el.get("data-x")), float(el.get("data-y"))
                wd, ht, dp = float(el.get("data-wd")), float(el.get("data-ht")), float(el.get("data-dp"))
                snip = {"tex": html.unescape(el.get("data-tex") or ""), "pt": float(el.get("data-pt")),
                        "color": (el.get("fill") or "#000000").lstrip("#")}
            except (TypeError, ValueError):
                out.append((None, None, hidden))
                return
            ok = abs(M.b) < 1e-9 and abs(M.c) < 1e-9 and M.a > 0 and M.d > 0
            if ok:
                (ax, ay), (bx, by) = M.ap(x, y - ht), M.ap(x + wd, y + dp)
                rect = ((ax - X0) * k, (ay - Y0) * k, (bx - X0) * k, (by - Y0) * k)
            else:
                rect = None
            out.append((snip, rect, hidden))
            return
        M = M * parse_transform(el.get("transform"))
        for ch in el:
            if isinstance(ch.tag, str):
                walk(ch, M, hidden)

    walk(root, Mat(), False)
    return out


def prepare_math_pdf(svg_text, root, vb, target_pt, notes):
    """(svg text for the PDF renderer, stamp job). Stampable math groups are removed from the PDF render and drawn
    afterwards from pdflatex output with their real Type 1 fonts; the rest stay as glyph outlines."""
    places = math_placements(root, vb, target_pt)
    if not places:
        return svg_text, None
    env = tex_math.tex_env()
    probs = tex_math.env_problems(env, need_pdf=True)
    if probs:
        notes.append("math in PDF: glyph outlines, no fonts (" + probs[-1].split(";")[0] + ")")
        return svg_text, None
    preamble, _ = read_tex_setup(svg_text)
    keep_idx = []
    jobs = []
    for i, (snip, rect, hidden) in enumerate(places):
        if hidden:
            continue
        if snip is None or rect is None:
            keep_idx.append(i)
            continue
        jobs.append((i, snip, rect))
    if any(p[1] is None and not p[2] for p in places):
        notes.append("math in PDF: rotated/skewed math kept as glyph outlines")
    if not jobs:
        return svg_text, None
    drop = {i for i, _, _ in jobs}
    cnt = [-1]

    def sub(mt):
        cnt[0] += 1
        return "" if cnt[0] in drop else mt.group(0)

    return MATH_RE.sub(sub, svg_text), {"jobs": jobs, "preamble": preamble or ""}


def stamp_math_pdf(pdf, job, notes):
    snips = [s for _, s, _ in job["jobs"]]
    try:
        with tempfile.TemporaryDirectory(prefix="mlfig_tex_") as ttd:
            comp = tex_math.compile_snippets(snips, job["preamble"], workdir=ttd, svg=False, pdf=True)
            tex_math.stamp_pdf(pdf, [r for _, _, r in job["jobs"]], comp["pdf"])
        return len(snips)
    except Exception as e:
        notes.append(f"math in PDF: stamping failed ({str(e).splitlines()[-1][:200]})")
        return 0


# ----------------------------------------------------------------------------- main


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("svg", nargs="?", help="input .svg")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--export", action="store_true", help="final deliverables: hi-res PNG + vector PDF + PDF checks")
    mode.add_argument("--check", action="store_true", help="lint only, write no images")
    ap.add_argument("--pdf", action="store_true", help="also write the PDF in review mode")
    ap.add_argument("--no-png", action="store_true", help="skip the main PNG")
    ap.add_argument("-o", "--outdir", help="output directory (default: next to the SVG)")
    ap.add_argument("--target", default="neurips", help="printed width: " + ", ".join(TARGETS) + " or a length (5.5in, 397pt, 12cm). Default neurips")
    ap.add_argument("--scale", type=float, help="PNG pixels per user unit (default 2 review / 3 export)")
    ap.add_argument("--dpi", type=float, help="PNG resolution at the printed width (overrides --scale)")
    ap.add_argument("--preview-dpi", type=float, default=120.0, help="DPI of the printed-size preview (default 120)")
    ap.add_argument("--grid", type=float, default=50.0, help="debug grid spacing in user units (default 50)")
    ap.add_argument("--backend", default="auto", help="auto | chromium | rsvg | inkscape | cairosvg | resvg")
    ap.add_argument("--chromium-path", default=os.environ.get("ML_FIG_CHROMIUM"), help="explicit Chromium executable")
    ap.add_argument("--min-pt", type=float, default=6.0, help="warn below this printed font size (default 6pt)")
    ap.add_argument("--err-pt", type=float, default=5.0, help="error below this printed font size (default 5pt)")
    ap.add_argument("--min-pad", type=float, default=3.0, help="min text clearance inside its box in user units (default 3)")
    ap.add_argument("--edge-margin", type=float, default=6.0, help="min distance from the canvas edge (default 6)")
    ap.add_argument("--tip-offset", type=float, default=2.0, help="how far the arrowhead tip extends past the path end (default 2, matches svg-primitives markers)")
    ap.add_argument("--align-tol", type=float, default=3.0, help="flag centres that differ by 0.5..N units (default 3)")
    ap.add_argument("--pdf-text", choices=["auto", "fonts", "outline"], default="auto",
                    help="auto: keep embedded fonts unless they are Type 3, then outline them; fonts: never outline; outline: always outline text")
    ap.add_argument("--paper", help="paper's main .tex: $...$ math uses its math fonts, packages and \\newcommand macros (stored in the SVG)")
    ap.add_argument("--math", help="math setup override: " + ", ".join(tex_math.MATH_SETUPS) + " or verbatim LaTeX (default: from --paper, else cm)")
    ap.add_argument("--no-macros", action="store_true", help="with --paper, do not copy the paper's macro definitions")
    ap.add_argument("--no-typeset", action="store_true", help="do not (re)typeset $...$ math")
    ap.add_argument("--no-tex-fonts", action="store_true", help="do not add the TeX font directories to fontconfig for Chromium")
    ap.add_argument("--keep-review", action="store_true", help="with --export, keep .debug/.preview PNGs")
    ap.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    ap.add_argument("--json", help="write the full report as JSON to this path")
    ap.add_argument("--no-browser", action="store_true", help="do not use Chromium (approximate geometry; for machines without Playwright or for testing)")
    ap.add_argument("--list-backends", action="store_true", help="show available renderers and exit")
    a = ap.parse_args(argv)

    backends = detect_backends(a.chromium_path)
    if a.no_browser:
        backends.pop("chromium", None)
    if a.list_backends:
        print("Detected renderers (auto order: chromium > rsvg > inkscape > cairosvg > resvg):")
        for k in ("chromium", "rsvg", "inkscape", "cairosvg", "resvg"):
            v = backends.get(k)
            print(f"  {k:9s} {'-' if not v else (v[1] if isinstance(v, tuple) else v)}")
        for tool in ("pdfinfo", "pdffonts", "pdfimages", "pdftoppm"):
            print(f"  {tool:9s} {shutil.which(tool) or '-'}")
        print("LaTeX math ($...$ in <text>):")
        tenv = tex_math.tex_env()
        for k_ in ("latex", "pdflatex", "dvisvgm", "kpsewhich", "pymupdf"):
            print(f"  {k_:9s} {tenv.get(k_) or '-'}")
        for p_ in tex_math.env_problems(tenv, need_pdf=True):
            print("  note:", p_)
        if "chromium" not in backends:
            print("  note: exact geometry lint needs Chromium via Playwright (pip install playwright && playwright install chromium)")
        return 0
    if not a.svg:
        ap.error("missing input .svg")

    svg_path = Path(a.svg).resolve()
    if not svg_path.exists():
        print(f"error: {svg_path} not found", file=sys.stderr)
        return 2
    outdir = Path(a.outdir).resolve() if a.outdir else svg_path.parent
    outdir.mkdir(parents=True, exist_ok=True)
    stem = svg_path.stem
    tname, tpt, tdesc = parse_target(a.target)

    notes = []
    if not a.no_tex_fonts and (backends.get("chromium") or backends.get("rsvg") or backends.get("inkscape")):
        fc_td = tempfile.mkdtemp(prefix="mlfig_fc_")
        atexit.register(shutil.rmtree, fc_td, True)
        fc_env, fc_dirs = tex_math.fontconfig_env(fc_td)
        if fc_env:
            os.environ["FONTCONFIG_FILE"] = fc_env["FONTCONFIG_FILE"]

    static, meta = static_lint(svg_path)
    if meta.get("fatal"):
        tag_issues(static)
        print_report(svg_path, static, None, {}, None, {}, tname, tpt, tdesc, {}, a)
        return 2
    vx, vy, VW, VH = meta["vb"]
    svg_text = meta["text"]
    tex_issues = []
    new_text = typeset_math(svg_path, svg_text, tpt, VW, VH, backends.get("chromium"), a.chromium_path, a, notes, tex_issues)
    if new_text != svg_text:
        static, meta = static_lint(svg_path)
        if meta.get("fatal"):
            tag_issues(static)
            print_report(svg_path, static, None, {}, None, {}, tname, tpt, tdesc, {"notes": notes}, a)
            return 2
        svg_text = meta["text"]
    static += tex_issues

    review = not a.export and not a.check
    want_png = not a.check and not a.no_png
    want_pdf = a.export or a.pdf
    want_debug = review
    want_preview = review
    if a.dpi:
        scale = a.dpi * (tpt / 72.0) / VW
    else:
        scale = a.scale or (3.0 if a.export else 2.0)
    preview_scale = a.preview_dpi * (tpt / 72.0) / VW
    debug_scale = max(1.0, min(4.0, 1800.0 / VW))
    pdf_wpt, pdf_hpt = tpt, tpt * VH / VW
    files = {
        "png": str(outdir / f"{stem}.png") if want_png else None,
        "pdf": str(outdir / f"{stem}.pdf") if want_pdf else None,
        "debug": str(outdir / f"{stem}.debug.png") if want_debug else None,
        "preview": str(outdir / f"{stem}.preview.png") if want_preview else None,
    }

    order = ["chromium", "rsvg", "inkscape", "cairosvg", "resvg"]
    if a.backend != "auto":
        if a.backend not in backends:
            print(f"error: backend '{a.backend}' not available (found: {', '.join(backends) or 'none'})", file=sys.stderr)
            return 2
        render_be = a.backend
    else:
        render_be = next((b for b in order if b in backends), None)
    if render_be is None and (want_png or want_pdf):
        print("error: no SVG renderer found. Install one of: Playwright+Chromium (pip install playwright && playwright install chromium), "
              "rsvg-convert (librsvg), cairosvg (pip install cairosvg), inkscape, resvg", file=sys.stderr)
        return 2
    # PDF: prefer cairo/pango renderers (proper font embedding, glyph fallback); Chromium PDFs get Type 3 fonts
    # for CFF fonts, which --pdf-text auto then outlines.
    pdf_order = ["rsvg", "inkscape", "chromium", "cairosvg"]
    if a.backend != "auto" and a.backend != "resvg":
        pdf_be = a.backend
    else:
        pdf_be = next((b for b in pdf_order if b in backends), None)
    if want_pdf and pdf_be is None:
        print("error: no PDF-capable renderer found (resvg writes PNG only)", file=sys.stderr)
        return 2

    opt = {"step": 2.0, "edgeMargin": a.edge_margin, "minPad": a.min_pad, "tipOffset": a.tip_offset, "alignTol": a.align_tol,
           "targetPt": tpt, "targetName": tname, "minPt": a.min_pt, "errPt": a.err_pt, "textGap": 2.0, "endSkip": 3.0,
           "mathScriptErrPt": tex_math.MIN_SCRIPT_PT}
    analysis, written, geometry = None, {}, "approximate"
    issues = None
    chromium = backends.get("chromium")
    pdf_svg_text, stamp_job = svg_text, None
    if want_pdf:
        pdf_svg_text, stamp_job = prepare_math_pdf(svg_text, meta["root"], meta["vb"], pdf_wpt, notes)
    if chromium:
        use_for_render = render_be == "chromium"
        cfg = {
            "svg": str(svg_path), "cssW": VW, "cssH": VH, "analyze": True, "analyzeOpts": opt, "staticIssues": static,
            "pngScale": scale, "png": files["png"] if use_for_render else None,
            "preview": files["preview"], "previewScale": preview_scale,
            "debug": files["debug"], "debugScale": debug_scale, "grid": a.grid,
            "pdf": files["pdf"] if (pdf_be == "chromium") else None,
            "pdfW": round(pdf_wpt / 0.75, 3), "pdfH": round(pdf_hpt / 0.75, 3),
            "pdfSvgText": pdf_svg_text if stamp_job else None,
            "executablePath": a.chromium_path,
        }
        try:
            res = run_chromium(chromium[0], cfg, svg_text)
            analysis = res.get("analysis")
            issues = res.get("issues")
            written.update(res.get("files", {}))
            geometry = "exact (chromium)"
        except Exception as e:
            notes.append(f"chromium failed, falling back: {str(e).splitlines()[-1][:300]}")
            if render_be == "chromium":
                render_be = next((b for b in order[1:] if b in backends), None)
            if pdf_be == "chromium":
                pdf_be = next((b for b in pdf_order if b != "chromium" and b in backends), None)
            chromium = None
            analysis = None
    if analysis is None:
        g_issues, g_stats = approx_geometry(meta["root"], meta["vb"], opt)
        analysis = {"issues": g_issues, "stats": g_stats}
        issues = static + g_issues
        tag_issues(issues)

    try:
        need_png = files["png"] and "png" not in written and render_be not in (None, "chromium")
        need_pdf = files["pdf"] and "pdf" not in written and pdf_be not in (None, "chromium")
        if need_png:
            written.update(render_cli(render_be, svg_path, svg_text, png=files["png"], png_px=(round(VW * scale), round(VH * scale))))
        if need_pdf:
            written.update(render_cli(pdf_be, svg_path, pdf_svg_text, pdf=files["pdf"], pdf_pt=(pdf_wpt, pdf_hpt)))
    except Exception as e:
        print(f"error: rendering failed: {e}", file=sys.stderr)
        return 2
    if want_debug and "debug" not in written and written.get("png"):
        if pil_debug_overlay(written["png"], files["debug"], issues, meta["vb"], scale, a.grid):
            written["debug"] = files["debug"]
    if want_preview and "preview" not in written and render_be not in (None, "chromium"):
        try:
            written.update({"preview": render_cli(render_be, svg_path, svg_text, png=files["preview"],
                                                  png_px=(round(VW * preview_scale), round(VH * preview_scale)))["png"]})
        except Exception:
            pass

    pdf_info = {}
    if written.get("pdf"):
        types = pdf_font_types(written["pdf"])
        has_t3 = bool(types) and any("Type 3" in t for _, t in types)
        if a.pdf_text == "outline" or (a.pdf_text == "auto" and has_t3):
            if chromium and shutil.which("pdftocairo"):
                try:
                    outline_pdf_text(written["pdf"], chromium[0], a.chromium_path)
                    pdf_info["text"] = "outlined (vector glyphs, no fonts)" + (" - replaced Type 3 fonts" if has_t3 else "")
                except Exception as e:
                    notes.append(f"could not outline PDF text: {str(e).splitlines()[-1][:200]}")
            else:
                notes.append("PDF text outlining needs Chromium (Playwright) + pdftocairo (poppler)")
        if "text" not in pdf_info:
            pdf_info["text"] = "embedded fonts"
        if stamp_job:
            n_st = stamp_math_pdf(written["pdf"], stamp_job, notes)
            if n_st:
                pdf_info["math"] = f"{n_st} snippet(s) with LaTeX Type 1 fonts"
            else:   # put the outlined math back rather than ship a PDF without it
                try:
                    if pdf_be == "chromium" and chromium:
                        cfg2 = {"svg": str(svg_path), "cssW": VW, "cssH": VH, "analyze": False, "staticIssues": [], "pngScale": 1,
                                "png": None, "preview": None, "debug": None, "grid": a.grid, "pdf": files["pdf"],
                                "pdfW": round(pdf_wpt / 0.75, 3), "pdfH": round(pdf_hpt / 0.75, 3), "executablePath": a.chromium_path}
                        run_chromium(chromium[0], cfg2, svg_text)
                    else:
                        render_cli(pdf_be, svg_path, svg_text, pdf=files["pdf"], pdf_pt=(pdf_wpt, pdf_hpt))
                    if a.pdf_text == "outline" or (a.pdf_text == "auto" and has_t3):
                        outline_pdf_text(written["pdf"], chromium[0], a.chromium_path)
                    pdf_info["math"] = "glyph outlines (stamping failed)"
                except Exception as e:
                    notes.append(f"could not restore the math in the PDF: {str(e).splitlines()[-1][:200]}")
        elif meta["root"] is not None and math_placements(meta["root"], meta["vb"], pdf_wpt):
            pdf_info["math"] = "glyph outlines"
        counts = {s: sum(1 for i in issues if i["sev"] == s) for s in ("error", "warn", "info")}
        outlined = pdf_info.get("text", "").startswith("outlined")
        p_issues, p_info = check_pdf(written["pdf"], pdf_wpt, pdf_hpt, written.get("png"), None if outlined else meta.get("first_family"))
        pdf_info.update(p_info)
        tag_issues(p_issues, counts)
        issues += p_issues
    if a.export and not a.keep_review:
        for suf in (".debug.png", ".preview.png"):
            p = outdir / f"{stem}{suf}"
            if p.exists():
                p.unlink()

    be_desc = {"render": render_be, "pdf": pdf_be if want_pdf else None, "geometry": geometry}
    stats = analysis.get("stats", {})
    print_report(svg_path, issues, stats, written, be_desc, pdf_info, tname, tpt, tdesc, {"scale": scale, "notes": notes, "VW": VW, "VH": VH}, a)
    if a.json:
        Path(a.json).write_text(json.dumps({"svg": str(svg_path), "issues": issues, "stats": stats, "files": written,
                                            "backend": be_desc, "pdf": pdf_info, "target": {"name": tname, "pt": tpt}}, indent=2))
    n_err = sum(1 for i in issues if i["sev"] == "error")
    n_warn = sum(1 for i in issues if i["sev"] == "warn")
    return 1 if n_err or (a.strict and n_warn) else 0


def print_report(svg_path, issues, stats, files, be, pdf_info, tname, tpt, tdesc, extra, a):
    out = []
    out.append(f"== render_svg.py | {svg_path.name} ==")
    if stats:
        _, _, VW, VH = stats.get("vb", [0, 0, extra.get("VW", 0), extra.get("VH", 0)])
        k = tpt / VW
        out.append(f"canvas    {VW:g} x {VH:g} u   render: {be['render'] or '-'}{'' if not be.get('pdf') or be['pdf'] == be['render'] else ', pdf: ' + be['pdf']}   geometry: {be['geometry']}")
        out.append(f"target    {tname}: {tdesc} = {tpt:.0f}pt  ->  1u = {k:.3f}pt  (font-size for N pt = {1 / k:.2f} x N u)")
        sizes = stats.get("fontSizes") or []
        if sizes:
            tiers = " | ".join(f"{s:g}u={s * k:.1f}pt" for s in sizes)
            cmp_ = ", ".join(f"{t} {sizes[0] * TARGETS[t][0] * 72 / VW:.1f}pt" for t in COMPARE_TARGETS if t != tname)
            out.append(f"fonts     {tiers}   (min at other widths: {cmp_})")
        out.append(f"counted   {stats.get('nTexts', 0)} texts, {stats.get('nShapes', 0)} filled shapes, {stats.get('nEdges', 0)} connectors")
        mi = stats.get("math") or []
        if mi:
            base_ = sorted({m["pt"] for m in mi})
            scr = sorted({m["scriptPt"] for m in mi if m.get("hasScripts")})
            out.append(f"math      {len(mi)} LaTeX group(s): base {', '.join(f'{v:g}' for v in base_)}pt"
                       + (f", scripts {', '.join(f'{v:g}' for v in scr)}pt" if scr else "") + " (printed)")
    for n in (extra.get("notes") or []):
        out.append(f"note      {n}")
    if files:
        desc = []
        for k_ in ("png", "debug", "preview", "pdf"):
            if files.get(k_):
                p = Path(files[k_])
                extra_s = ""
                if k_ in ("png", "debug", "preview"):
                    try:
                        from PIL import Image
                        with Image.open(p) as im:
                            extra_s = f" ({im.width}x{im.height})"
                    except Exception:
                        pass
                elif k_ == "pdf" and pdf_info.get("size_pt"):
                    w, h = pdf_info["size_pt"]
                    extra_s = f" ({w / 72:.2f}x{h / 72:.2f}in, vector)"
                desc.append(f"{p.name}{extra_s}")
        out.append("outputs   " + " | ".join(desc))
        out.append(f"          in {Path(next(iter(files.values()))).parent}")
    if pdf_info:
        bits = []
        if pdf_info.get("text"):
            bits.append("text " + pdf_info["text"])
        if pdf_info.get("math"):
            bits.append("math " + pdf_info["math"])
        if pdf_info.get("font_types"):
            bits.append("fonts " + ", ".join(pdf_info["font_types"]))
        elif pdf_info.get("fonts"):
            bits.append("fonts " + ", ".join(pdf_info["fonts"]))
        if pdf_info.get("text_sizes"):
            bits.append("text sizes " + ", ".join(f"{f} {'/'.join(f'{v:g}' for v in vs)}pt" for f, vs in pdf_info["text_sizes"].items()))
        if "raster_images" in pdf_info:
            bits.append(f"raster images {pdf_info['raster_images']}")
        if "png_pdf_diff" in pdf_info:
            bits.append(f"PNG/PDF diff {pdf_info['png_pdf_diff']}")
        out.append("pdf       " + "; ".join(bits))
    groups = [("error", "ERRORS"), ("warn", "WARNINGS"), ("info", "INFO")]
    for sev, title in groups:
        its = [i for i in issues if i["sev"] == sev]
        if not its:
            continue
        out.append(f"{title} ({len(its)})")
        shown_per_code = {}
        hidden = {}
        for it in its:
            c = it["code"]
            shown_per_code[c] = shown_per_code.get(c, 0) + 1
            if shown_per_code[c] > 8:
                hidden[c] = hidden.get(c, 0) + 1
                continue
            loc = ""
            if it.get("bbox"):
                b = it["bbox"]
                loc = f"  @({b[0]:g},{b[1]:g})-({b[2]:g},{b[3]:g})"
            out.append(f"  {it.get('tag', '?'):4s} {c:20s} {it['msg']}{loc}")
        for c, n in hidden.items():
            out.append(f"       ... {n} more {c}")
    n_err = sum(1 for i in issues if i["sev"] == "error")
    n_warn = sum(1 for i in issues if i["sev"] == "warn")
    verdict = "FAIL" if n_err or (a.strict and n_warn) else "PASS"
    hint = ""
    if not a.export and not a.check and files:
        hint = "  Next: open the .debug.png (issue boxes + grid) and .preview.png (printed size) and run the visual checklist."
    out.append(f"RESULT    {verdict}: {n_err} error(s), {n_warn} warning(s).{hint}")
    print("\n".join(out))


if __name__ == "__main__":
    sys.exit(main())
