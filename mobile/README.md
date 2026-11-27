# TRUSTSEAL Native Mobile App (Flutter)

Native iOS & Android Flutter client wired directly to TRUSTSEAL's JWT REST APIs covering all 5 core modules:

1. **Home** — Executive Navy header band, 4-metric KPI strip (`Documents`, `Projects`, `Awaiting`, `QES`), quick actions, and live eSignature activity.
2. **Projects & My Work** — Active projects with progress tracking and one-tap Timesheet logging (`POST /api/timesheets/`).
3. **Contracts & Sign (eIDAS 2.0)** — Manage & dispatch `SES`, `AES`, and `QES` signature workflows with ETSI `PAdES-B-B / B-T / B-LT / B-LTA` profiles and one-tap Reminders.
4. **Documents & Stamps** — Search `.tsd` encrypted documents and inspect registered corporate stamps.
5. **Verify** — Cryptographic verification by `ESIG-...` Package Reference or SHA-256 digest showing eIDAS 2.0 tier, ETSI PAdES profile, OCSP status, and Hash-Chained Audit Trail integrity.

## Quick Start

```bash
cd mobile
flutter pub get
flutter analyze
flutter test
flutter run
```

When running against a local TRUSTSEAL server:
- **iOS Simulator / macOS:** `http://127.0.0.1:5017`
- **Android Emulator:** `http://10.0.2.2:5017`
