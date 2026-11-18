# TSD real-time multi-cursor collab — architecture plan

**Status (2026-11-18):** Awareness channel shipped. Full co-editing
(conflict-free text merging) still requires CRDT engine integration —
see §Recommended path below.

## What ships today

* **Transport:** Flask-SocketIO 5.x with `async_mode='threading'` and
  `simple-websocket` as the WSGI-compatible WebSocket adapter. True
  WebSocket in dev with `flask run`; gunicorn + gevent/eventlet in
  production.
* **Namespace:** `/tsd`. Per-document rooms keyed as `tsd:<id>`.
* **Auth:** inherits the HTTP session (`flask_login.current_user`).
  Every `join` re-runs the same `_can_access` check as the HTTP
  endpoints (tenant membership or active share grant).
* **Protocol events:**
  - `hello` on connect — server tells client its own identity +
    stable color.
  - `join` `{tsd_id}` — join the document room; server emits
    `peer_joined` to everyone else and `whois` back to the room so
    existing peers reply with `whoami` → `peer_joined` pointed at
    the newcomer.
  - `cursor` `{tsd_id, position}` — position carries caret rect
    (top/left/width/height relative to the page element) and
    optional selection rects. Server broadcasts `peer_cursor` to
    the room except the sender.
  - `typing` `{tsd_id}` — transient typing indicator,
    broadcast as `peer_typing`.
  - `leave` + `disconnect` — broadcast `peer_left`.
* **UI:** editor renders colored vertical cursor lines with labeled
  name chips for every active peer. Selection rects render as
  semi-transparent highlights. A green "● live" badge in the title
  bar flips to "● offline" on disconnect. A "<name> typing" pill
  appears for 2.5 s next to the presence avatars.

Realistic test coverage ships in `tests/documents/test_tsd_realtime.py`
(colour stability, access check parity, outsider denial). The socket
round-trip itself is proven via a live smoke script (see §Smoke).

## What is still deferred

**Conflict-free co-editing.** Two users editing the same paragraph
simultaneously still need the Y.js / Automerge CRDT or an OT engine
— the awareness channel moves cursors, not text. Today the existing
`If-Match` optimistic-concurrency guard prevents silent clobbering;
the losing write gets `412 version_conflict` and the loser's version
is accessible from the append-only `ts_document_versions` snapshot.

## Why not shipped yet

A real-time multi-cursor editor (Google Docs-class) is not a UI feature
— it's a distributed-systems problem. Shipping it responsibly requires
architecture decisions that have not yet been taken:

1. **Concurrency model.** Operational Transformation (OT) vs. CRDT. CRDT
   via `Yjs` or `Automerge` is the modern choice and integrates with
   contentEditable through `y-prosemirror` / `y-quill`. OT (ShareJS-era)
   is simpler but harder to reason about when connectivity is flaky.
2. **Transport.** Flask is WSGI — not WebSocket-native. Options:
   - Flask-SocketIO + eventlet/gevent worker
   - A separate FastAPI/Starlette sidecar running `uvicorn` with
     `python-socketio` or raw `websockets`, sharing the Postgres DB
     with the Flask app
   - `y-websocket` reference server (Node) behind the same reverse proxy
3. **Persistence model.** The authoritative TSD is the encrypted
   ciphertext in `ts_documents`. A co-editing session needs a mutable
   in-memory document that periodically snapshots back to the TSD. That
   snapshot cadence, debouncing, and conflict with the existing
   `If-Match` autosave must be designed together.
4. **Encryption boundary.** The current TSD threat model has plaintext
   decrypted only inside the server process. Peer-to-peer CRDT updates
   would either:
   - Run through the server (server stays the trust boundary — simpler;
     server CPU cost scales with session count)
   - Peer-to-peer with end-to-end encryption using a derived session
     key (more complex; requires key-exchange protocol; incompatible
     with server-side comments/search)
5. **Presence protocol.** Y.js ships `y-awareness` for cursors,
   selections, user colors. The polling endpoints shipped today
   (`POST/GET /api/tsd/<id>/presence`) are the upgrade path — the UI
   already renders avatar pills that a WebSocket awareness stream can
   feed.

## What ships now

### Polling-based (first iteration)

- `TSDPresence` row per `(tsd_id, user_id)` with `last_ping_at`.
- `POST /api/tsd/<id>/presence` — pinged by the editor every 15 s.
- `GET /api/tsd/<id>/presence` — returns viewers active in the last 45 s.
- Avatar pills in the editor title bar refresh every 15 s.

### WebSocket awareness channel (this iteration)

- Flask-SocketIO on `/socket.io/` with the `/tsd` namespace.
- Live cursor + selection broadcast under per-document rooms.
- Session-cookie auth; same tenant / share check as the HTTP layer.
- Editor renders peers' colored cursors with name labels and
  semi-transparent selection highlights inside the paper page.

## Recommended path for a real implementation

1. **Decide transport first.** Deploy a `y-websocket` server (Node) as a
   sidecar; terminate WebSocket at the same reverse proxy as the Flask
   app; authenticate the WebSocket handshake with the existing session
   cookie (same-origin only) or a short-lived signed token.
2. **Wrap contentEditable with ProseMirror + y-prosemirror.** The
   editor's current `document.execCommand` surface is replaced with a
   ProseMirror schema derived from the TSD HTML subset.
3. **Snapshot cadence.** Every 10 s of inactivity (or on explicit save)
   serialize the CRDT state back into TSD HTML, sanitize, encrypt,
   write with `If-Match`.
4. **Reuse comments, shares, approvals, versions.** All four shipped
   this iteration are orthogonal to the editor engine and need no
   changes.
5. **Security.** Enforce RLS policy on the CRDT sync endpoint (same
   checks as `_owned()` / `_share_permission()`). Never relay CRDT
   updates to peers who no longer have permission.

## Effort estimate

- WebSocket sidecar + auth bridge: ~1 week
- ProseMirror / Y.js integration into editor: ~2 weeks
- CRDT snapshot-to-TSD autosave + conflict handling: ~1 week
- Security test suite + tenant isolation under co-editing: ~1 week

**Total:** ~5 engineering weeks. Not a single-session task.

## Interim mitigation

The current `If-Match` concurrency guard + version-history snapshots
mean two editors cannot silently clobber each other: whoever saves
second gets `412 version_conflict` and can see the other version in
history. This is not multi-cursor editing, but it IS safe sequential
collaboration.
