"""Public, unauthenticated stamp-receipt verification.

Anyone who holds a receipt id + nonce can confirm a stamp impression's
authenticity without logging in. This gives third-party readers (a
counterparty, an auditor, a journalist) a way to independently prove
that a TrustSeal stamp mark was genuinely issued by the tenant.

The URL carries both the receipt id and the nonce so the request is
self-authorising, similar to a share-link pattern. Signature
verification still happens server-side with a tenant-scoped HMAC key
derived from the DEK, so revealing the URL does not help an attacker
forge new receipts.

Public response intentionally omits tenant internals (user ids,
document ids) — only the stamp name/kind, placed_at, and validity are
returned. Anyone already holding the TSD being verified naturally
knows the context around those marks.
"""
from __future__ import annotations

from io import BytesIO

import segno
from flask import Blueprint, Response, abort, jsonify, render_template_string, request

from app.extensions import db
from app.models.tsd_stamp import TSDStamp
from app.models.tsd_stamp_insertion import TSDStampInsertion
from app.services.rate_limiting import RateLimitError, consume
from app.services.tsd_stamp_receipts import verify_receipt


stamp_verify_public = Blueprint(
    "stamp_verify_public", __name__, url_prefix="/verify/stamp"
)


_HTML_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Stamp verification · TRUSTSEAL</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body { font-family: -apple-system, Segoe UI, Helvetica, sans-serif;
         background: #f6f8fa; color: #121a26; margin: 0;
         min-height: 100vh; display: flex; align-items: center; justify-content: center; }
  .card { max-width: 480px; width: 100%; background: #fff;
          border-radius: 10px; padding: 32px;
          box-shadow: 0 6px 28px rgba(18,26,38,.10); margin: 20px; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  .sub { color: #5a6676; font-size: 13px; margin: 0 0 20px; }
  .badge { display: inline-flex; align-items: center; gap: 8px;
           padding: 8px 14px; border-radius: 99px;
           font-size: 13px; font-weight: 700; margin-bottom: 20px; }
  .badge--ok   { background: #e8f5ef; color: #0e664d; }
  .badge--warn { background: #fff5e2; color: #835a0c; }
  .badge--bad  { background: #fbe9ea; color: #9e2f36; }
  .k { color: #5a6676; font-size: 11px; text-transform: uppercase;
       letter-spacing: 0.08em; }
  .v { color: #121a26; font-size: 14px; font-weight: 600; }
  .row { display: grid; grid-template-columns: 140px 1fr;
         padding: 8px 0; border-bottom: 1px solid #e2e7ed; }
  .row:last-child { border-bottom: 0; }
  .brand { font-size: 11px; color: #5a6676; margin-top: 24px; text-align: center; }
  .brand strong { color: #3778d4; }
</style>
</head>
<body>
  <div class="card">
    <h1>TRUSTSEAL stamp verification</h1>
    <p class="sub">Independent validation of a stamp impression by its signed receipt.</p>

    {% if result.valid %}
      {% if result.revoked %}
        <div class="badge badge--warn">⚠ Receipt revoked</div>
      {% elif result.context_intact is false %}
        <div class="badge badge--warn">⚠ Signature valid · mark edited after insertion</div>
      {% else %}
        <div class="badge badge--ok">✓ Authentic stamp impression</div>
      {% endif %}
      <div class="row"><span class="k">Stamp</span><span class="v">{{ result.stamp_name }}</span></div>
      <div class="row"><span class="k">Kind</span><span class="v">{{ result.stamp_kind|upper }}</span></div>
      <div class="row"><span class="k">Placed at</span><span class="v">{{ result.placed_at }}</span></div>
      {% if result.context_label %}
      <div class="row"><span class="k">Context</span><span class="v">{{ result.context_label }}</span></div>
      {% endif %}
      <div class="row"><span class="k">Receipt</span><span class="v">#{{ result.receipt_id }}</span></div>
      {% if result.revoked_reason %}
      <div class="row"><span class="k">Revoked reason</span><span class="v">{{ result.revoked_reason }}</span></div>
      {% endif %}
    {% else %}
      <div class="badge badge--bad">✗ Verification failed</div>
      <div class="row"><span class="k">Reason</span><span class="v">{{ result.reason }}</span></div>
    {% endif %}

    <div class="brand">Issued by <strong>TRUSTSEAL</strong> · signatures validate against the issuing tenant key.</div>
  </div>
</body>
</html>
"""


def _lookup_org(receipt_id: int) -> int | None:
    row = db.session.get(TSDStampInsertion, int(receipt_id))
    return row.organization_id if row else None


def _rate_limited(bucket: str, max_hits: int = 60,
                  window_seconds: int = 60) -> bool:
    """Return True when the caller has exceeded the window budget."""
    ident = (request.headers.get("X-Forwarded-For")
             or request.remote_addr or "anon").split(",")[0].strip()
    try:
        decision = consume(
            bucket_key=f"{bucket}:{ident}",
            max_hits=max_hits,
            window_seconds=window_seconds,
        )
    except RateLimitError:
        return False
    return not decision.allowed


@stamp_verify_public.route("/<int:receipt_id>/<string:nonce>", methods=["GET"])
def verify_public(receipt_id: int, nonce: str):
    """HTML or JSON verification depending on Accept header."""
    if _rate_limited("stamp_verify", max_hits=60, window_seconds=60):
        abort(429)
    org_id = _lookup_org(receipt_id)
    if org_id is None:
        if _wants_json():
            return jsonify({"valid": False, "reason": "receipt_not_found"}), 404
        abort(404)

    result = verify_receipt(
        organization_id=org_id,
        receipt_id=receipt_id,
        nonce=nonce,
    )

    # Scrub internal fields before leaving the server.
    public = {
        "valid": result.get("valid", False),
        "reason": result.get("reason"),
        "stamp_id": result.get("stamp_id"),
        "stamp_name": result.get("stamp_name"),
        "stamp_kind": result.get("stamp_kind"),
        "placed_at": result.get("placed_at"),
        "context_label": result.get("context_label"),
        "context_intact": result.get("context_intact"),
        "revoked": result.get("revoked", False),
        "revoked_reason": result.get("revoked_reason"),
        "receipt_id": receipt_id,
    }
    if _wants_json():
        return jsonify(public), (200 if public["valid"] else 400)
    return render_template_string(_HTML_TEMPLATE, result=public)


@stamp_verify_public.route("/qr/<int:receipt_id>/<string:nonce>.svg",
                           methods=["GET"])
def qr_svg(receipt_id: int, nonce: str):
    """Serve an SVG QR encoding the public verify URL for this receipt.

    Scanning the QR with any phone camera opens the public verify page.
    Use ``?size=120`` to request a specific width (default 120 px).
    """
    if _rate_limited("stamp_verify_qr", max_hits=30, window_seconds=60):
        abort(429)
    org_id = _lookup_org(receipt_id)
    if org_id is None:
        abort(404)
    # Prove the nonce matches before issuing a QR — prevents enumeration.
    quick = verify_receipt(
        organization_id=org_id, receipt_id=receipt_id, nonce=nonce,
    )
    if not quick.get("valid") and quick.get("reason") not in ("revoked",):
        abort(404)

    url = request.host_url.rstrip("/") + f"/verify/stamp/{receipt_id}/{nonce}"
    size_px = max(40, min(800, int(request.args.get("size", 120))))
    qr = segno.make(url, error="m")
    buf = BytesIO()
    qr.save(buf, kind="svg", scale=4, border=1, svgclass="ts-qr",
            lineclass=None, omitsize=True, xmldecl=False)
    svg = buf.getvalue().decode("utf-8")
    # Force an outer width so the QR renders at the requested size.
    svg = svg.replace(
        "<svg ", f'<svg width="{size_px}" height="{size_px}" ', 1
    )
    resp = Response(svg, mimetype="image/svg+xml")
    resp.cache_control.public = True
    resp.cache_control.max_age = 3600
    return resp


def _wants_json() -> bool:
    accept = request.headers.get("Accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return True
    return request.args.get("format") == "json"
