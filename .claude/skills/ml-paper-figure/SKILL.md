---
name: ml-paper-figure
description: >-
  Design publication-ready Figure 1 diagrams for ML/AI papers (NeurIPS, ICML, ICLR, CVPR, ECCV, ACL, AAAI):
  framework overviews, model-architecture schematics, method/pipeline and teaser figures. Produces one
  self-contained SVG plus a vector PDF for LaTeX \includegraphics and a high-res PNG, using a render-and-critique
  loop with an offline lint script. Use this skill whenever the user wants to draw, redesign or polish an
  overview/architecture/pipeline/method figure for a paper, poster or rebuttal, or hands over a Methods section,
  LaTeX/Markdown text or PyTorch model code and wants it turned into a diagram — even if they only say
  "make Figure 1", "draw my model", "visualize this architecture", "논문 그림", "모델 구조도 그려줘" or
  "파이프라인 다이어그램". Not for plots of experimental results (bar/line charts, tables) or cloud-infrastructure diagrams.
---

# ML Paper Figure 1

Build the figure as hand-written SVG in four gated phases: **Plan → Draft → Render & Critique (≤ 3 rounds) → Export**.
Do not start writing SVG before the blueprint exists. Coordinates chosen ad hoc are the main cause of overflowing
labels and arrows through boxes, and the lint and the visual review only work well against a plan.

`SKILL_DIR` below means this skill's base directory. Scripts run offline; check the renderer once per session:

```bash
python3 "$SKILL_DIR/scripts/render_svg.py" --list-backends
```

The script picks Chromium (Playwright), rsvg-convert, inkscape, cairosvg or resvg, whichever is installed. Exact geometry
lint needs Chromium. Without it the checks are approximate, so lean harder on the visual review.

## Reference files (read when the phase says so)

| File | Read it when |
|---|---|
| `references/design-system.md` | Phase 1. It covers canvas size per venue, layout spacing, palette roles, type tiers, shape metaphors, connector styles. These are defaults; adapt them when the content calls for it. |
| `references/svg-primitives.md` | Phase 2. It holds the copy-paste `<defs>` (markers, badges, thumbnails), text-centering and connector formulas, and ML shape templates. |
| `assets/primitives-gallery.png` | Optional. A rendered view of every primitive, useful for picking metaphors. |
| `assets/example-figure1.svg` (+ `.png`) | Optional. A complete, lint-clean Figure 1 (frozen encoder → proposed module → decoder + dashed losses) to copy structure from. |
| `scripts/svg_geom.py` | Use it any time you need exact coordinates. It prints connector paths, trapezoids, stacks, grids and centred labels with a fit check. |

## Phase 1: Plan (blueprint before any SVG)

1. **Extract the structure** from whatever the user gave (prose, Methods LaTeX/Markdown, PyTorch `nn.Module` code):
   - stages (2–4 groups that become cards (a), (b), (c)), and the modules inside each;
   - which module(s) are the paper's **contribution** (gets the accent colour), which are **frozen/pretrained**, which are **trainable**;
   - tensors on the main path with shapes, e.g. `(B, 3, H, W) → (B, N, D)`, using the paper's own symbols;
   - flows: forward data (solid), losses/supervision (dashed), gradients/feedback, skip connections, inference-only vs training-only paths.
   From code: `__init__` lists modules, `forward()` gives the order and shapes, `requires_grad_(False)`/`.eval()`/`torch.no_grad()` mark frozen parts, and loss terms come from the training step.
   If the source does not say what is novel or what is frozen, ask one short question. Otherwise proceed with reasonable assumptions and state them.
2. **Fix the canvas**: target venue and width, and `viewBox` from the table in `design-system.md` §2. The default is 2 units per printed pt, e.g. NeurIPS `800 × ~300`.
3. **Write the blueprint** to `<name>.blueprint.md` next to the figure, and summarise it to the user in a few lines. Files go where the user keeps
   paper figures (default: `figures/` in their project):

```yaml
figure: figure1_overview      # file stem
target: neurips               # render_svg.py --target value; viewBox 800 x 300 (2u = 1pt)
flow: left-to-right           # or top-to-bottom / two-row snake
stages:                       # card x-ranges tile the width with gaps; cards share one y-range
  - id: a
    title: "(a) Frozen Encoder"
    box: [12, 12, 186, 240]   # x, y, w, h
    modules:
      - {id: img, kind: thumb-patches, box: [28, 120, 40, 40], label: "x", dims: "3×H×W"}
      - {id: enc, kind: trapezoid-encoder, role: frozen, badge: frozen, box: [96, 90, 88, 100], inset: 18, label: "Vision|Encoder"}
  - id: b
    # ...
edges:
  - {from: img.right, to: enc.left, style: forward, role: data}
  - {from: dec.bottom, to: loss.top, style: loss, label: "ŷ"}
colors: {enc: frozen, uam: proposed, dec: train, loss: loss}   # palette roles from design-system.md §4
legend: [forward, loss, frozen, trainable]                    # only encodings that need explaining
notes: "proposed card ~45% of width; spine at y = 140"
```

Blueprint checks before moving on: every module has a box; boxes inside a card leave ≥ 14u card padding; neighbours that an arrow joins are ≥ 28u apart (≥ 40u if the arrow carries a label); label widths fit their boxes (`svg_geom.py label …` reports padding); and the spine (main path) is one straight line where possible.

## Phase 2: Draft (one self-contained SVG)

Read `references/svg-primitives.md`, then write `<name>.svg`:

- Start from the skeleton and core `<defs>` there (font stack, typography classes, one arrowhead per palette role, vector badges). Add optional thumbnail defs only when used.
- **Self-contained**: no external images, no web fonts or `@import`, no `<foreignObject>`, no scripts, no emoji. Use the vector badges instead of ❄️/🔥, because emoji become bitmaps or tofu in PDFs.
- Draw order: background → cards → edges → modules → labels → badges → legend. Edges sit under modules so their ends tuck under borders.
- Give modules ids (`id="enc"`), connectors `class="edge"` and `fill="none"`, and mini visuals `data-lint="ignore"`. Lint messages then name elements you can find.
- Compute coordinates with the formulas or `svg_geom.py`, not by eye. Text centre baseline is `cy + 0.35 × font-size`. Paths end **2u before** the target border, since the standard arrowhead tip overshoots by 2u.

## Phase 3: Render & critique (loop, max 3 rounds)

Each round:

1. Render and lint:
   ```bash
   python3 "$SKILL_DIR/scripts/render_svg.py" <name>.svg --target <venue>     # venue: neurips (default), icml, cvpr, …-col, or 5.5in
   ```
   This writes `<name>.png`, `<name>.debug.png` (coordinate grid plus numbered boxes around each issue `E#`/`W#`) and
   `<name>.preview.png` (the figure at printed size), and prints errors and warnings with coordinates.
2. **Look at the images yourself.** Read `<name>.debug.png` first, then `<name>.preview.png`. The lint cannot judge composition, so the visual pass is required.
3. Walk the checklist and write a short critique: one line per defect, with the fix in coordinates.
   - [ ] **Text fit**: no label touches or crosses its box border; module labels have ≥ 8u side padding.
   - [ ] **Arrows**: none pass through a module or label; arrowheads touch target borders (no gap, no piercing); no avoidable crossings; flow direction is obvious.
   - [ ] **Spacing & alignment**: equal gaps between siblings, rows share centre lines, same-type boxes share sizes, card padding is uniform, and no corner is crowded while another sits empty.
   - [ ] **Print legibility** (`preview.png`): smallest text still readable; script reports min ≥ 6pt at the target width; strokes visible; roles distinguishable.
   - [ ] **Hierarchy**: the proposed module is the first thing the eye lands on; stage titles (a)/(b)/(c) are scannable; one accent colour.
   - [ ] **Semantics**: every blueprint module and edge is present and correct; solid = forward, dashed = loss; badges and legend match what is drawn; notation matches the paper.
4. Fix, then re-render. Stop when there are **0 errors** and every checklist item passes, or a remaining warning is a deliberate choice you can justify (say which, and why). Lint warnings are hints, not verdicts: a warning you have inspected and judged fine needs no change.

After round 3, stop iterating even if minor issues remain, and list them in the report.

## Phase 4: Export

```bash
python3 "$SKILL_DIR/scripts/render_svg.py" <name>.svg --target <venue> --export
```

This produces `<name>.pdf` (vector, page size equals the printed width, so its text sizes are the real printed sizes), a high-res `<name>.png` (3 px/u, or `--dpi 300`), and PDF checks: single page, fonts embedded (no Type 3), no rasterised content, and the PDF matching the PNG. If the renderer would embed Type 3 fonts (Chromium does this for CFF fonts such as Inter `.otf`, and NeurIPS/ICML-style checkers flag them), the text is converted to vector outlines automatically (`--pdf-text auto|fonts|outline`). It also removes the review images. Then give the user:

- the files (`.svg` source, `.pdf` for LaTeX, `.png` for slides/preview);
- a LaTeX snippet matching the target width:
  ```latex
  \begin{figure*}[t]   % use figure + \linewidth for single-column venues (NeurIPS/ICLR) or column-width figures
    \centering
    \includegraphics[width=\textwidth]{figures/<name>.pdf}
    \caption{...}\label{fig:overview}
  \end{figure*}
  ```
- a short report: the target and smallest printed font size, critique rounds run and what changed, and any accepted warnings.

## Quality bar (what "done" means)

- Readable at the printed width: text ≥ 6pt, at most 4 font sizes, line weights ≥ 0.5pt.
- Zero lint errors. No text overflow, overlaps, out-of-canvas elements, broken refs or emoji.
- Every arrow starts and ends on a border, never runs through a module or label, and follows rounded orthogonal routes.
- One clear focal point (the contribution), consistent role colours, and a legend only for non-obvious encodings.
- Faithful to the paper: module names, symbols and tensor shapes match the text or code. Nothing is invented. Mark anything assumed.
- Deliverables are a single self-contained SVG, a vector PDF (embedded or outlined fonts, never Type 3), and a PNG, all rendered locally with no cloud APIs.
