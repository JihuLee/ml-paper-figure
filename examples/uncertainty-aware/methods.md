# Input: hypothetical Methods excerpt (verification prompt)

> *Make Figure 1 for our NeurIPS submission: frozen vision encoder → our Uncertainty-Aware Module → decoder, with the losses as dashed paths.*

**3 Method.** Given an image $x \in \mathbb{R}^{3\times H\times W}$, a frozen ViT-B/16 encoder $E$ produces patch
tokens $F = E(x) \in \mathbb{R}^{N\times D}$. Our **Uncertainty-Aware Module (UAM)** has a lightweight Gaussian head
that predicts a per-token mean $\mu$ and scale $\sigma$. We draw stochastic features with the reparameterisation
$z = \mu + \sigma \odot \epsilon$, $\epsilon \sim \mathcal{N}(0, I)$. The uncertainty map $U = \lVert\sigma\rVert$
gates them: $\tilde F = (1 - U) \odot z$. A trainable decoder $D$ upsamples $\tilde F$ to the segmentation
$\hat y \in \mathbb{R}^{K\times H\times W}$.

**Training.** $\mathcal{L} = \mathcal{L}_{task}(\hat y, y) + \lambda\,\mathcal{L}_{KL}$, where
$\mathcal{L}_{KL} = \mathrm{KL}(\mathcal{N}(\mu, \sigma^2)\,\|\,\mathcal{N}(0, I))$. Only the UAM and $D$ are trained; $E$ stays frozen.
