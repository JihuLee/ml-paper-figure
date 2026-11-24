# Verification run: `ml-paper-figure` applied to a hypothetical UAM paper

> This record predates LaTeX math typesetting and the component-shape lint. The maintained example is
> `skills/ml-paper-figure/assets/example-figure1.svg`.

The input is `methods.md` (frozen ViT encoder → proposed Uncertainty-Aware Module → decoder, with dashed loss paths).
The target is NeurIPS `\textwidth` (5.5in = 396pt), on an 800 × 290u canvas.

| Phase | Output |
|---|---|
| 1 Plan | `figure1_uam.blueprint.md`: 3 stages, 9 modules, 10 edges; label widths checked with `svg_geom.py label`/`width` before drawing |
| 2 Draft | `round1/figure1_uam.svg`: core `<defs>` + 6 optional defs from `svg-primitives.md`; every path computed with `svg_geom.py` |
| 3 Critique | 3 rounds (below) |
| 4 Export | `figure1_uam.svg`, `figure1_uam.pdf` (vector, 5.50 × 2.00in, 1 page, text outlined, 0 raster images, PNG/PDF diff 1.3 %), `figure1_uam.png` (2400 × 870) |

## Round 1: 1 error, 6 warnings

| Tag | Finding | Fix |
|---|---|---|
| E1 `duplicate-id` | `thumb-image` defined twice. The defs were assembled with a lazy regex that swallowed the next group. A real bug. | delete the second copy |
| W1, W2 `font-small` | loss subscripts at 12u = 5.9pt (an 800u canvas gives 0.495pt/u) | use the 13u T3 tier, which also drops the figure from 4 font sizes to 3 |
| W3–W6 `near-misaligned` | edge labels F̃/ŷ (baseline 134) compared with module labels (135.9) | false positive: unrelated rows. **Lint refined**: baselines are now compared only between texts whose containers have similar size |
| visual | composition OK: spine y = 140 shared by all 6 main-path elements, accent clearly on UAM, no crossings, every arrowhead lands on a border | — |

## Round 2: 0 errors, 1 warning

| Tag | Finding | Fix |
|---|---|---|
| W1 `tight-padding` | the 13u subscript pushes "ℒtask" to 2.5u above the pill bottom; visible in the PNG too (both loss labels sit low) | lift both loss labels from baseline 231 to 229.5 (cy + 3.5, see the svg-primitives §2 rule) |

## Round 3: 0 errors, 0 warnings

Checklist: text fit ✓ · arrows ✓ · spacing & alignment ✓ · print legibility ✓ (min 6.4pt at 5.5in; 8.0pt at CVPR width) ·
hierarchy ✓ (UAM is the only warm element) · semantics ✓ (frozen badge on E only; trainable on Gaussian head + decoder;
both loss paths dashed; legend matches).

## Things the run fed back into the skill

- `render_svg.py`: Chromium PDFs embed Inter (`.otf`, CFF) as **Type 3** fonts. Export now detects this and outlines the text (`pdftocairo -svg` → Chromium print), so the PDF has no fonts at all. PDF backend preference is rsvg > inkscape > chromium > cairosvg.
- `render_svg.py`: baseline-alignment check limited to comparable containers (removed the round-1 false positives).
- `design-system.md` / `svg-primitives.md`: sub/superscripts use the 13u T3 tier; the floor is 12.5u; the baseline rule for subscripted labels in pills is `cy + 3.5`.
- `svg_geom.py`: no zero-length `L` when a bend consumes the whole first segment; `label --cls` no longer duplicates font attributes.
