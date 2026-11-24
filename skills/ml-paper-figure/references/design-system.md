# Design system: ML paper Figure 1

These are defaults, not laws. Start here, then deviate when the content calls for it, and note the reason in the
blueprint. The goal is the quiet, structured look of strong NeurIPS/CVPR overview figures: one focal point, a
legible flow, nothing decorative.

## Contents
1. Tone
2. Canvas & scale
3. Layout & containers
4. Colour palette
5. Typography
6. Shapes & ML conventions
7. Connectors
8. Badges, legend, annotations
9. Information density
10. Adapting the defaults
11. Anti-patterns

---

## 1. Tone

- **One focal point.** A reviewer should find "what is new" in about three seconds. The proposed module is the only warm, accented element; frozen and standard parts recede.
- **Flat vector.** No drop shadows, glows, bevels or decorative gradients. Use 3D only as a tensor metaphor (stacks, cuboids). No clip-art.
- **Pure white canvas (`#FFFFFF`)**, light neutral cards for grouping, pastel role fills, and dark role inks for lines, text accents and arrowheads.

## 2. Canvas & scale

Design at **2 user units (u) per printed point**: `viewBox` width = 2 × the figure's printed width in pt. Every size in
these references assumes this scale, so a 15u label prints at 7.5pt. `render_svg.py --target <venue>` reports the exact pt
value of every font size in the file.

| Venue (environment) | Printed width | pt | `viewBox` width | `--target` |
|---|---|---|---|---|
| NeurIPS / ICLR / COLM (`figure`, full text width) | 5.5 in | 396 | **800** | `neurips` / `iclr` |
| ICML (`figure*`) | 6.75 in | 486 | 970 | `icml` |
| ICML (`figure`, one column) | 3.25 in | 234 | 470 | `icml-col` |
| CVPR / ICCV / WACV (`figure*`) | 6.875 in | 495 | **1000** | `cvpr` |
| CVPR / ICCV (`figure`, one column) | 3.28 in | 236 | 470 | `cvpr-col` |
| ECCV / LNCS (`figure`) | 12.2 cm | 346 | 700 | `eccv` |
| ACL / EMNLP (`figure*`) | 16 cm | 454 | 900 | `acl` |
| ACL / EMNLP (`figure`, one column) | 7.7 cm | 218 | 440 | `acl-col` |
| AAAI (`figure*`) | 7 in | 504 | 1000 | `aaai` |

- **Height.** A full-width Figure 1 is usually 0.3–0.45 × its width (aspect 2.2:1 to 3.3:1). Keep it ≤ 0.5 × width so it does not eat the first page. Column-width figures run 0.6–1.0 × width.
- Set `width`/`height` on the root `<svg>` equal to the `viewBox` size.
- **Grid.** Put coordinates on a 4u grid (8u for major spacing). Use half units only for text baselines.
- Unknown venue: default to `neurips` (the narrowest common full width), which then holds up everywhere.

## 3. Layout & containers

**Reading order.** Pipelines read left → right (default). Use top → bottom for column figures and deep stacks. For more
than ~6 sequential steps use two rows (row 1 left→right, a down-turn, row 2 left→right) and avoid right→left backtracking.

**Stage cards** ((a), (b), (c)) group the 2–4 stages of the method:
- fill `#F7F8FA`, stroke `#E2E6EC` 1u, `rx` 10–12;
- title inside, top-left: `(a) Stage Name` in T1, x = card.x + 14, baseline = card.y + 25;
- the card holding the contribution may be wider (≈ 40–50 % of the canvas); keep context stages compact;
- skip cards entirely for a single-stage figure, where they add nothing.

**Spacing** (in u; the lint enforces the numbers marked ✓):

| Gap | Default | Notes |
|---|---|---|
| canvas margin | ≥ 12 | ✓ warns below 6 |
| card padding (sides, bottom) | 14–16 | title band ≈ 36 at the top |
| between cards | 14–20 | equal everywhere |
| between modules joined by an arrow | ≥ 28 | 2u start + ≥ 10u shaft + 8u head + 2u tip overshoot + slack |
| …if the arrow carries a label | ≥ 40 | label sits above the shaft |
| text padding inside a module | ≥ 8 horizontal, ≥ 5 vertical | ✓ warns below 3 |
| between separate text items | ≥ 2 | ✓ |

**Alignment.**
- The main data path (the *spine*) is one straight horizontal line wherever possible, at the same y across cards.
- Branches (heads, losses, conditioning) sit symmetrically above or below the spine.
- Siblings of the same type share width and height. Boxes in a row share their centre y; columns share their centre x.
- Near misses of 1–3u look careless at print scale, and the lint flags them.

## 4. Colour palette

Low-saturation pastels derived from the Okabe–Ito colour-blind-safe hues. Each role has a **fill** (box interior),
a **stroke** (box outline) and an **ink** (text accents, arrows that leave this role, arrowheads, icons).

| Role | Use for | Fill | Stroke | Ink |
|---|---|---|---|---|
| `card` | stage containers | `#F7F8FA` | `#E2E6EC` | `#1F2933` (title) |
| `data` | inputs, outputs, tensors, tokens, prompts | `#EEF1F5` | `#A3AEBD` | `#4B5768` |
| `frozen` | pretrained / fixed backbone, teacher | `#E4EEF8` | `#8DB0D6` | `#3A6A9E` |
| `proposed` | **your contribution** (accent; one per figure) | `#FDEBDC` | `#E79A5D` | `#B5602A` |
| `train` | trainable standard parts: heads, decoders, adapters | `#E3F2ED` | `#86C0AA` | `#3B806A` |
| `loss` | objectives, supervision, ground truth | `#F9E6EA` | `#D9909F` | `#A84B61` |
| `aux` | memory, retrieval, optional / inference-only paths | `#EEEAF6` | `#A99BCB` | `#6A5A9B` |
| `highlight` | callouts, zoom-in frames (sparingly) | `#FBF3D6` | `#DDBF5F` | `#8C6D12` |

Text colours: primary `#1F2933` (module names, titles), secondary `#4B5563` (sub-labels, legend), muted `#6B7280`
(tensor shapes, notes). Never use pure black.

Rules:
- **One accent.** The proposed orange appears only on the contribution (and the trainable flame badge).
- **Arrows take the ink of the module they leave**, which shows at a glance who produces what. Loss and supervision paths always use the `loss` ink.
- The proposed module also gets a thicker outline (1.6u vs 1.2u), so it stays the focal point in grayscale print.
- **Never encode meaning by colour alone.** Pair it with a label, line style (solid vs dashed), badge or shape. Blue vs orange is the primary contrast and is safe for all common colour-vision deficiencies.
- Use at most 4–5 roles in one figure. Mini visualisations (thumbnails, heatmaps) may be slightly more saturated but stay soft.

## 5. Typography

Root font stack (system fonts, no web fonts): `font-family="Inter, 'Helvetica Neue', Helvetica, Arial, 'Liberation Sans', sans-serif"`.
Math is real LaTeX: write it between `$…$` in a `<text>` and the render script typesets it in the paper's math font
(Computer Modern unless the paper loads another math package) with the paper's macros (svg-primitives.md §2). If Inter
is missing the figure falls back to Helvetica/Arial, which run about 5 % narrower, so a layout planned with Inter
widths stays safe.

| Tier | Class | Size | Printed (2u/pt) | Weight | Colour | Use |
|---|---|---|---|---|---|---|
| T1 | `.t-stage` | 17u | 8.5pt | 600 | `#1F2933` | stage titles `(a) …` |
| T2 | `.t-mod` | 15u | 7.5pt | 600 | `#1F2933` | module names |
| T3 | `.t-sub`, `.t-dim` | 13u | 6.5pt | 400 | `#4B5563` / `#6B7280` | sub-labels, tensor shapes, edge labels, legend |
| floor | — | 12.5u | 6.2pt | 400 | `#6B7280` | tiny tags (`×N`) only |
| scripts | (LaTeX) | — | ≥ 5pt | — | as the line | sub/superscripts inside `$…$`: LaTeX's script size for the base (6pt → 5pt, 8pt → 6pt), never set by hand |

- At most 4 sizes per figure (3 is typical). Captions print at ~9pt, so figure text stays at or below that. On an 800u NeurIPS canvas 1u = 0.495pt, so 12u would print at 5.9pt; hence the 12.5u floor.
- **Module names** are nouns in Title Case, ≤ 2 lines, ~14 characters per line (`Vision Encoder`, `Cross-Attn`). Use exactly the paper's names.
- **Tensor shapes** take the form `(B, C, H, W)`, with comma + space; use `×` (U+00D7) for products such as `H/16×W/16`. Show them at stage boundaries and wherever the shape changes, not on every edge.
- **Symbols** follow the paper's notation exactly, as LaTeX in `$…$`: `$x$`, `$\hat{y}$`, `$\mathcal{L}_{\text{task}}$`, `$c_{FA}$`. Render with `--paper main.tex` so the paper's macros and math font are used. Math in a line counts toward the size of that line's tier, not as an extra tier.
- **Emphasis inside the figure.** Set the proposed method's name in bold (`class="t-mod t-ours"`, weight 700) where it
  names the method's box, panel or column, once per figure. This is a figure-only device that gives the eye its
  target; it does not change how the paper's text styles the name.
- **Notation contract with the paper.**
  - Every symbol in the figure is defined in the caption or in text before the figure.
  - One name per entity: a module is not "encoder" in the figure and "backbone" in the caption.
  - Same notation as the body, including upright vs italic subscripts (`c_{\text{FA}}` vs `c_{FA}`). Copy it from the
    paper instead of retyping it.
- **Glyph coverage.** A character the figure font lacks (Inter has no `∗` U+2217, `⊙` or `∇`) is drawn in a fallback
  font with a different design; the lint reports `glyph-fallback`. Write such symbols as `$…$` math, or give that
  `<tspan>` a font that has them.
- Line height is 1.25 × size. Avoid all-caps, underline and italics for emphasis.

## 6. Shapes & ML conventions

Readers of ML papers recognise components by shape before they read labels. Draw each **model component** with its
conventional shape: a pretrained model, a head or a feature vector shown as a plain text box reads as a placeholder,
and the lint flags it (`plain-component`). Keep plain rounded rectangles for generic operations that have no
convention (fusion, pooling, sampling), and use an operator symbol when the step is one. Beyond that, 1–3 metaphors
per figure is the sweet spot.

| Component | Conventional shape (template in svg-primitives.md) |
|---|---|
| generic operation (fusion, pooling, sampling) | rounded rect, `rx` 6–8 |
| pretrained / frozen large model (VLM, LLM, vision encoder) | layer stack: block of 3–5 slabs crossing the flow (§5.6), or an encoder trapezoid, + frozen badge |
| encoder (compresses) | trapezoid, wide side toward the input |
| decoder / upsampler / generator | inverted trapezoid, wide side toward the output |
| small trainable head (linear, logistic, MLP, classifier, probe) | small trapezoid narrowing to its output, with its function inside: sigmoid glyph, `$\sigma$`, `$\mathrm{softmax}$` (§5.8) |
| feature / embedding vector | bar split into 6–8 cells, optionally shaded like values (§5.7) |
| input views / augmentations | 2×2 grid of small thumbnails showing each transform (flip, colour, mask); 1–2 word label |
| feature map / latent tensor | isometric cuboid, or a 3-card stack |
| multi-head, ensemble, ×N layers | 3-card stack + `×N` tag |
| token sequence / embeddings | row of small rounded squares |
| image in / out, ViT patchify | image thumbnail / thumbnail + patch grid |
| noise, sampling ε, diffusion step | Gaussian noise patch |
| attention / affinity / similarity | attention-matrix thumbnail |
| uncertainty, saliency, confidence map | heatmap thumbnail; distribution → bell glyph |
| segmentation / dense prediction | segmentation-map thumbnail |
| add / multiply / concatenate | vector operator circles ⊕ ⊗ ∥ (never Unicode glyphs) |
| loss / objective | pill (`rx` = h/2) in the `loss` palette, label `ℒ_name` |
| text prompt | `data` chip with the prompt in quotes |

## 7. Connectors

- **Routing.** Rounded orthogonal paths with corner radius 6–8u. Prefer straight segments. Use diagonals only inside a tight fan-in/fan-out cluster.
- **Ports.** Attach at side midpoints. Several edges on one side spread evenly (⅓, ⅔). Leave the source and enter the target perpendicular to the border.
- **Arrowheads.** One per edge, at the target, using the standard markers (tip overshoots the path end by 2u). The last straight run before a head is ≥ 12u.

| Flow | Style | Width | Colour |
|---|---|---|---|
| forward data | solid + arrowhead | 1.6u | ink of the source role |
| loss / supervision | dashed `5 3.5` + arrowhead | 1.4u | `loss` ink |
| gradient / feedback (optional) | dotted `2 2.5` + arrowhead | 1.2u | `loss` ink |
| skip / residual | solid, routed above the spine | 1.2u | source ink |
| conditioning / auxiliary / inference-only | dashed `5 3.5` | 1.4u | `aux` ink |

- **Crossings.** Avoid them by reordering modules first. If one is unavoidable, cross at 90°, away from corners. Never let two edges share a segment unless it is a deliberate fan-out from one port.
- **Edge labels.** T3, centred 6u above a horizontal segment or 6u right of a vertical one. A label never sits on the line, except with a white halo marked `class="on-edge"`.
- **Feedback paths** (loss → earlier module) run outside the main flow, through the gap below the cards.

## 8. Badges, legend, annotations

- **Frozen / trainable badges.** A vector icon in a white circle (r = 7.5u) straddling the top-right corner of the module (centre = corner + (−2, +2)). Add them only when the frozen vs trained split matters to the story, and then badge every relevant module, not some.
- **Legend.** Include it only for encodings a reader cannot guess: line styles, badges, the accent swatch. Put it in one row along the bottom (or in a genuinely empty corner) in T3 text, with ≥ 20u between items. Order: line styles, badges, swatches.
- **Callouts / zoom-ins.** `highlight` palette, 1u dashed frame, and a thin connector to the enlarged panel.
- **Step numbers.** Small circles with T3 digits. Do not use Unicode enclosed numerals (①), which depend on the font.

## 9. Information density

- Budget for a full-width Figure 1: ≤ ~12 modules, ≤ ~15 edges, ≤ ~40 text items. Anything beyond belongs in a later figure or an inset.
- **Labels are names, not sentences**: ≤ 3 words and ≤ 2 lines per box. The lint warns when one box holds more than 8
  words or 3 lines (`verbose-label`).
- **Show, don't describe.** Input and preprocessing blocks are where sentences creep in ("resize to 224×224, normalise
  and split into 16×16 patches"). Draw the result instead (patch grid, views grid) with a 1–2 word label, and put the
  description in the caption.
- Every symbol and shape must come from the paper or code. If you had to assume something, say so in the report.

## 10. Adapting the defaults

- **Prior work vs ours:** two panels at identical scale and layout; grey out the prior method and put the accent only on what changed.
- **Training vs inference:** separate panels (a)/(b), or a dashed `aux` region labelled "training only".
- **Column-width figure:** top → bottom flow, viewBox ≈ 470 wide, and fewer elements rather than smaller text.
- **Existing house style:** if the user shares earlier figures or a palette, match them and keep the role semantics.
- **Very dense method:** show the overview in Figure 1 and move the internals of the proposed module to a zoom-in panel or Figure 2.

## 11. Anti-patterns

- Rainbow or saturated palettes; gradients, glows, drop shadows (filters also rasterise in PDFs).
- Labels touching box borders; more than 4 font sizes; text smaller than 6pt printed.
- Arrows through modules, diagonal spaghetti, arrowheads floating short of or piercing their target.
- Emoji or Unicode pictographs as icons, which render as bitmaps or tofu in camera-ready PDFs.
- Sentences inside the figure; every module a different colour; boxes misaligned by 1–3u.
- Model components as text boxes: an "LLM" or "Linear Head" rectangle instead of a layer stack or a small head shape.
- Raster screenshots pasted into a vector schematic. Use vector thumbnails; if real images are essential, use small, clean crops.
