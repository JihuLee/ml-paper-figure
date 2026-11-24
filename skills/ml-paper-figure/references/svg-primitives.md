# SVG primitives: copy-paste building blocks

Every snippet here has been rendered and linted (see `assets/primitives-gallery.svg` / `.png`). Units are SVG user
units (u) on the 2u = 1pt scale from `design-system.md`. When a formula needs arithmetic, prefer
`scripts/svg_geom.py`, which prints exact markup (§10).

## Contents
0. Conventions the lint relies on
1. Skeleton + core `<defs>` (always paste)
2. Text placement
3. Boxes & containers
4. Connectors: markers, rounded orthogonal paths, ports, labels
5. ML shapes: trapezoids, stacks, cuboids, tokens, operators
6. Mini visualisations (optional `<defs>`)
7. Badges
8. Legend
9. Renderer-safe subset
10. `svg_geom.py` cheat-sheet

---

## 0. Conventions the lint relies on

| Markup | Meaning |
|---|---|
| `id="enc"` on modules, cards and important labels | issue messages name the element |
| `class="edge"` + `fill="none"` on every connector | marks it for arrow checks; a missing `fill="none"` renders a black wedge (lint error `edge-filled`) |
| `class="badge"` on badge `<use>` | excluded from alignment checks |
| `class="legend"` on the legend group | legend line samples skip arrow-target checks |
| `class="stack"` / `class="cuboid"` / `class="layers"` / `class="vector"` on composite shapes | excluded from alignment checks |
| `class="on-edge"` on a label and its white halo that sit on a line | excused from edge-crosses-label checks |
| `data-lint="ignore"` | skip this subtree entirely (mini visualisations made of many cells) |

Coordinates: integers on a 4u grid. Draw order inside `<svg>`: background → cards → edges → modules → labels → badges → legend.

## 1. Skeleton + core `<defs>`

Paste this, set the `viewBox`/`width`/`height` (and the background rect) to the canvas size, then add content. The root
`fill` makes unlabelled text primary-dark. Typography classes set size and weight only; give colours as `fill`
attributes on each `<text>`. (A CSS `fill` in a class would silently override those attributes.)

```xml
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     width="800" height="300" viewBox="0 0 800 300" fill="#1F2933"
     font-family="Inter, 'Helvetica Neue', Helvetica, Arial, 'Liberation Sans', sans-serif">
  <defs>
    <style>
      .t-stage { font-size: 17px; font-weight: 600; }
      .t-mod   { font-size: 15px; font-weight: 600; }
      .t-sub   { font-size: 13px; font-weight: 400; }
      .t-dim   { font-size: 13px; font-weight: 400; }
      .t-ours  { font-weight: 700; }   /* proposed method's name, in the figure only */
    </style>
    <marker id="ah-data" viewBox="0 0 10 8" refX="7.5" refY="4" markerWidth="8" markerHeight="6.4" markerUnits="userSpaceOnUse" orient="auto"><path d="M0 0L10 4L0 8L2.5 4Z" fill="#4B5768"/></marker>
    <marker id="ah-frozen" viewBox="0 0 10 8" refX="7.5" refY="4" markerWidth="8" markerHeight="6.4" markerUnits="userSpaceOnUse" orient="auto"><path d="M0 0L10 4L0 8L2.5 4Z" fill="#3A6A9E"/></marker>
    <marker id="ah-proposed" viewBox="0 0 10 8" refX="7.5" refY="4" markerWidth="8" markerHeight="6.4" markerUnits="userSpaceOnUse" orient="auto"><path d="M0 0L10 4L0 8L2.5 4Z" fill="#B5602A"/></marker>
    <marker id="ah-train" viewBox="0 0 10 8" refX="7.5" refY="4" markerWidth="8" markerHeight="6.4" markerUnits="userSpaceOnUse" orient="auto"><path d="M0 0L10 4L0 8L2.5 4Z" fill="#3B806A"/></marker>
    <marker id="ah-loss" viewBox="0 0 10 8" refX="7.5" refY="4" markerWidth="8" markerHeight="6.4" markerUnits="userSpaceOnUse" orient="auto"><path d="M0 0L10 4L0 8L2.5 4Z" fill="#A84B61"/></marker>
    <marker id="ah-aux" viewBox="0 0 10 8" refX="7.5" refY="4" markerWidth="8" markerHeight="6.4" markerUnits="userSpaceOnUse" orient="auto"><path d="M0 0L10 4L0 8L2.5 4Z" fill="#6A5A9B"/></marker>
    <g id="badge-frozen">
      <circle r="7.5" fill="#FFFFFF" stroke="#3A6A9E" stroke-width="1.1"/>
      <path d="M0 4.60L0 -4.60M3.98 2.30L-3.98 -2.30M3.98 -2.30L-3.98 2.30M0 -2.80L-1.06 -3.86M0 -2.80L1.06 -3.86M-2.42 -1.40L-3.87 -1.01M-2.42 -1.40L-2.81 -2.85M-2.42 1.40L-2.81 2.85M-2.42 1.40L-3.87 1.01M0 2.80L1.06 3.86M0 2.80L-1.06 3.86M2.42 1.40L3.87 1.01M2.42 1.40L2.81 2.85M2.42 -1.40L2.81 -2.85M2.42 -1.40L3.87 -1.01" fill="none" stroke="#3A6A9E" stroke-width="1.1" stroke-linecap="round"/>
    </g>
    <g id="badge-train">
      <circle r="7.5" fill="#FFFFFF" stroke="#C8602F" stroke-width="1.1"/>
      <path d="M0.3 -5.2C1.1 -3 3.9 -1.8 3.9 1.4C3.9 3.9 2.2 5.2 0 5.2C-2.2 5.2 -3.9 3.9 -3.9 1.5C-3.9 -0.4 -2.7 -1.5 -2.2 -3C-1.6 -1.8 -1.2 -0.9 -0.8 -0.5C-0.6 -2.1 -0.3 -3.6 0.3 -5.2Z" fill="#E2703A"/>
      <path d="M0.2 0.6C1.1 1.6 1.9 2.4 1.9 3.4C1.9 4.4 1.1 5 0 5C-1.1 5 -1.9 4.4 -1.9 3.4C-1.9 2.5 -1.1 1.9 -0.6 1.1C-0.4 1.6 -0.1 1.9 0.2 2.1C0.3 1.6 0.3 1.1 0.2 0.6Z" fill="#F8C98F"/>
    </g>
    <g id="badge-lock">
      <circle r="7.5" fill="#FFFFFF" stroke="#3A6A9E" stroke-width="1.1"/>
      <path d="M-2.3 -0.6V-2.3A2.3 2.3 0 0 1 2.3 -2.3V-0.6" fill="none" stroke="#3A6A9E" stroke-width="1.2"/>
      <rect x="-3.4" y="-0.8" width="6.8" height="5.2" rx="1.1" fill="#3A6A9E"/>
    </g>
  </defs>
  <rect id="bg" width="800" height="300" fill="#FFFFFF"/>
  <!-- cards, edges, modules, labels, badges, legend -->
</svg>
```

Markers: `ah-<role>` for `data, frozen, proposed, train, loss, aux`. All share one geometry: an 8u-long "stealth" head
whose **tip lands 2u past the path's last point**. So: **end every arrow path 2u before the target border.** (Target left
edge at x = 300 → path ends at x = 298.) Combined with `stroke-width ≤ 1.6`, this gives a sharp tip with no shaft
poking out. Leave ≥ 12u of straight segment before the head.

## 2. Text placement

There is no `dominant-baseline` (it differs between renderers). Place the **baseline** instead:

| Situation | Formula (font size `fs`) |
|---|---|
| one line centred in box (x, y, w, h) | `x = x + w/2`, `y = y + h/2 + 0.35·fs`, `text-anchor="middle"` |
| n lines centred, line height lh = 1.25·fs | first baseline `= cy − (n−1)·lh/2 + 0.35·fs`, then `+ lh` each |
| name (15u) + detail (13u) centred at cy | name `y = cy − 3.5`, detail `y = cy + 12.5` |
| card title | `x = card.x + 14`, `y = card.y + 25`, `text-anchor="start"` |
| tensor shape under a module | `y = module.bottom + 16`, centred on the module |
| edge label on a horizontal segment at y₀ | `y = y₀ − 6`, centred on the segment |
| edge label beside a vertical segment at x₀ | `x = x₀ + 6`, `text-anchor="start"`, `y = mid + 4` |

Width estimates (Inter): semibold 15u ≈ 8.7u per character, regular 13u ≈ 7.2u per character. Uppercase and `m`/`w`
run wider. For exact numbers use `svg_geom.py width "Vision Encoder" --fs 15 --weight 600` → `109.4`, or
`svg_geom.py label x y w h "Mean|Head"`, which prints the `<text>` lines plus the resulting padding (`OK`/`TIGHT`).

### Math: LaTeX between `$…$`

Write math as LaTeX between `$…$` inside an ordinary `<text>`, in the paper's own notation and macros. Text outside
the dollars stays in the figure's sans font; `render_svg.py` typesets each math segment with LaTeX on every run.

```xml
<!-- mixed line: the sans words and the math share one baseline (y), placed and centred as one line -->
<text class="t-sub" x="114" y="66" text-anchor="middle" fill="#4B5563">scores $S[i,v,p]$</text>
<!-- loss in a pill centred at cy: the usual baseline y = cy + 0.35·fs; the lint measures the subscript's ink -->
<text class="t-mod" x="408" y="412.25" text-anchor="middle" fill="#A84B61">$\mathcal{L}_{\text{task}}$</text>
<!-- accents, Greek, operators: plain LaTeX, or the paper's macros when rendered with --paper -->
<text class="t-mod" x="200" y="120" text-anchor="middle">$\hat{y}$</text>
<text class="t-dim" x="464" y="71" text-anchor="middle" fill="#6B7280">$z = \mu + \sigma \odot \epsilon$</text>
<!-- shape annotation: sans, unless the paper writes the shape as math -->
<text class="t-dim" x="144" y="214" text-anchor="middle" fill="#6B7280">(B, N, D)</text>
```

What the script does with such a `<text>`: it keeps it as the source (hidden, `data-tex="src" display="none"`) and
writes a generated `<g data-tex="out" class="tex-line">` right after it. That group holds one `<text>` per sans segment
and one `<g class="tex-math">` of glyph paths (latex → dvisvgm) per math segment, all on the source's baseline and
aligned by its `text-anchor`. The widths come from TeX's box metrics and the sans text's measured width (in Chromium,
with the TeX font directories added to fontconfig). In the exported PDF the math is drawn from pdflatex output, so
it embeds the real Type 1 fonts (CMMI6, CMR5, …) instead of outlines.

Rules:
- **Edit only the source `<text>`** (content, `x`, `y`, class, fill). The generated group is rebuilt whenever the source,
  the `--target` width or the TeX setup changes; edits inside it are lost.
- One line per `<text>`, and no `<tspan>` in a line that contains math. Write a literal dollar sign as `\$`.
- **Sizes**: the math base size is the text's printed size (font-size in u × pt per u at `--target`), and
  sub/superscripts get LaTeX's script sizes: 6pt → 5pt, 7pt → 5pt, 8pt → 6pt, 9pt → 6pt, 10pt → 7pt (other sizes:
  0.7× and 0.5×, never below 5pt). The lint reports each math group's printed base and script size; scripts below
  5pt are an error, below 6pt a warning. Fix it with a larger base size or a `\DeclareMathSizes` line (`--math`),
  never by shrinking, raising or redrawing the scripts by hand.
- **Fonts and notation**: render with `--paper path/to/main.tex`. The script reads the preamble, the `\input` macro
  files and local `.sty`/`.cls` files, picks the math setup (Computer Modern unless the paper loads e.g.
  `newtxmath`/`mathptmx`; `\usepackage{times}` changes only the text font, so CVPR math stays Computer Modern),
  copies math packages such as `amsmath`, `bm`, and every `\newcommand`/`\DeclareMathOperator`. If the paper writes
  `c_{FA}`, write `$c_{FA}$`, not `$c_{\mathrm{FA}}$`. The setup is stored in `<metadata id="tex-setup">`, so later
  runs reuse it. Override with `--math cm|newtx|mathptmx|newpx|...` or verbatim LaTeX; `python3 scripts/tex_math.py
  --paper main.tex --show` prints the preamble.
- Never fake math: no serif-italic classes, `<tspan dy>` subscripts, smaller separate text for indices or Unicode
  italic letters.
- Needs `latex` + `dvisvgm` (TeX Live, MiKTeX or TinyTeX) and, for real fonts in the PDF, `pdflatex` + PyMuPDF
  (`pip install pymupdf`). `--list-backends` shows what is found. Without them the script reports the untypeset math
  as an error instead of installing anything.

## 3. Boxes & containers

```xml
<!-- stage card + title -->
<rect id="card-a" x="12" y="12" width="200" height="250" rx="10" fill="#F7F8FA" stroke="#E2E6EC" stroke-width="1"/>
<text class="t-stage" x="26" y="37" fill="#1F2933">(a) Frozen Encoder</text>

<!-- generic operation without a conventional shape (fusion, pooling, sampling): rounded rect + name.
     Model components (pretrained models, heads, feature vectors) use their shapes from §5 instead. -->
<rect id="fuse" x="300" y="92" width="96" height="36" rx="7" fill="#E3F2ED" stroke="#86C0AA" stroke-width="1.2"/>
<text class="t-mod" x="348" y="115.25" text-anchor="middle" fill="#1F2933">Fusion</text>

<!-- the proposed method's own box: accent palette, 1.6 stroke, name in bold (t-ours), once per figure -->
<rect id="ours" x="590" y="164" width="88" height="44" rx="7" fill="#FDEBDC" stroke="#E79A5D" stroke-width="1.6"/>
<text class="t-mod t-ours" x="634" y="191.25" text-anchor="middle" fill="#1F2933">Ours</text>

<!-- dims chip (pill): rx = h/2 -->
<rect x="470" y="174" width="96" height="24" rx="12" fill="#EEF1F5" stroke="#A3AEBD" stroke-width="1"/>
<text class="t-dim" x="518" y="190.55" text-anchor="middle" fill="#4B5768">(B, N, D)</text>

<!-- loss pill -->
<rect id="loss" x="380" y="392" width="56" height="30" rx="15" fill="#F9E6EA" stroke="#D9909F" stroke-width="1.2"/>
```

Role fills, strokes and inks are listed in `design-system.md` §4. Bold (`t-ours`) is a figure-only emphasis for the
method's name; it does not change how the paper's text styles that name.

## 4. Connectors

### 4.1 Rounded orthogonal path formula

For each bend at corner **P**, with unit direction **d_in** arriving and **d_out** leaving and radius r (default 8u;
never more than half of either adjacent segment):

```
… L (P − r·d_in)  Q P  (P + r·d_out) …
```

The quadratic `Q` is renderer-proof and avoids arc sweep-flag mistakes. Templates (sx = sign(x₁ − x₀), sy = sign(y₁ − y₀),
target border point (x₁, y₁), arrow end pulled back 2u):

| Shape | `d` |
|---|---|
| straight → | `M x₀ y L (x₁ − 2·sx) y` |
| L: horizontal then vertical | `M x₀ y₀ L (x₁ − sx·r) y₀ Q x₁ y₀ x₁ (y₀ + sy·r) L x₁ (y₁ − 2·sy)` |
| Z: H-V-H via middle x = m | `M x₀ y₀ L (m − sx·r) y₀ Q m y₀ m (y₀ + sy·r) L m (y₁ − sy·r) Q m y₁ (m + sx·r) y₁ L (x₁ − 2·sx) y₁` |
| Z: V-H-V via middle y = m | `M x₀ y₀ L x₀ (m − sy·r) Q x₀ m (x₀ + sx·r) m L (x₁ − sx·r) m Q x₁ m x₁ (m + sy·r) L x₁ (y₁ − 2·sy)` |
| U: feedback below everything (m > y₀, y₁) | `M x₀ y₀ L x₀ (m − r) Q x₀ m (x₀ + sx·r) m L (x₁ − sx·r) m Q x₁ m x₁ (m − r) L x₁ (y₁ + 2)` |

Worked examples (from the gallery):

```xml
<!-- straight: source right edge x=76, target left edge x=140 → end at 138 -->
<path class="edge" d="M 76 407 L 138 407" fill="none" stroke="#3A6A9E" stroke-width="1.6" marker-end="url(#ah-frozen)"/>
<!-- Z (H-V-H): (196,407) → target left edge (260,465), middle x = 228 -->
<path class="edge" d="M 196 407 L 220 407 Q 228 407 228 415 L 228 457 Q 228 465 236 465 L 258 465" fill="none" stroke="#B5602A" stroke-width="1.6" marker-end="url(#ah-proposed)"/>
<!-- loss (dashed L): (316,465) → loss pill bottom (408,422) -->
<path class="edge" d="M 316 465 L 400 465 Q 408 465 408 457 L 408 424" fill="none" stroke="#A84B61" stroke-width="1.4" stroke-dasharray="5 3.5" marker-end="url(#ah-loss)"/>
```

Generate any of these with `svg_geom.py elbow x0,y0 x1,y1 --mode hvh --mid 228 --arrow --marker ah-proposed --stroke "#B5602A"`
or `svg_geom.py ortho "x0,y0 x1,y1 x2,y2 …" --arrow`. Both pull the end back 2u, shrink radii that do not fit, and warn
when the last run is too short for an arrowhead.

### 4.2 Ports, fan-out, junctions

- Ports are side midpoints: right `(x+w, y+h/2)`, left `(x, y+h/2)`, top `(x+w/2, y)`, bottom `(x+w/2, y+h)`. For two edges on one side use `h/3` and `2h/3`.
- Fan-out from one port: separate paths that share the start point and split after a ≥ 8u common stub. The lint does not flag a shared start. Add a junction dot where a trunk splits: `<circle cx= cy= r="2.2" fill="<ink>"/>`.
- Fan-in: separate paths into distinct ports, or merge onto an operator circle (§5.5).
- Skip/residual connections arc over the spine: VHV upward with m = card.y + 48 or so, clear of titles.

### 4.3 Edge labels

```xml
<text class="t-dim" x="108" y="401" text-anchor="middle" fill="#6B7280">F</text>          <!-- 6u above a horizontal edge at y=407 -->
<!-- label that must sit ON the line: white halo + both marked on-edge -->
<rect class="on-edge" x="96" y="399" width="24" height="16" rx="3" fill="#FFFFFF"/>
<text class="t-dim on-edge" x="108" y="411.55" text-anchor="middle" fill="#6B7280">z</text>
```

## 5. ML shapes

### 5.1 Encoder / decoder trapezoids (left → right flow)

Encoder: wide (input) side on the left, narrowing by `i` per side on the right. Decoder: mirrored. Rounded corners
use the same `Q` rule. Generate exactly with `svg_geom.py trapezoid x y w h --inset i --kind encoder|decoder [--flow tb]`,
which also prints the safe text box, ports and badge position.

```xml
<!-- encoder  x=100 y=98 w=88 h=100 inset=20 (svg_geom output) -->
<path id="enc" d="M 100 103 Q 100 98 104.88 99.11 L 183.12 116.89 Q 188 118 188 123 L 188 173 Q 188 178 183.12 179.11 L 104.88 196.89 Q 100 198 100 193 Z" fill="#E4EEF8" stroke="#8DB0D6" stroke-width="1.2"/>
<!-- safe text box x 106..182, y 124..172 (narrow side minus 6u); ports (100,148) → (188,148); badge at (186,120) -->
```

Polygon form (sharp corners): encoder `x,y  x+w,y+i  x+w,y+h−i  x,y+h`; decoder `x,y+i  x+w,y  x+w,y+h  x,y+h−i`.
Text must fit the **narrow** side: available height = h − 2i − 2·pad.

### 5.2 Card stack (multi-head, ×N layers, ensemble)

Draw back to front, each card offset (+dx, −dy). Front card at (x, y). Cards are opaque, so outlines do not show through.

```xml
<g class="stack">
  <rect x="260" y="154" width="30" height="44" rx="3" fill="#E4EEF8" stroke="#8DB0D6" stroke-width="1.1"/>
  <rect x="255" y="159" width="30" height="44" rx="3" fill="#E4EEF8" stroke="#8DB0D6" stroke-width="1.1"/>
  <rect x="250" y="164" width="30" height="44" rx="3" fill="#E4EEF8" stroke="#8DB0D6" stroke-width="1.1"/>
</g>
<!-- bbox x 250..290, y 154..208; leave arrows from the front card's right edge (280, 186) -->
```

### 5.3 Isometric cuboid (feature map / latent tensor)

Front face rect (x, y, w, h). Depth d at 45° gives (dx, dy) = (0.707d, 0.707d). Top face is lighter, side face darker.

```xml
<g class="cuboid">
  <polygon points="330 164 337.07 156.93 365.07 156.93 358 164" fill="#F0F6FB" stroke="#8DB0D6" stroke-width="1" stroke-linejoin="round"/>
  <polygon points="358 164 365.07 156.93 365.07 200.93 358 208" fill="#C6D8EC" stroke="#8DB0D6" stroke-width="1" stroke-linejoin="round"/>
  <rect x="330" y="164" width="28" height="44" fill="#E4EEF8" stroke="#8DB0D6" stroke-width="1"/>
</g>
```

`svg_geom.py cuboid x y w h --depth 10 --fill <fill> --stroke <stroke>` computes the faces and shades for any role.

### 5.4 Token row

`<use xlink:href="#tok-row" x= y=/>` draws five 8×8 tokens with a 3u gap (52×8 total; the last one is accent-coloured).
For other counts, repeat `<rect width="8" height="8" rx="2">` every 11u.

### 5.5 Operators

`<use xlink:href="#op-add" x="cx" y="cy"/>` (⊕), `#op-mul` (⊗), `#op-cat` (∥). These are r = 7 circles centred on (cx, cy).
Connect to them like any box: their left border is at cx − 7.

### 5.6 Layer stack (pretrained / frozen model: VLM, LLM, vision encoder)

A block of 3–5 layer slabs that the data crosses in flow order, in the `frozen` palette with a frozen badge. Put the
name under the block (T2, `y = bottom + 16`) or inside a wide block above the slabs.

```xml
<g class="layers">   <!-- svg_geom.py layers 400 560 52 64 --n 4 --pad 6 --gap 3 -->
  <rect x="400" y="560" width="52" height="64" rx="7" fill="#E4EEF8" stroke="#8DB0D6" stroke-width="1.2"/>
  <rect x="406" y="566" width="7.75" height="52" rx="2.5" fill="#BDD2E9" stroke="#8DB0D6" stroke-width="0.8"/>
  <rect x="416.75" y="566" width="7.75" height="52" rx="2.5" fill="#BDD2E9" stroke="#8DB0D6" stroke-width="0.8"/>
  <rect x="427.5" y="566" width="7.75" height="52" rx="2.5" fill="#BDD2E9" stroke="#8DB0D6" stroke-width="0.8"/>
  <rect x="438.25" y="566" width="7.75" height="52" rx="2.5" fill="#BDD2E9" stroke="#8DB0D6" stroke-width="0.8"/>
</g>
<use class="badge" xlink:href="#badge-frozen" x="450" y="562"/>
```

`--flow tb` gives horizontal slabs for top-to-bottom figures.

### 5.7 Feature vector

A bar split into 6–8 cells, vertical in left-to-right figures; `--shade` fills the cells like values. Label it with
its symbol under the bar (`$f$`).

```bash
python3 "$SKILL_DIR/scripts/svg_geom.py" vector 480 564 12 56 --cells 6 --shade --seed 5 --fill "#3A6A9E"
```

### 5.8 Small trainable head (linear, logistic, MLP, classifier, probe)

A small trapezoid narrowing toward its output, with the head's function inside: the `glyph-sigmoid` curve (§6) or the
symbol as LaTeX (`$\sigma$`, `$\mathrm{softmax}$`). Name it under the shape when the name matters.

```xml
<!-- svg_geom.py trapezoid 520 568 36 48 --inset 8 --r 3 --fill "#E3F2ED" --stroke "#86C0AA" -->
<path d="M 520 571 Q 520 568 522.93 568.65 L 553.07 575.35 Q 556 576 556 579 L 556 605 Q 556 608 553.07 608.65 L 522.93 615.35 Q 520 616 520 613 Z" fill="#E3F2ED" stroke="#86C0AA" stroke-width="1.2"/>
<use xlink:href="#glyph-sigmoid" x="537" y="592"/>
<use class="badge" xlink:href="#badge-train" x="554" y="578"/>
```

## 6. Mini visualisations (optional `<defs>`)

Paste only the ones you use into `<defs>`. Place with `<use xlink:href="#thumb-…" x="left" y="top"/>`. Scale with
`transform="translate(x,y) scale(s)"` and no x/y. Sizes: images 40×40; noise/heat/attention 36×36 plus a 1.5u frame;
bell 32×14; tokens 52×8; augmented views 40×40 (2×2: original, flipped, colour-jittered, masked); sigmoid
glyph 16×10 centred on (x, y). Make variants with `svg_geom.py grid … --mode noise|heat|attn|seg|patch --seed N`
(compact output, one path per opacity level).

```xml
<defs>
  <g id="op-add"><circle r="7" fill="#FFFFFF" stroke="#4B5768" stroke-width="1.2"/><path d="M-3.6 0H3.6M0 -3.6V3.6" stroke="#4B5768" stroke-width="1.4" stroke-linecap="round"/></g>
  <g id="op-mul"><circle r="7" fill="#FFFFFF" stroke="#4B5768" stroke-width="1.2"/><path d="M-2.6 -2.6L2.6 2.6M2.6 -2.6L-2.6 2.6" stroke="#4B5768" stroke-width="1.4" stroke-linecap="round"/></g>
  <g id="op-cat"><circle r="7" fill="#FFFFFF" stroke="#4B5768" stroke-width="1.2"/><path d="M-1.6 -3.6V3.6M1.6 -3.6V3.6" stroke="#4B5768" stroke-width="1.4" stroke-linecap="round"/></g>
  <g id="thumb-image">
    <rect width="40" height="40" rx="3" fill="#DCE8F5"/>
    <circle cx="29" cy="11" r="4.5" fill="#F2C46D"/>
    <path d="M0 30L11 18L19 26L26 20L40 31V37Q40 40 37 40H3Q0 40 0 37Z" fill="#9CC3AE"/>
    <path d="M0 35L9 29L18 34L27 28L40 36V37Q40 40 37 40H3Q0 40 0 37Z" fill="#6E9A86"/>
    <rect width="40" height="40" rx="3" fill="none" stroke="#A3AEBD" stroke-width="1"/>
  </g>
  <g id="thumb-patches">
    <use xlink:href="#thumb-image"/>
    <path d="M10 0V40M20 0V40M30 0V40M0 10H40M0 20H40M0 30H40" stroke="#FFFFFF" stroke-width="1.2"/>
  </g>
  <g id="thumb-seg">
    <rect width="40" height="40" rx="3" fill="#B7D3EE"/>
    <path d="M0 30L11 18L19 26L26 20L40 31V37Q40 40 37 40H3Q0 40 0 37Z" fill="#A8D5BF"/>
    <path d="M0 35L9 29L18 34L27 28L40 36V37Q40 40 37 40H3Q0 40 0 37Z" fill="#E8D99A"/>
    <circle cx="29" cy="11" r="4.5" fill="#F2B98A"/>
    <rect width="40" height="40" rx="3" fill="none" stroke="#A3AEBD" stroke-width="1"/>
  </g>
  <g id="thumb-noise">
    <path fill="#4B5563" fill-opacity="0.17" d="M24.53 0h5.33v5.33h-5.33zM0 12.27h5.33v5.33h-5.33zM24.53 12.27h5.33v5.33h-5.33zM30.67 12.27h5.33v5.33h-5.33zM0 18.4h5.33v5.33h-5.33z"/>
    <path fill="#4B5563" fill-opacity="0.33" d="M0 0h5.33v5.33h-5.33zM12.27 0h5.33v5.33h-5.33zM18.4 0h5.33v5.33h-5.33zM30.67 0h5.33v5.33h-5.33zM6.13 18.4h5.33v5.33h-5.33zM30.67 18.4h5.33v5.33h-5.33zM12.27 24.53h5.33v5.33h-5.33zM0 30.67h5.33v5.33h-5.33zM6.13 30.67h5.33v5.33h-5.33zM12.27 30.67h5.33v5.33h-5.33z"/>
    <path fill="#4B5563" fill-opacity="0.50" d="M18.4 6.13h5.33v5.33h-5.33zM30.67 6.13h5.33v5.33h-5.33zM12.27 18.4h5.33v5.33h-5.33zM18.4 18.4h5.33v5.33h-5.33zM0 24.53h5.33v5.33h-5.33zM18.4 30.67h5.33v5.33h-5.33zM30.67 30.67h5.33v5.33h-5.33z"/>
    <path fill="#4B5563" fill-opacity="0.67" d="M6.13 0h5.33v5.33h-5.33zM6.13 6.13h5.33v5.33h-5.33zM24.53 6.13h5.33v5.33h-5.33zM6.13 12.27h5.33v5.33h-5.33zM12.27 12.27h5.33v5.33h-5.33zM18.4 12.27h5.33v5.33h-5.33zM24.53 18.4h5.33v5.33h-5.33zM6.13 24.53h5.33v5.33h-5.33zM24.53 24.53h5.33v5.33h-5.33zM24.53 30.67h5.33v5.33h-5.33z"/>
    <path fill="#4B5563" fill-opacity="0.83" d="M0 6.13h5.33v5.33h-5.33zM12.27 6.13h5.33v5.33h-5.33zM18.4 24.53h5.33v5.33h-5.33zM30.67 24.53h5.33v5.33h-5.33z"/>
    <rect x="-1.5" y="-1.5" width="39" height="39" rx="3" fill="none" stroke="#A3AEBD" stroke-width="1"/>
  </g>
  <g id="thumb-heat">
    <path fill="#D9772F" fill-opacity="0.17" d="M0 0h5.33v5.33h-5.33zM0 6.13h5.33v5.33h-5.33zM0 12.27h5.33v5.33h-5.33zM0 18.4h5.33v5.33h-5.33zM0 24.53h5.33v5.33h-5.33zM0 30.67h5.33v5.33h-5.33zM6.13 30.67h5.33v5.33h-5.33z"/>
    <path fill="#D9772F" fill-opacity="0.33" d="M6.13 0h5.33v5.33h-5.33zM6.13 6.13h5.33v5.33h-5.33zM6.13 12.27h5.33v5.33h-5.33zM6.13 18.4h5.33v5.33h-5.33zM6.13 24.53h5.33v5.33h-5.33zM12.27 30.67h5.33v5.33h-5.33z"/>
    <path fill="#D9772F" fill-opacity="0.50" d="M12.27 0h5.33v5.33h-5.33zM30.67 0h5.33v5.33h-5.33zM12.27 24.53h5.33v5.33h-5.33zM18.4 30.67h5.33v5.33h-5.33zM24.53 30.67h5.33v5.33h-5.33zM30.67 30.67h5.33v5.33h-5.33z"/>
    <path fill="#D9772F" fill-opacity="0.67" d="M18.4 0h5.33v5.33h-5.33zM24.53 0h5.33v5.33h-5.33zM12.27 6.13h5.33v5.33h-5.33zM30.67 6.13h5.33v5.33h-5.33zM12.27 12.27h5.33v5.33h-5.33zM30.67 12.27h5.33v5.33h-5.33zM12.27 18.4h5.33v5.33h-5.33zM30.67 18.4h5.33v5.33h-5.33zM18.4 24.53h5.33v5.33h-5.33zM24.53 24.53h5.33v5.33h-5.33zM30.67 24.53h5.33v5.33h-5.33z"/>
    <path fill="#D9772F" fill-opacity="0.83" d="M18.4 6.13h5.33v5.33h-5.33zM24.53 6.13h5.33v5.33h-5.33zM18.4 12.27h5.33v5.33h-5.33zM24.53 12.27h5.33v5.33h-5.33zM18.4 18.4h5.33v5.33h-5.33zM24.53 18.4h5.33v5.33h-5.33z"/>
    <rect x="-1.5" y="-1.5" width="39" height="39" rx="3" fill="none" stroke="#A3AEBD" stroke-width="1"/>
  </g>
  <g id="thumb-attn">
    <path fill="#3A6A9E" fill-opacity="0.06" d="M12.27 0h5.33v5.33h-5.33zM24.53 0h5.33v5.33h-5.33zM30.67 0h5.33v5.33h-5.33zM30.67 6.13h5.33v5.33h-5.33zM24.53 12.27h5.33v5.33h-5.33zM30.67 12.27h5.33v5.33h-5.33zM30.67 18.4h5.33v5.33h-5.33zM0 30.67h5.33v5.33h-5.33z"/>
    <path fill="#3A6A9E" fill-opacity="0.17" d="M6.13 0h5.33v5.33h-5.33zM18.4 0h5.33v5.33h-5.33zM0 6.13h5.33v5.33h-5.33zM18.4 6.13h5.33v5.33h-5.33zM24.53 6.13h5.33v5.33h-5.33zM0 12.27h5.33v5.33h-5.33zM6.13 12.27h5.33v5.33h-5.33zM18.4 12.27h5.33v5.33h-5.33zM6.13 18.4h5.33v5.33h-5.33zM0 24.53h5.33v5.33h-5.33zM6.13 24.53h5.33v5.33h-5.33zM12.27 24.53h5.33v5.33h-5.33zM6.13 30.67h5.33v5.33h-5.33zM12.27 30.67h5.33v5.33h-5.33zM18.4 30.67h5.33v5.33h-5.33zM24.53 30.67h5.33v5.33h-5.33z"/>
    <path fill="#3A6A9E" fill-opacity="0.33" d="M0 18.4h5.33v5.33h-5.33zM12.27 18.4h5.33v5.33h-5.33zM24.53 18.4h5.33v5.33h-5.33zM18.4 24.53h5.33v5.33h-5.33zM30.67 24.53h5.33v5.33h-5.33z"/>
    <path fill="#3A6A9E" fill-opacity="0.50" d="M12.27 6.13h5.33v5.33h-5.33z"/>
    <path fill="#3A6A9E" fill-opacity="0.83" d="M0 0h5.33v5.33h-5.33zM6.13 6.13h5.33v5.33h-5.33zM12.27 12.27h5.33v5.33h-5.33zM18.4 18.4h5.33v5.33h-5.33zM24.53 24.53h5.33v5.33h-5.33zM30.67 30.67h5.33v5.33h-5.33z"/>
    <rect x="-1.5" y="-1.5" width="39" height="39" rx="3" fill="none" stroke="#A3AEBD" stroke-width="1"/>
  </g>
  <g id="glyph-bell">
    <path d="M0 14C9.6 14 11.5 0 16 0C20.5 0 22.4 14 32 14Z" fill="#EBA26A" fill-opacity="0.35"/>
    <path d="M0 14C9.6 14 11.5 0 16 0C20.5 0 22.4 14 32 14" fill="none" stroke="#B5602A" stroke-width="1.3" stroke-linecap="round"/>
    <path d="M0 14H32" stroke="#B5602A" stroke-width="0.8" stroke-opacity="0.6"/>
  </g>
  <g id="tok-row">
    <rect width="8" height="8" rx="2" fill="#E4EEF8" stroke="#8DB0D6"/><rect x="11" width="8" height="8" rx="2" fill="#E4EEF8" stroke="#8DB0D6"/><rect x="22" width="8" height="8" rx="2" fill="#E4EEF8" stroke="#8DB0D6"/><rect x="33" width="8" height="8" rx="2" fill="#E4EEF8" stroke="#8DB0D6"/><rect x="44" width="8" height="8" rx="2" fill="#FDEBDC" stroke="#E79A5D"/>
  </g>
  <g id="glyph-sigmoid"><path d="M-8 5C0 5 0 -5 8 -5" fill="none" stroke="#4B5768" stroke-width="1.4" stroke-linecap="round"/></g>
  <g id="thumb-views">   <!-- needs thumb-image -->
    <use xlink:href="#thumb-image" transform="scale(0.475)"/>
    <use xlink:href="#thumb-image" transform="translate(40 0) scale(-0.475 0.475)"/>
    <use xlink:href="#thumb-image" transform="translate(0 21) scale(0.475)"/>
    <rect x="0" y="21" width="19" height="19" rx="1.4" fill="#F2C46D" fill-opacity="0.35"/>
    <use xlink:href="#thumb-image" transform="translate(21 21) scale(0.475)"/>
    <rect x="27.5" y="27.5" width="7" height="7" fill="#6B7280" fill-opacity="0.6"/>
  </g>
</defs>
```

## 7. Badges

Frozen = snowflake, trainable = flame (`badge-lock` is an alternative for frozen). Each is a r = 7.5 white disc, pure
vector (emoji render as bitmaps or tofu in PDF). Place the centre 2u inside the module's top-right corner so the badge
straddles it:

```xml
<!-- module rect x=590 y=164 w=88 → corner (678,164) → badge centre (676,166) -->
<use class="badge" xlink:href="#badge-train" x="676" y="166"/>
<!-- encoder trapezoid: corner = top-right vertex (x+w, y+inset) → centre (x+w−2, y+inset+2) -->
<use class="badge" xlink:href="#badge-frozen" x="186" y="120"/>
```

Keep the label's right edge ≥ 10u left of the badge centre. For rect modules, centre the label as usual; the badge
only occupies the corner.

## 8. Legend

One row, T3 text, ≥ 20u between items. Icon-to-text gap 8u. Text baseline = icon centre + 4.55 (that is, 0.35 × 13).

```xml
<g class="legend">
  <path d="M560 434H586" fill="none" stroke="#4B5768" stroke-width="1.6" marker-end="url(#ah-data)"/>
  <text class="t-dim" x="596" y="438.55" fill="#4B5563">Forward</text>
  <path d="M670 434H696" fill="none" stroke="#A84B61" stroke-width="1.4" stroke-dasharray="5 3.5" marker-end="url(#ah-loss)"/>
  <text class="t-dim" x="706" y="438.55" fill="#4B5563">Loss</text>
  <use class="badge" xlink:href="#badge-frozen" x="567.5" y="404"/>
  <text class="t-dim" x="580" y="408.55" fill="#4B5563">Frozen</text>
  <use class="badge" xlink:href="#badge-train" x="657.5" y="404"/>
  <text class="t-dim" x="670" y="408.55" fill="#4B5563">Trainable</text>
  <rect x="560" y="456" width="16" height="11" rx="3" fill="#FDEBDC" stroke="#E79A5D" stroke-width="1.2"/>
  <text class="t-dim" x="584" y="466.05" fill="#4B5563">Proposed</text>
</g>
```

Text x of the next item = previous text x + text width (`svg_geom.py width`) + 20 + icon width + 8.

## 9. Renderer-safe subset

Chromium, librsvg, cairosvg, resvg and Inkscape agree on:
- presentation attributes, hex colours, `fill-opacity`/`stroke-opacity`;
- one `<style>` with plain class selectors and `px` units (`font-size: 15px`);
- `<use xlink:href="#g-id">` pointing at a `<g>` in `<defs>` (avoid `<symbol>` sizing), with `xmlns:xlink` declared on the root;
- `<marker markerUnits="userSpaceOnUse" orient="auto">`, one marker per colour.

Avoid these, which the lint warns about: `filter` (drop shadows rasterise in PDF), `mix-blend-mode`, `dominant-baseline`,
`alignment-baseline`, `textLength`, `context-stroke`, `orient="auto-start-reverse"`, CSS `var(--x)`, `<foreignObject>`,
`@import`/`@font-face`, external `href`s, emoji. Use `clip-path` only when unavoidable.

### Fonts in the exported PDF

- Chromium embeds TrueType fonts as TrueType but CFF-flavoured OpenType fonts (`.otf`: Inter from many distributions,
  TeX Gyre, Latin Modern) as **Type 3**, which camera-ready checkers reject. `--export` then outlines the text
  (`pdftocairo`, or PyMuPDF when poppler is missing); if neither is available it reports `pdf-outline-unavailable`.
- To keep real, selectable fonts instead, convert the figure fonts to TrueType (fontTools' `otf2ttf` snippet,
  `Snippets/otf2ttf.py` in the fontTools repository) into a folder and render with `--font-dir <folder>`. Family names
  stay the same, so the SVG needs no change; the CFF copies of those families are hidden from the renderer for that run.
  Check the result with `pdffonts`: every font should be `TrueType` or `Type 1`.
- A character missing from the figure font (Inter has no `∗` U+2217, `⊙` or `∇`) is drawn in a fallback font with a
  different design, and a CFF fallback adds Type 3 fonts. The lint reports it as `glyph-fallback`. Write the symbol as
  `$…$` math, or give that `<tspan>` a `font-family` that has the glyph.

## 10. `svg_geom.py` cheat-sheet

```bash
G="$SKILL_DIR/scripts/svg_geom.py"
python3 $G elbow 282,148 300,110 --mode hvh --mid 288 --arrow --marker ah-data      # connector between ports
python3 $G ortho "470,190 470,240 650,240 650,198" --arrow --dash --marker ah-loss --stroke "#A84B61"
python3 $G trapezoid 100 98 88 100 --inset 20 --kind encoder                         # + safe text box, ports, badge
python3 $G trapezoid 600 110 76 80 --inset 16 --kind decoder --fill "#E3F2ED" --stroke "#86C0AA"
python3 $G stack 250 164 30 44 --n 3 --dx 5 --dy 5
python3 $G cuboid 330 164 28 44 --depth 10 --fill "#FDEBDC" --stroke "#E79A5D"
python3 $G layers 400 560 52 64 --n 4 --pad 6 --gap 3                                # pretrained model (layer stack)
python3 $G vector 480 564 12 56 --cells 6 --shade --fill "#3A6A9E"                    # feature vector
python3 $G grid 0 0 36 36 --rows 6 --cols 6 --gap 0.8 --mode heat --seed 2 --color "#D9772F"
python3 $G bell 384 298 32 14
python3 $G label 300 92 96 36 "Fusion" --fs 15 --cls t-mod                           # prints <text> + padding check
python3 $G width "(b) Uncertainty-Aware Module" --fs 17 --weight 600                 # → 250.7
```
