# Vendored PDF.js

The files in this directory are a verbatim copy of selected build
outputs from Mozilla's PDF.js project, redistributed here to avoid
third-party CDN dependencies on the signer landing surface.

* `pdf.mjs`, `pdf.worker.mjs`, `pdf.renderer.mjs` — upstream build
  artifacts, licensed under Apache License 2.0. See `LICENSE` for the
  full text.
* `trustseal-viewer.mjs` — a small first-party embedded viewer
  written specifically for the `/sign/<token>` review flow. It is
  **not** part of the upstream PDF.js distribution.

**Version pinned:** PDF.js v6.5.438 (upstream release)
**Source:** <https://github.com/mozilla/pdf.js/releases/tag/v6.5.438>

## Updating

Replace the four upstream files above with matching artifacts from a
newer tagged release. Do not modify the upstream files locally;
instead, extend `trustseal-viewer.mjs` for first-party changes.
