// TrustSeal glue around signature_pad.
//
// Thin first-party initialisation of the vendored signature_pad UMD
// bundle. Keeps the review template free of inline JavaScript
// implementation details.

export function mountSignaturePad({ canvas, clearBtn, hiddenInput }) {
  if (!canvas) {
    return null;
  }
  const SignaturePad = window.SignaturePad;
  if (!SignaturePad) {
    throw new Error(
      "signature_pad.umd.min.js must be loaded before trustseal-signature.mjs"
    );
  }

  const resizeCanvas = () => {
    const ratio = Math.max(window.devicePixelRatio || 1, 1);
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.floor(rect.width * ratio);
    canvas.height = Math.floor(rect.height * ratio);
    const ctx = canvas.getContext("2d");
    ctx.scale(ratio, ratio);
  };

  resizeCanvas();
  const pad = new SignaturePad(canvas, {
    minWidth: 0.8,
    maxWidth: 2.4,
    penColor: "#164C83",
    backgroundColor: "rgba(255,255,255,0)",
  });

  const updateHidden = () => {
    if (!hiddenInput) return;
    if (pad.isEmpty()) {
      hiddenInput.value = "";
      return;
    }
    // Trim the canvas to a PNG and store its data URL in a hidden
    // field so the review form carries it on submit.
    hiddenInput.value = pad.toDataURL("image/png");
  };

  pad.addEventListener("endStroke", updateHidden);

  if (clearBtn) {
    clearBtn.addEventListener("click", (event) => {
      event.preventDefault();
      pad.clear();
      updateHidden();
    });
  }

  // Resize on viewport changes so the drawn surface stays crisp.
  window.addEventListener("resize", () => {
    const current = pad.toData();
    resizeCanvas();
    pad.clear();
    pad.fromData(current);
    updateHidden();
  });

  return {
    pad,
    isEmpty: () => pad.isEmpty(),
    clear: () => {
      pad.clear();
      updateHidden();
    },
  };
}
