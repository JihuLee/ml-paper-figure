# Blueprint: figure1_uam (Phase 1)

Extracted from `methods.md`:
- **Stages**: (a) frozen encoding, (b) the proposed Uncertainty-Aware Module, (c) decoding + objectives.
- **Contribution**: UAM (Gaussian head, sampling, uncertainty map, gate) → `proposed` palette.
- **Frozen**: ViT-B/16 encoder E. **Trainable**: Gaussian head, decoder D. Sampling, U-map and the gate have no parameters, so they get no badge.
- **Tensors**: x 3×H×W → F N×D → z, U → F̃ → ŷ K×H×W (batch dim omitted for compactness).
- **Flows**: forward solid; ℒ_task(ŷ) and ℒ_KL(μ, σ) dashed in loss ink.

```yaml
figure: figure1_uam
target: neurips               # 5.5in = 396pt; viewBox 800 x 290 (2u = 1pt)
flow: left-to-right, spine y = 140
stages:
  - id: a
    title: "(a) Frozen Encoder"                    # 156.5u wide at 17u, card inner 158u
    box: [12, 12, 186, 240]
    modules:
      - {id: img, kind: thumb-patches, box: [28, 120, 40, 40], label: "x", dims: "3×H×W"}
      - {id: enc, kind: trapezoid-encoder, role: frozen, badge: frozen, box: [96, 90, 88, 100], inset: 18,
         label: "Vision|Encoder", sub: "ViT-B/16"}
  - id: b
    title: "(b) Uncertainty-Aware Module (UAM)"    # 308u, card inner 344u
    box: [212, 12, 372, 240]
    modules:
      - {id: feat, kind: stack, role: data, box: [236, 112, 34, 48], label: "F", dims: "N×D"}
      - {id: head, kind: rect, role: proposed, badge: train, box: [298, 114, 84, 52], label: "Gaussian|Head"}
      - {id: sample, kind: rect+thumb-noise, role: proposed, box: [412, 78, 104, 44], label: "Sample", caption: "z = μ + σ ⊙ ε"}
      - {id: umap, kind: rect+thumb-heat, role: proposed, box: [412, 158, 104, 44], label: "U-Map", caption: "U = ‖σ‖"}
      - {id: gate, kind: op-mul, centre: [540, 140]}
  - id: c
    title: "(c) Decoder & Loss"                    # 155u, card inner 162u
    box: [598, 12, 190, 240]
    modules:
      - {id: dec, kind: trapezoid-decoder, role: train, badge: train, box: [612, 90, 76, 100], inset: 18, label: "Decoder"}
      - {id: yhat, kind: thumb-seg, box: [716, 120, 40, 40]}
      - {id: lkl, kind: loss-pill, box: [614, 214, 60, 24], label: "ℒ_KL"}
      - {id: ltask, kind: loss-pill, box: [706, 214, 60, 24], label: "ℒ_task"}
edges:
  - {from: img.right, to: enc.left, style: forward, ink: data}
  - {from: enc.right, to: feat.left, style: forward, ink: frozen}
  - {from: feat.right, to: head.left, style: forward, ink: data}
  - {from: head.right, to: [sample.left, umap.left], style: forward, ink: proposed, fork_x: 390}
  - {from: sample.right, to: gate.top, style: forward, ink: proposed}
  - {from: umap.right, to: gate.bottom, style: forward, ink: proposed}
  - {from: gate.right, to: dec.left, style: forward, ink: proposed, label: "F̃"}
  - {from: dec.right, to: yhat.left, style: forward, ink: train, label: "ŷ"}
  - {from: yhat.bottom, to: ltask.top, style: loss}
  - {from: head.bottom, to: lkl.left, style: loss, route: "down to y=226, then right below everything"}
legend: [forward, loss, frozen, trainable, proposed]   # one row, centred, y = 270
checks:
  - card gaps 14u, canvas margin 12u, card padding >= 14u
  - arrow gaps >= 26u (img→enc, F→head, dec→ŷ), fork at x=390 leaves a 12u final run
  - label padding (svg_geom label): Vision|Encoder 13.8u, Gaussian|Head 8.4u, Sample 8u, Decoder 7u (narrow side)
```
