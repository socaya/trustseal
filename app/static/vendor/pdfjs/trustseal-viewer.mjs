// TrustSeal embedded PDF viewer.
//
// A minimal reviewer-focused viewer built on top of the vendored
// PDF.js library. Renders every page of a document into a stack of
// `<canvas>` elements inside a host container. The viewer is not
// trying to replace Mozilla's full web/viewer.mjs — it deliberately
// omits annotations, form fill, text selection, and find, so the
// signer's attention stays on the document content.
//
// Usage from a Jinja template (see ``templates/envelopes/sign/review.html``):
//
//   import { mountViewer } from "/static/vendor/pdfjs/trustseal-viewer.mjs";
//   mountViewer({
//     url: "/sign/<token>/download",
//     container: document.getElementById("pdf-host"),
//     statusLabel: document.getElementById("pdf-status"),
//     page: document.getElementById("pdf-page"),
//     zoomInc: document.getElementById("zoom-in"),
//     zoomDec: document.getElementById("zoom-out"),
//   });
//
// Security notes:
//   * The worker is loaded from the same origin (no CDN).
//   * The caller supplies a URL under their own domain; the viewer
//     does not accept cross-origin URLs by default.
//   * Rendering failures surface in the status label, never silently.

import * as pdfjs from "./pdf.mjs";

pdfjs.GlobalWorkerOptions.workerSrc = "/static/vendor/pdfjs/pdf.worker.mjs";

const DEFAULT_SCALE = 1.25;
const MIN_SCALE = 0.5;
const MAX_SCALE = 2.5;

export async function mountViewer(options) {
  const {
    url,
    container,
    statusLabel = null,
    page = null,
    zoomInc = null,
    zoomDec = null,
  } = options || {};
  if (!url || !container) {
    throw new Error("mountViewer requires url and container");
  }

  const state = { scale: DEFAULT_SCALE, doc: null, canvases: [] };

  const setStatus = (text) => {
    if (statusLabel) statusLabel.textContent = text;
  };

  setStatus("Loading document...");
  try {
    state.doc = await pdfjs.getDocument({
      url,
      withCredentials: true,
    }).promise;
  } catch (err) {
    setStatus("Could not load the document. Try the download link.");
    throw err;
  }

  if (page) {
    page.textContent = `1 / ${state.doc.numPages}`;
  }

  // Build an empty canvas per page so the layout is stable before
  // high-resolution rendering completes.
  container.innerHTML = "";
  for (let i = 1; i <= state.doc.numPages; i += 1) {
    const canvas = document.createElement("canvas");
    canvas.dataset.page = String(i);
    canvas.style.display = "block";
    canvas.style.margin = "0 auto 12px";
    canvas.style.background = "#FFFFFF";
    canvas.style.border = "1px solid #D6DADE";
    canvas.setAttribute("aria-label", `PDF page ${i}`);
    container.appendChild(canvas);
    state.canvases.push(canvas);
  }

  const renderAll = async () => {
    setStatus("Rendering...");
    for (let i = 1; i <= state.doc.numPages; i += 1) {
      const pdfPage = await state.doc.getPage(i);
      const viewport = pdfPage.getViewport({ scale: state.scale });
      const canvas = state.canvases[i - 1];
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.floor(viewport.width * ratio);
      canvas.height = Math.floor(viewport.height * ratio);
      canvas.style.width = `${Math.floor(viewport.width)}px`;
      canvas.style.height = `${Math.floor(viewport.height)}px`;
      const ctx = canvas.getContext("2d");
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      await pdfPage.render({ canvasContext: ctx, viewport }).promise;
    }
    setStatus(`Loaded ${state.doc.numPages} page(s)`);
  };

  await renderAll();

  // Track the top-most visible page so a page indicator can reflect
  // the signer's position within the scroll.
  const updatePageIndicator = () => {
    if (!page) return;
    const scrollTop = container.scrollTop;
    let visible = 1;
    for (const canvas of state.canvases) {
      if (canvas.offsetTop - 12 <= scrollTop + 1) {
        visible = Number(canvas.dataset.page);
      } else {
        break;
      }
    }
    page.textContent = `${visible} / ${state.doc.numPages}`;
  };
  container.addEventListener("scroll", updatePageIndicator, { passive: true });
  updatePageIndicator();

  const applyZoom = async (next) => {
    const clamped = Math.min(MAX_SCALE, Math.max(MIN_SCALE, next));
    if (clamped === state.scale) return;
    state.scale = clamped;
    await renderAll();
    updatePageIndicator();
  };

  if (zoomInc) {
    zoomInc.addEventListener("click", () => {
      void applyZoom(state.scale + 0.1);
    });
  }
  if (zoomDec) {
    zoomDec.addEventListener("click", () => {
      void applyZoom(state.scale - 0.1);
    });
  }

  return {
    getState() {
      return { scale: state.scale, pages: state.doc?.numPages ?? 0 };
    },
    async setScale(next) {
      await applyZoom(next);
    },
  };
}
