"""Live-browser WCAG 2.1 AA accessibility suite powered by Playwright + Chromium.

Closes Gap G5 from ``docs/REMAINING_GAPS_2026-11-15.md`` by booting the real
Flask application on an ephemeral localhost port and auditing rendered DOM,
computed visibility, ARIA naming, landmarks, keyboard focusability, and
uncaught runtime errors across every compliance-critical UI surface:

* Public verification (``/verify``)
* Signer landing + review (``/sign/<token>``)
* Evidence retention browser (``/evidence/retentions``)
* Stamp library / custody dashboard (``/stamps/library``)
* Sealed signatures vault (``/signatures``)

When ``axe.min.js`` is available (via ``TRUSTSEAL_AXE_JS`` or
``app/static/vendor/axe/axe.min.js``), the suite also executes ``axe.run()``
against WCAG 2.1 Level A & AA rules and fails on any critical or serious
violation.
"""
from __future__ import annotations

import hashlib
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from werkzeug.serving import make_server

playwright = pytest.importorskip("playwright.sync_api")


_DOM_A11Y_AUDIT_JS = r"""
() => {
  const issues = [];

  const isVisible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
      return false;
    }
    if (el.hasAttribute('hidden') || el.getAttribute('aria-hidden') === 'true') {
      return false;
    }
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };

  const hasLabelledBy = (el) => {
    const ids = (el.getAttribute('aria-labelledby') || '').trim().split(/\s+/).filter(Boolean);
    return ids.some((id) => {
      const target = document.getElementById(id);
      return target && (target.textContent || '').trim().length > 0;
    });
  };

  // 1. Document language & title
  const lang = (document.documentElement.getAttribute('lang') || '').trim();
  if (!lang) issues.push({ rule: 'html-lang', detail: '<html> missing lang attribute' });
  if (!(document.title || '').trim()) issues.push({ rule: 'document-title', detail: 'Missing <title>' });

  // 2. Main landmark & primary heading
  const main = document.querySelector('main, [role="main"]');
  if (!main) issues.push({ rule: 'landmark-main', detail: 'Missing <main> landmark' });
  const h1s = Array.from(document.querySelectorAll('h1')).filter(isVisible);
  if (h1s.length === 0) issues.push({ rule: 'page-has-h1', detail: 'No visible <h1> heading' });

  // 3. Visible form controls must have an accessible label
  const controls = document.querySelectorAll('input, select, textarea');
  for (const el of controls) {
    if (!isVisible(el)) continue;
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (['hidden', 'submit', 'button', 'reset', 'image'].includes(type)) continue;
    const id = el.getAttribute('id');
    const hasForLabel = id ? Boolean(document.querySelector(`label[for="${CSS.escape(id)}"]`)) : false;
    const inLabel = Boolean(el.closest('label'));
    const hasAria = Boolean((el.getAttribute('aria-label') || '').trim()) || hasLabelledBy(el);
    if (!hasForLabel && !inLabel && !hasAria) {
      issues.push({
        rule: 'form-control-label',
        detail: `<${el.tagName.toLowerCase()} id="${id || ''}" name="${el.getAttribute('name') || ''}"> missing accessible label`,
      });
    }
  }

  // 4. Visible buttons & links must have an accessible name
  const interactives = document.querySelectorAll('button, a[href]');
  for (const el of interactives) {
    if (!isVisible(el)) continue;
    const text = (el.innerText || el.textContent || '').trim();
    const aria = (el.getAttribute('aria-label') || '').trim();
    const title = (el.getAttribute('title') || '').trim();
    const imgAlt = Array.from(el.querySelectorAll('img[alt]')).some((i) => (i.getAttribute('alt') || '').trim().length > 0);
    if (!text && !aria && !title && !hasLabelledBy(el) && !imgAlt) {
      issues.push({
        rule: 'interactive-name',
        detail: `<${el.tagName.toLowerCase()} class="${el.className || ''}"> has no accessible name`,
      });
    }
  }

  // 5. Visible images must carry an alt attribute (empty alt="" allowed for decorative)
  for (const img of document.querySelectorAll('img')) {
    if (!isVisible(img)) continue;
    if (!img.hasAttribute('alt')) {
      issues.push({ rule: 'img-alt', detail: `<img src="${(img.getAttribute('src') || '').slice(0, 40)}"> missing alt` });
    }
  }

  return issues;
}
"""


def _find_axe_script() -> Path | None:
    env_path = os.environ.get("TRUSTSEAL_AXE_JS")
    if env_path and Path(env_path).is_file():
        return Path(env_path)
    vendored = Path(__file__).resolve().parent.parent / "app" / "static" / "vendor" / "axe" / "axe.min.js"
    return vendored if vendored.is_file() else None


def _run_page_a11y_audit(page, url: str) -> list[dict]:
    page_errors: list[str] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    resp = page.goto(url, wait_until="domcontentloaded", timeout=15000)
    assert resp is not None, f"No response for {url}"
    assert resp.status == 200, f"Expected 200 for {url}, got {resp.status}"
    assert not page_errors, f"Uncaught JS errors on {url}: {page_errors}"

    issues = page.evaluate(_DOM_A11Y_AUDIT_JS)

    # Verify keyboard navigation focuses an element
    page.keyboard.press("Tab")
    active_tag = page.evaluate("() => document.activeElement ? document.activeElement.tagName : ''")
    assert active_tag, f"Keyboard Tab did not focus any element on {url}"

    # Optional axe-core pass when vendored
    axe_path = _find_axe_script()
    if axe_path is not None:
        page.add_script_tag(path=str(axe_path))
        axe_violations = page.evaluate(
            """async () => {
              const res = await window.axe.run(document, {
                runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] }
              });
              return res.violations
                .filter(v => v.impact === 'critical' || v.impact === 'serious')
                .map(v => ({ rule: 'axe:' + v.id, detail: v.help + ' (' + v.nodes.length + ' nodes)' }));
            }"""
        )
        issues.extend(axe_violations)

    return issues


@pytest.fixture
def live_a11y_env(pg_app):
    """Boot a live Werkzeug server and seed an authenticated user + signing invitation."""
    from app.extensions import db
    from app.models.documents.document_blob import DocumentBlob
    from app.models.documents.document import Document
    from app.models.evidence_preservation import EvidenceRetention
    from app.models.organization import Organization
    from app.models.signing_envelope import EnvelopeParticipant, SigningEnvelope
    from app.models.user import User
    from app.services import signer_invitations

    pg_app.config["PUBLIC_PDF_VERIFICATION_ENABLED"] = True
    pg_app.config["PUBLIC_PDF_VERIFICATION_CERT_SHA256"] = "a" * 64

    org = Organization(name="Playwright A11y Org")
    db.session.add(org)
    db.session.flush()

    user = User(
        username="a11y-browser-user",
        email="a11y-browser@example.test",
        first_name="A11y",
        last_name="Tester",
        is_active=True,
        email_verified=True,
        organization_id=org.id,
    )
    user.set_password("A11yBrowserPass!123")
    db.session.add(user)
    db.session.flush()

    doc = Document(
        title="A11y Review Agreement",
        status="pending",
        created_by=user.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()

    digest = hashlib.sha256(b"a11y-browser-doc").hexdigest()
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"tenants/{org.id}/orig/a11y-doc",
        file_name="a11y-doc.pdf",
        mime_type="application/pdf",
        file_size=4,
        sha256=digest,
        scanner="noop",
        created_by_id=user.id,
    )
    db.session.add(blob)
    db.session.flush()

    env = SigningEnvelope(
        organization_id=org.id,
        document_id=doc.id,
        document_blob_id=blob.id,
        created_by_id=user.id,
        state="prepared",
        document_sha256=digest,
        prepared_at=datetime.utcnow(),
    )
    db.session.add(env)
    db.session.flush()

    participant = EnvelopeParticipant(
        envelope_id=env.id,
        user_id=user.id,
        role="signer",
        signing_order=1,
    )
    db.session.add(participant)
    db.session.flush()

    _inv, sign_token = signer_invitations.issue(
        envelope=env,
        participant=participant,
        issued_by_id=user.id,
    )

    retention = EvidenceRetention(
        organization_id=org.id,
        artifact_type="finalized_pdf",
        artifact_id=1,
        artifact_sha256=digest,
        retain_until=datetime.utcnow() + timedelta(days=365),
        created_by_id=user.id,
    )
    db.session.add(retention)
    db.session.commit()

    server = make_server("127.0.0.1", 0, pg_app)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    # Mint a signed Flask-Login session cookie for the Playwright browser context
    tc = pg_app.test_client()
    with tc.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    # Trigger a harmless request so the test client writes the signed session cookie
    tc.get("/verify")
    session_cookies = [
        {
            "name": name,
            "value": c.value,
            "domain": "127.0.0.1",
            "path": path or "/",
        }
        for (_dom, path, name), c in tc._cookies.items()
    ]

    try:
        yield {
            "base_url": f"http://127.0.0.1:{port}",
            "sign_token": sign_token,
            "session_cookies": session_cookies,
        }
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_playwright_browser_accessibility_all_core_surfaces(live_a11y_env):
    """Audit /verify, /sign/<token>, /evidence/retentions, /stamps/library, and /signatures in Chromium."""
    from playwright.sync_api import sync_playwright

    base = live_a11y_env["base_url"]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        try:
            # 1. Public verify
            verify_issues = _run_page_a11y_audit(page, f"{base}/verify")
            assert verify_issues == [], f"/verify a11y issues: {verify_issues}"

            # 2. Signer landing + review
            sign_issues = _run_page_a11y_audit(page, f"{base}/sign/{live_a11y_env['sign_token']}")
            assert sign_issues == [], f"/sign/<token> a11y issues: {sign_issues}"

            # Authenticate browser context with the signed Flask-Login session cookie
            context.add_cookies(live_a11y_env["session_cookies"])

            # 3. Evidence retentions
            ev_issues = _run_page_a11y_audit(page, f"{base}/evidence/retentions")
            assert ev_issues == [], f"/evidence/retentions a11y issues: {ev_issues}"

            # 4. Stamp library / custody dashboard
            stamps_issues = _run_page_a11y_audit(page, f"{base}/stamps")
            assert stamps_issues == [], f"/stamps a11y issues: {stamps_issues}"

            # 5. Sealed signatures vault
            sig_issues = _run_page_a11y_audit(page, f"{base}/signatures")
            assert sig_issues == [], f"/signatures a11y issues: {sig_issues}"
        finally:
            context.close()
            browser.close()
