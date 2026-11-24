#!/usr/bin/env python3
"""svg_geom.py - exact geometry for ml-paper-figure SVG primitives.

Prints ready-to-paste SVG markup / attribute values so connector paths, ML
shapes and mini visualisations never have to be computed by hand.

Commands (all coordinates in SVG user units, "u"):
  ortho      rounded orthogonal path through axis-aligned waypoints
  elbow      auto-routed orthogonal connector between two ports (hv, vh, hvh, vhv)
  trapezoid  encoder / decoder shape (rounded path) + safe text area + ports
  stack      offset card stack (multi-head, channels, ensembles), back to front
  cuboid     isometric tensor block (front / top / side faces)
  layers     pretrained / frozen model as a block of stacked layers
  vector     feature vector: a bar split into cells (optionally shaded)
  grid       mini cell grid: noise | heat | attn | seg | patch
  bell       Gaussian bell-curve path (distribution / uncertainty glyph)
  label      centred (multi-line) <text> for a box + width-fit check
  width      estimate rendered text width (Inter metrics)

Examples:
  python svg_geom.py elbow 282,155 304,110 --mode hvh --mid 290 --arrow
  python svg_geom.py ortho "470,190 470,240 650,240 650,198" --r 8 --arrow
  python svg_geom.py trapezoid 108 96 88 96 --inset 20 --kind encoder
  python svg_geom.py grid 30 30 40 40 --rows 6 --cols 6 --mode noise --seed 3
  python svg_geom.py label 300 92 96 36 "Mean Head" --fs 14 --weight 600
"""
from __future__ import annotations

import argparse
import math
import random
import sys

# Arrowheads from references/svg-primitives.md put the tip ARROW_TIP units past
# the path end, so a path must stop ARROW_TIP short of the target border.
ARROW_TIP = 2.0
MIN_LAST_RUN = 12.0  # straight run needed after the last bend for an arrowhead

# Inter advance widths (1/1000 em) for ASCII 32..126, measured from Inter 4.
_W_REG = ("281 288 466 633 642 982 644 300 365 365 501 662 288 460 288 360 631 407 610 618 646 608 620 566 "
          "619 620 288 302 662 662 662 511 966 690 654 730 722 601 590 746 743 269 571 672 565 903 753 765 639 "
          "765 644 642 646 744 690 985 682 679 629 365 360 365 471 456 323 562 612 571 612 583 370 613 591 242 "
          "242 549 242 876 591 600 612 612 376 528 327 591 562 818 546 562 552 426 333 426 662")
_W_SEMI = ("252 321 523 644 650 1004 663 326 373 373 540 673 319 465 319 379 660 423 623 636 666 629 640 576 "
           "640 640 319 329 673 673 673 543 999 728 659 737 722 605 588 749 746 277 580 703 565 922 759 769 645 "
           "773 652 650 660 736 728 1020 720 713 652 373 379 373 481 469 351 574 624 583 624 591 389 625 612 262 "
           "262 569 262 900 612 609 624 624 397 549 353 612 587 839 569 588 566 455 359 455 673")
WIDTHS = {
    "regular": [int(v) for v in _W_REG.split()],
    "semibold": [int(v) for v in _W_SEMI.split()],
}
_GREEK = {"μ": 600, "σ": 633, "ε": 544, "α": 674, "β": 600, "λ": 655, "θ": 623, "φ": 746,
          "ψ": 795, "ω": 815, "Σ": 690, "×": 668, "·": 300, "→": 954, "∈": 656, "ℝ": 656}


def text_width(text: str, fs: float, weight: int | str = 400) -> float:
    """Estimated advance width of `text` at font-size `fs` (Inter; Helvetica/Arial are ~5% narrower)."""
    try:
        w = int(weight)
    except (TypeError, ValueError):
        w = 700 if str(weight).lower() in ("bold", "bolder") else 400
    table = WIDTHS["semibold"] if w >= 550 else WIDTHS["regular"]
    total = 0
    for ch in text:
        o = ord(ch)
        if 32 <= o <= 126:
            total += table[o - 32]
        elif ch in _GREEK:
            total += _GREEK[ch]
        elif 0x300 <= o <= 0x36F:  # combining marks
            continue
        else:
            total += 620
    return total / 1000.0 * fs


# --------------------------------------------------------------------------- helpers
def f(v: float) -> str:
    """Compact number formatting (max 2 decimals, no trailing zeros)."""
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def pt(p) -> str:
    return f"{f(p[0])} {f(p[1])}"


def parse_point(s: str):
    try:
        x, y = s.replace(" ", "").split(",")
        return (float(x), float(y))
    except ValueError:
        sys.exit(f"bad point '{s}' (expected x,y)")


def parse_points(s: str):
    return [parse_point(tok) for tok in s.replace(";", " ").split() if tok.strip()]


def _sign(v: float) -> float:
    return (v > 0) - (v < 0)


def _simplify(pts):
    out = []
    for p in pts:
        if out and abs(out[-1][0] - p[0]) < 1e-9 and abs(out[-1][1] - p[1]) < 1e-9:
            continue
        out.append(p)
    i = 1
    while i < len(out) - 1:  # drop collinear middle points
        a, b, c = out[i - 1], out[i], out[i + 1]
        if (abs(a[0] - b[0]) < 1e-9 and abs(b[0] - c[0]) < 1e-9) or (abs(a[1] - b[1]) < 1e-9 and abs(b[1] - c[1]) < 1e-9):
            out.pop(i)
        else:
            i += 1
    return out


def _move(p, q, dist):
    """Point at `dist` from p toward q."""
    L = math.hypot(q[0] - p[0], q[1] - p[1])
    if L == 0:
        return p
    return (p[0] + (q[0] - p[0]) * dist / L, p[1] + (q[1] - p[1]) * dist / L)


def ortho_path(points, r=8.0, trim_start=0.0, trim_end=0.0):
    """Rounded orthogonal path. Returns (d, warnings, final_points)."""
    pts = _simplify(list(points))
    warns = []
    if len(pts) < 2:
        sys.exit("need at least two distinct points")
    for a, b in zip(pts, pts[1:]):
        if abs(a[0] - b[0]) > 1e-9 and abs(a[1] - b[1]) > 1e-9:
            sys.exit(f"segment {pt(a)} -> {pt(b)} is diagonal; orthogonal paths need shared x or y")
    if trim_end:
        L = math.hypot(pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1])
        if L <= trim_end:
            sys.exit("last segment shorter than the trim")
        pts[-1] = _move(pts[-1], pts[-2], trim_end)
    if trim_start:
        pts[0] = _move(pts[0], pts[1], trim_start)
    d = [f"M {pt(pts[0])}"]
    n = len(pts)
    used_out = 0.0
    last_run = None
    for i in range(1, n - 1):
        A, P, B = pts[i - 1], pts[i], pts[i + 1]
        lin = math.hypot(P[0] - A[0], P[1] - A[1])
        lout = math.hypot(B[0] - P[0], B[1] - P[1])
        rin = lin - used_out
        rout = lout if i == n - 2 else lout / 2
        ri = max(0.0, min(r, rin, rout))
        if ri < r - 1e-9:
            warns.append(f"corner at {pt(P)} radius reduced to {f(ri)} (segments too short)")
        p1 = _move(P, A, ri)
        p2 = _move(P, B, ri)
        cur = A if i == 1 else _move(A, P, used_out)
        if math.hypot(p1[0] - cur[0], p1[1] - cur[1]) > 1e-6:
            d.append(f"L {pt(p1)}")
        d.append(f"Q {pt(P)} {pt(p2)}")
        used_out = ri
        if i == n - 2:
            last_run = lout - ri
    d.append(f"L {pt(pts[-1])}")
    if last_run is None:
        last_run = math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])
    return " ".join(d), warns, pts, last_run


def _emit_path(d, args, pts, last_run, warns):
    cls = "edge"
    attrs = [f'd="{d}"', 'fill="none"', f'stroke="{args.stroke}"', f'stroke-width="{f(args.sw)}"']
    if args.dash:
        attrs.append('stroke-dasharray="5 3.5"')
    if args.arrow:
        attrs.append(f'marker-end="url(#{args.marker})"')
    attrs.insert(0, f'class="{cls}"')
    print(f"<path {' '.join(attrs)}/>")
    if args.arrow:
        tip = _move(pts[-1], pts[-2], -ARROW_TIP)
        print(f"<!-- tip lands at {pt(tip)}; last straight run {f(last_run)}u -->")
        if last_run < MIN_LAST_RUN:
            warns.append(f"last straight run {f(last_run)}u < {f(MIN_LAST_RUN)}u: arrowhead will sit on the bend; move the bend away from the target")
    # suggested label anchor: midpoint of longest segment
    segs = list(zip(pts, pts[1:]))
    a, b = max(segs, key=lambda s: math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1]))
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    if abs(a[1] - b[1]) < 1e-9:
        print(f"<!-- edge label: text-anchor=middle x={f(mx)} y={f(my - 6)} (baseline 6u above the line) -->")
    else:
        print(f"<!-- edge label: text-anchor=start x={f(mx + 6)} y={f(my + 4)} (6u right of the line) -->")
    for w in warns:
        print(f"warning: {w}", file=sys.stderr)


def cmd_ortho(args):
    pts = parse_points(args.points)
    trim = ARROW_TIP if args.arrow and args.trim_end is None else (args.trim_end or 0.0)
    d, warns, final, last = ortho_path(pts, args.r, args.trim_start, trim)
    _emit_path(d, args, final, last, warns)


def cmd_elbow(args):
    (x0, y0), (x1, y1) = parse_point(args.start), parse_point(args.end)
    mode = args.mode
    if mode == "hvh":
        m = args.mid if args.mid is not None else round((x0 + x1) / 2 * 2) / 2
        pts = [(x0, y0), (m, y0), (m, y1), (x1, y1)]
    elif mode == "vhv":
        m = args.mid if args.mid is not None else round((y0 + y1) / 2 * 2) / 2
        pts = [(x0, y0), (x0, m), (x1, m), (x1, y1)]
    elif mode == "hv":
        pts = [(x0, y0), (x1, y0), (x1, y1)]
    elif mode == "vh":
        pts = [(x0, y0), (x0, y1), (x1, y1)]
    else:
        sys.exit("mode must be hv, vh, hvh or vhv")
    trim = ARROW_TIP if args.arrow and args.trim_end is None else (args.trim_end or 0.0)
    d, warns, final, last = ortho_path(pts, args.r, args.trim_start, trim)
    _emit_path(d, args, final, last, warns)


def rounded_polygon(pts, r):
    """Closed path through polygon vertices with quadratic-rounded corners."""
    n = len(pts)
    d = []
    for i in range(n):
        A, P, B = pts[i - 1], pts[i], pts[(i + 1) % n]
        la = math.hypot(P[0] - A[0], P[1] - A[1])
        lb = math.hypot(B[0] - P[0], B[1] - P[1])
        ri = min(r, la / 2, lb / 2)
        p1, p2 = _move(P, A, ri), _move(P, B, ri)
        d.append(("M " if i == 0 else "L ") + pt(p1))
        d.append(f"Q {pt(P)} {pt(p2)}")
    d.append("Z")
    return " ".join(d)


def cmd_trapezoid(args):
    x, y, w, h, i = args.x, args.y, args.w, args.h, args.inset
    enc = args.kind == "encoder"
    if args.flow == "lr":
        if enc:   # wide (input) side on the left, narrow (output) side on the right
            pts = [(x, y), (x + w, y + i), (x + w, y + h - i), (x, y + h)]
        else:
            pts = [(x, y + i), (x + w, y), (x + w, y + h), (x, y + h - i)]
        safe = (x + args.pad, y + i + args.pad, x + w - args.pad, y + h - i - args.pad)
        ports = {"in (left mid)": (x, y + h / 2), "out (right mid)": (x + w, y + h / 2)}
        corner = (x + w, y + i) if enc else (x + w, y)
    else:     # top-to-bottom
        if enc:
            pts = [(x, y), (x + w, y), (x + w - i, y + h), (x + i, y + h)]
        else:
            pts = [(x + i, y), (x + w - i, y), (x + w, y + h), (x, y + h)]
        safe = (x + i + args.pad, y + args.pad, x + w - i - args.pad, y + h - args.pad)
        ports = {"in (top mid)": (x + w / 2, y), "out (bottom mid)": (x + w / 2, y + h)}
        corner = (x + w, y) if enc else (x + w - i, y)
    d = rounded_polygon(pts, args.r)
    print(f'<path d="{d}" fill="{args.fill}" stroke="{args.stroke}" stroke-width="1.2"/>')
    print(f"<!-- safe text box (narrowest span, {f(args.pad)}u pad): x {f(safe[0])}..{f(safe[2])}, y {f(safe[1])}..{f(safe[3])}; "
          f"centre {f((x + x + w) / 2)},{f(y + h / 2)} -->")
    for k, v in ports.items():
        print(f"<!-- port {k}: {pt(v)} -->")
    print(f"<!-- badge corner (top-right vertex): {pt(corner)} -> badge centre {pt((corner[0] - 2, corner[1] + 2))} -->")


def cmd_stack(args):
    x, y, w, h, n, dx, dy = args.x, args.y, args.w, args.h, args.n, args.dx, args.dy
    print(f'<g class="stack">  <!-- back to front; front card at {f(x)},{f(y)} -->')
    for k in reversed(range(n)):
        print(f'  <rect x="{f(x + k * dx)}" y="{f(y - k * dy)}" width="{f(w)}" height="{f(h)}" rx="{f(args.r)}" '
              f'fill="{args.fill}" stroke="{args.stroke}" stroke-width="1.1"/>')
    print("</g>")
    bx0, by0 = x, y - (n - 1) * dy
    bx1, by1 = x + w + (n - 1) * dx, y + h
    print(f"<!-- stack bbox x {f(bx0)}..{f(bx1)}, y {f(by0)}..{f(by1)}; front-card centre {f(x + w / 2)},{f(y + h / 2)}; "
          f"right port (front card) {f(x + w)},{f(y + h / 2)} -->")


def _mix(hex_a, hex_b, t):
    a = [int(hex_a.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    b = [int(hex_b.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(a[i] + (b[i] - a[i]) * t):02X}" for i in range(3))


def cmd_cuboid(args):
    x, y, w, h, dep = args.x, args.y, args.w, args.h, args.depth
    dx = dep * math.cos(math.radians(args.angle))
    dy = dep * math.sin(math.radians(args.angle))
    top = _mix(args.fill, "#FFFFFF", 0.45)
    side = _mix(args.fill, args.stroke, 0.35)
    sw = 'stroke-width="1" stroke-linejoin="round"'
    print(f'<g class="cuboid">')
    print(f'  <polygon points="{pt((x, y))} {pt((x + dx, y - dy))} {pt((x + w + dx, y - dy))} {pt((x + w, y))}" fill="{top}" stroke="{args.stroke}" {sw}/>')
    print(f'  <polygon points="{pt((x + w, y))} {pt((x + w + dx, y - dy))} {pt((x + w + dx, y + h - dy))} {pt((x + w, y + h))}" fill="{side}" stroke="{args.stroke}" {sw}/>')
    print(f'  <rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" fill="{args.fill}" stroke="{args.stroke}" {sw}/>')
    print("</g>")
    print(f"<!-- bbox x {f(x)}..{f(x + w + dx)}, y {f(y - dy)}..{f(y + h)}; front centre {f(x + w / 2)},{f(y + h / 2)}; "
          f"right port (side face mid) {f(x + w + dx)},{f(y + h / 2 - dy / 2)} -->")


def cmd_layers(args):
    """Pretrained / frozen model drawn as a block of stacked layers (data crosses the slabs in flow order)."""
    x, y, w, h, n, pad, gap = args.x, args.y, args.w, args.h, args.n, args.pad, args.gap
    slab = _mix(args.fill, args.stroke, 0.45)
    print(f'<g class="layers">')
    print(f'  <rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" rx="{f(args.r)}" fill="{args.fill}" '
          f'stroke="{args.stroke}" stroke-width="1.2"/>')
    if args.flow == "lr":   # vertical slabs side by side
        sw_ = (w - 2 * pad - (n - 1) * gap) / n
        for k in range(n):
            print(f'  <rect x="{f(x + pad + k * (sw_ + gap))}" y="{f(y + pad)}" width="{f(sw_)}" height="{f(h - 2 * pad)}" '
                  f'rx="2.5" fill="{slab}" stroke="{args.stroke}" stroke-width="0.8"/>')
    else:                   # horizontal slabs stacked top to bottom
        sh = (h - 2 * pad - (n - 1) * gap) / n
        for k in range(n):
            print(f'  <rect x="{f(x + pad)}" y="{f(y + pad + k * (sh + gap))}" width="{f(w - 2 * pad)}" height="{f(sh)}" '
                  f'rx="2.5" fill="{slab}" stroke="{args.stroke}" stroke-width="0.8"/>')
    print("</g>")
    print(f"<!-- ports: left {pt((x, y + h / 2))}, right {pt((x + w, y + h / 2))}, top {pt((x + w / 2, y))}, "
          f"bottom {pt((x + w / 2, y + h))}; badge centre {pt((x + w - 2, y + 2))}; "
          f"name below: text-anchor=middle x={f(x + w / 2)} y={f(y + h + 16)} -->")


def cmd_vector(args):
    """Feature / embedding vector: a bar split into cells, optionally shaded like values."""
    x, y, w, h, n = args.x, args.y, args.w, args.h, args.cells
    rnd = random.Random(args.seed)
    vertical = not args.horizontal
    step = (h if vertical else w) / n
    print(f'<g class="vector">')
    print(f'  <rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" rx="1.5" fill="#FFFFFF"/>')
    if args.shade:
        for k in range(n):
            op = 0.15 + 0.7 * rnd.random()
            cx, cy = (x, y + k * step) if vertical else (x + k * step, y)
            cw, ch = (w, step) if vertical else (step, h)
            print(f'  <rect x="{f(cx)}" y="{f(cy)}" width="{f(cw)}" height="{f(ch)}" fill="{args.fill}" fill-opacity="{op:.2f}"/>')
    else:
        print(f'  <rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" rx="1.5" fill="{_mix(args.fill, "#FFFFFF", 0.82)}"/>')
    lines = []
    for k in range(1, n):
        if vertical:
            lines.append(f"M{f(x)} {f(y + k * step)}H{f(x + w)}")
        else:
            lines.append(f"M{f(x + k * step)} {f(y)}V{f(y + h)}")
    print(f'  <path d="{"".join(lines)}" stroke="{args.stroke}" stroke-width="0.8" fill="none"/>')
    print(f'  <rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" rx="1.5" fill="none" stroke="{args.stroke}" stroke-width="1.1"/>')
    print("</g>")
    print(f"<!-- ports: left {pt((x, y + h / 2))}, right {pt((x + w, y + h / 2))}; name below: text-anchor=middle "
          f"x={f(x + w / 2)} y={f(y + h + 16)} -->")


SEG_COLORS = ["#9EC1E3", "#F2C18F", "#A8D5BF", "#D9B8DE", "#E8D99A"]


def cmd_grid(args):
    rnd = random.Random(args.seed)
    R, C, g = args.rows, args.cols, args.gap
    cw = (args.w - (C - 1) * g) / C
    ch = (args.h - (R - 1) * g) / R
    mode = args.mode
    vals = [[0.0] * C for _ in range(R)]
    colors = [[args.color] * C for _ in range(R)]
    if mode == "noise":
        for i in range(R):
            for j in range(C):
                u = 0.5 * (1 + math.erf(rnd.gauss(0, 1) / math.sqrt(2)))  # Gaussian sample -> uniform
                vals[i][j] = 0.08 + 0.80 * u
    elif mode == "heat":
        peaks = [(rnd.uniform(0.2, 0.8) * (R - 1), rnd.uniform(0.2, 0.8) * (C - 1), rnd.uniform(0.6, 1.0)) for _ in range(2)]
        s = max(R, C) / 3.2
        for i in range(R):
            for j in range(C):
                v = sum(a * math.exp(-((i - pi) ** 2 + (j - pj) ** 2) / (2 * s * s)) for pi, pj, a in peaks)
                vals[i][j] = v
        mx = max(max(r_) for r_ in vals)
        vals = [[0.08 + 0.82 * v / mx for v in r_] for r_ in vals]
    elif mode == "attn":
        for i in range(R):
            for j in range(C):
                v = 0.85 if i == j else rnd.uniform(0.05, 0.45) * (1.0 if abs(i - j) == 1 else 0.6)
                vals[i][j] = max(0.08, v)
    elif mode == "seg":
        seeds = [(rnd.uniform(0, R), rnd.uniform(0, C)) for _ in range(args.k)]
        for i in range(R):
            for j in range(C):
                k = min(range(len(seeds)), key=lambda t: (i + 0.5 - seeds[t][0]) ** 2 + (j + 0.5 - seeds[t][1]) ** 2)
                colors[i][j] = SEG_COLORS[k % len(SEG_COLORS)]
                vals[i][j] = 1.0
    elif mode == "patch":
        for i in range(R):
            for j in range(C):
                vals[i][j] = 0.0
    else:
        sys.exit("mode must be noise|heat|attn|seg|patch")
    print(f'<g class="mini-{mode}" data-lint="ignore">')
    if mode == "patch":
        # grid lines only, to overlay on an image thumbnail
        for j in range(1, C):
            xx = args.x + j * args.w / C
            print(f'  <line x1="{f(xx)}" y1="{f(args.y)}" x2="{f(xx)}" y2="{f(args.y + args.h)}" stroke="#FFFFFF" stroke-width="{f(max(g, 1))}"/>')
        for i in range(1, R):
            yy = args.y + i * args.h / R
            print(f'  <line x1="{f(args.x)}" y1="{f(yy)}" x2="{f(args.x + args.w)}" y2="{f(yy)}" stroke="#FFFFFF" stroke-width="{f(max(g, 1))}"/>')
    elif args.cells:
        for i in range(R):
            for j in range(C):
                xx = args.x + j * (cw + g)
                yy = args.y + i * (ch + g)
                op = "" if mode == "seg" else f' fill-opacity="{vals[i][j]:.2f}"'
                rx = f' rx="{f(args.cell_r)}"' if args.cell_r else ""
                print(f'  <rect x="{f(xx)}" y="{f(yy)}" width="{f(cw)}" height="{f(ch)}"{rx} fill="{colors[i][j]}"{op}/>')
    else:
        # compact: one <path> per colour / quantised opacity level
        groups = {}
        for i in range(R):
            for j in range(C):
                key = (colors[i][j], 1.0 if mode == "seg" else round(vals[i][j] * args.levels) / args.levels)
                xx = args.x + j * (cw + g)
                yy = args.y + i * (ch + g)
                groups.setdefault(key, []).append(f"M{f(xx)} {f(yy)}h{f(cw)}v{f(ch)}h-{f(cw)}z")
        for (col, op), parts in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            ops = "" if mode == "seg" else f' fill-opacity="{max(op, 0.06):.2f}"'
            print(f'  <path fill="{col}"{ops} d="{"".join(parts)}"/>')
    print("</g>")
    print(f"<!-- cells {f(cw)}x{f(ch)}u; frame it with a rect x={f(args.x - 1.5)} y={f(args.y - 1.5)} "
          f"width={f(args.w + 3)} height={f(args.h + 3)} rx=3 fill=none stroke=#A3AEBD -->")


def cmd_bell(args):
    x, y, w, h = args.x, args.y, args.w, args.h
    base = y + h
    d = (f"M {pt((x, base))} C {pt((x + 0.30 * w, base))} {pt((x + 0.36 * w, y))} {pt((x + 0.5 * w, y))} "
         f"C {pt((x + 0.64 * w, y))} {pt((x + 0.70 * w, base))} {pt((x + w, base))}")
    print(f'<path d="{d} Z" fill="{args.fill}" fill-opacity="0.35" stroke="none"/>')
    print(f'<path d="{d}" fill="none" stroke="{args.stroke}" stroke-width="1.3" stroke-linecap="round"/>')
    print(f'<line x1="{f(x)}" y1="{f(base)}" x2="{f(x + w)}" y2="{f(base)}" stroke="{args.stroke}" stroke-width="0.8" stroke-opacity="0.6"/>')


def cmd_label(args):
    lines = args.text.split("\\n") if "\\n" in args.text else args.text.split("|")
    fs, lh = args.fs, args.fs * args.leading
    cx, cy = args.x + args.w / 2, args.y + args.h / 2
    first = cy - (len(lines) - 1) * lh / 2 + 0.35 * fs
    cls = f' class="{args.cls}"' if args.cls else ""
    for k, line in enumerate(lines):
        font = "" if args.cls else f' font-size="{f(fs)}" font-weight="{args.weight}"'
        print(f'<text{cls} x="{f(cx)}" y="{f(first + k * lh)}" text-anchor="middle"{font} fill="#1F2933">{line}</text>')
    widest = max(text_width(s, fs, args.weight) for s in lines)
    block_h = (len(lines) - 1) * lh + 0.95 * fs
    pad_x = (args.w - widest) / 2
    pad_y = (args.h - block_h) / 2
    status = "OK" if pad_x >= 8 and pad_y >= 5 else "TIGHT"
    print(f"<!-- est. text {f(widest)}x{f(block_h)}u -> padding x {f(pad_x)}u, y {f(pad_y)}u [{status}: want x>=8, y>=5] -->")


def cmd_width(args):
    w = text_width(args.text, args.fs, args.weight)
    print(f"{f(w)}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def edge_opts(sp):
        sp.add_argument("--r", type=float, default=8.0, help="corner radius (default 8)")
        sp.add_argument("--arrow", action="store_true", help=f"add marker-end and stop {ARROW_TIP}u short of the end point")
        sp.add_argument("--marker", default="ah-data", help="marker id (default ah-data)")
        sp.add_argument("--stroke", default="#4B5768")
        sp.add_argument("--sw", type=float, default=1.6)
        sp.add_argument("--dash", action="store_true", help="dashed (loss / auxiliary) style")
        sp.add_argument("--trim-start", type=float, default=0.0)
        sp.add_argument("--trim-end", type=float, default=None)

    sp = sub.add_parser("ortho", help="rounded orthogonal path through waypoints")
    sp.add_argument("points", help='"x0,y0 x1,y1 ..." (end point = target border)')
    edge_opts(sp)
    sp.set_defaults(fn=cmd_ortho)

    sp = sub.add_parser("elbow", help="auto orthogonal connector between two ports")
    sp.add_argument("start")
    sp.add_argument("end", help="target border point")
    sp.add_argument("--mode", default="hvh", help="hv | vh | hvh | vhv (default hvh)")
    sp.add_argument("--mid", type=float, default=None, help="x (hvh) or y (vhv) of the middle segment")
    edge_opts(sp)
    sp.set_defaults(fn=cmd_elbow)

    sp = sub.add_parser("trapezoid", help="encoder/decoder shape")
    for k in ("x", "y", "w", "h"):
        sp.add_argument(k, type=float)
    sp.add_argument("--inset", type=float, default=None, help="narrowing per side (default h/5 or w/5)")
    sp.add_argument("--kind", choices=["encoder", "decoder"], default="encoder")
    sp.add_argument("--flow", choices=["lr", "tb"], default="lr")
    sp.add_argument("--r", type=float, default=5.0)
    sp.add_argument("--pad", type=float, default=6.0)
    sp.add_argument("--fill", default="#E4EEF8")
    sp.add_argument("--stroke", default="#8DB0D6")
    sp.set_defaults(fn=cmd_trapezoid)

    sp = sub.add_parser("stack", help="offset card stack")
    for k in ("x", "y", "w", "h"):
        sp.add_argument(k, type=float)
    sp.add_argument("--n", type=int, default=3)
    sp.add_argument("--dx", type=float, default=5.0)
    sp.add_argument("--dy", type=float, default=5.0, help="vertical offset per card (up)")
    sp.add_argument("--r", type=float, default=3.0)
    sp.add_argument("--fill", default="#E4EEF8")
    sp.add_argument("--stroke", default="#8DB0D6")
    sp.set_defaults(fn=cmd_stack)

    sp = sub.add_parser("cuboid", help="isometric tensor block")
    for k in ("x", "y", "w", "h"):
        sp.add_argument(k, type=float)
    sp.add_argument("--depth", type=float, default=10.0)
    sp.add_argument("--angle", type=float, default=45.0)
    sp.add_argument("--fill", default="#E4EEF8")
    sp.add_argument("--stroke", default="#8DB0D6")
    sp.set_defaults(fn=cmd_cuboid)

    sp = sub.add_parser("layers", help="pretrained/frozen model as a block of stacked layers")
    for k in ("x", "y", "w", "h"):
        sp.add_argument(k, type=float)
    sp.add_argument("--n", type=int, default=4, help="number of layer slabs (default 4)")
    sp.add_argument("--flow", choices=["lr", "tb"], default="lr", help="lr: vertical slabs side by side; tb: horizontal slabs")
    sp.add_argument("--pad", type=float, default=7.0)
    sp.add_argument("--gap", type=float, default=4.0)
    sp.add_argument("--r", type=float, default=7.0)
    sp.add_argument("--fill", default="#E4EEF8")
    sp.add_argument("--stroke", default="#8DB0D6")
    sp.set_defaults(fn=cmd_layers)

    sp = sub.add_parser("vector", help="feature vector: bar split into cells")
    for k in ("x", "y", "w", "h"):
        sp.add_argument(k, type=float)
    sp.add_argument("--cells", type=int, default=6)
    sp.add_argument("--horizontal", action="store_true", help="row vector (cells left to right)")
    sp.add_argument("--shade", action="store_true", help="shade cells like values")
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--fill", default="#3A6A9E")
    sp.add_argument("--stroke", default="#8DB0D6")
    sp.set_defaults(fn=cmd_vector)

    sp = sub.add_parser("grid", help="mini cell grid visualisation")
    for k in ("x", "y", "w", "h"):
        sp.add_argument(k, type=float)
    sp.add_argument("--rows", type=int, default=5)
    sp.add_argument("--cols", type=int, default=5)
    sp.add_argument("--gap", type=float, default=1.0)
    sp.add_argument("--mode", default="noise", help="noise | heat | attn | seg | patch")
    sp.add_argument("--color", default="#4B5563")
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--k", type=int, default=3, help="regions for seg mode")
    sp.add_argument("--cell-r", type=float, default=0.0)
    sp.add_argument("--levels", type=int, default=6, help="opacity levels in compact output (default 6)")
    sp.add_argument("--cells", action="store_true", help="one <rect> per cell instead of compact paths")
    sp.set_defaults(fn=cmd_grid)

    sp = sub.add_parser("bell", help="bell-curve glyph")
    for k in ("x", "y", "w", "h"):
        sp.add_argument(k, type=float)
    sp.add_argument("--fill", default="#EBA26A")
    sp.add_argument("--stroke", default="#B9662A")
    sp.set_defaults(fn=cmd_bell)

    sp = sub.add_parser("label", help="centred text for a box")
    for k in ("x", "y", "w", "h"):
        sp.add_argument(k, type=float)
    sp.add_argument("text", help='use "|" to separate lines')
    sp.add_argument("--fs", type=float, default=14.0)
    sp.add_argument("--weight", default="600")
    sp.add_argument("--leading", type=float, default=1.25)
    sp.add_argument("--cls", default="")
    sp.set_defaults(fn=cmd_label)

    sp = sub.add_parser("width", help="estimate text width")
    sp.add_argument("text")
    sp.add_argument("--fs", type=float, default=14.0)
    sp.add_argument("--weight", default="400")
    sp.set_defaults(fn=cmd_width)

    args = p.parse_args(argv)
    if args.cmd == "trapezoid" and args.inset is None:
        args.inset = (args.h if args.flow == "lr" else args.w) / 5
    args.fn(args)


if __name__ == "__main__":
    main()
