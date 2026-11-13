"""Create disposable current-legacy schema to test *new* Alembic revisions.

The repository's first 2025 migration is ALTER-only and cannot bootstrap a
fresh database. This script does NOT claim to reproduce a historical backup.
It deliberately excludes every new trust-service table added after revision
1856829bd7b1, then CI stamps that historical head and upgrades normally.

Only run in GitHub CI against the disposable trustseal_ci database.
"""
import os
from sqlalchemy import inspect
from app import create_app
from app.extensions import db

NEW_TABLES = {
    "revoked_tokens", "document_snapshots", "document_blobs",
    "security_events", "outbox_events",
    "signing_envelopes", "envelope_participants",
    "signer_challenges", "signer_decisions", "review_receipts",
    "finalized_pdfs", "signer_public_keys", "signer_key_challenges",
    "signer_endorsement_challenges", "signer_endorsements",
    "managed_stamps", "stamp_applications", "stamp_attestations",
    "stamped_pdfs", "stamp_design_versions",
    "evidence_retentions", "evidence_legal_holds", "evidence_checkpoints",
    "evidence_timestamps", "certificate_revocation_evidence",
    "ocsp_evidence", "validation_dossiers", "pdf_dss_derivatives",
}


def main():
    if os.getenv("CI") != "true" or os.getenv("FLASK_ENV") != "testing":
        raise SystemExit("Refusing legacy-baseline setup outside isolated CI")
    url = os.getenv("DATABASE_URL", "")
    if not url.endswith("@localhost:5432/trustseal_ci"):
        raise SystemExit("CI baseline requires disposable trustseal_ci database")
    app = create_app()
    with app.app_context():
        existing = inspect(db.engine).get_table_names()
        if existing:
            raise SystemExit("Refusing baseline creation on a nonempty database")
        table_list = [
            table for name, table in db.metadata.tables.items()
            if name not in NEW_TABLES
        ]
        db.metadata.create_all(bind=db.engine, tables=table_list)
        print("CI legacy-model baseline tables created:", len(table_list))
        print("Excluded trust-service tables:", len(NEW_TABLES))


if __name__ == "__main__":
    main()
