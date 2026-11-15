"""Disposable certificate authority for real PDF integration tests only.

Several integration modules call ``create_app()`` directly instead of
using ``pg_app`` from ``tests/conftest.py``. Those modules still need
``DATABASE_URL`` and the full schema to be in place — otherwise the
first ``Organization`` insert hits ``relation "organizations" does
not exist``. The autouse ``_integration_schema`` fixture below pulls
in the session-scope ``_session_app`` exactly once per module so
``DATABASE_URL`` is set and ``db.create_all()`` has run before any
module-level ``create_app()`` call runs.

``test_migration_replay`` is the exception — it deliberately runs
against its own disposable Postgres. It overrides the shared engine
locally; the autouse fixture here is harmless because
``test_migration_replay`` never queries through Flask-SQLAlchemy's
default engine after the override.
"""
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID


@pytest.fixture(scope="module", autouse=True)
def _integration_schema(_session_app):
    """Ensure ``DATABASE_URL`` is set, the schema exists, and the
    append-only snapshot triggers that Alembic migrations install
    are installed on the test schema.

    ``_session_app`` is a session-scope fixture from
    ``tests/conftest.py`` that creates a disposable Postgres database,
    sets ``os.environ['DATABASE_URL']``, runs ``db.create_all()``, and
    tears everything down at session end. Pulling it in once per
    integration module is enough because its side-effects are global.

    ``db.create_all()`` only builds table structure — it does not
    install the ``trustseal_reject_snapshot_mutation`` function and
    the ``BEFORE UPDATE OR DELETE`` triggers that production migrations
    attach to immutable evidence tables. Several integration tests
    assert that an ordinary UPDATE raises ``DatabaseError``; without
    the trigger they would silently succeed. We install the function
    + triggers idempotently here. Already-installed triggers (e.g.
    from a prior module in the same session) are a no-op.
    """
    from app.extensions import db

    append_only_tables = [
        "document_snapshots",
        "signer_decisions",
        "review_receipts",
        "evidence_timestamps",
        "ocsp_evidence",
        "certificate_revocation_evidence",
        "stamp_attestations",
        "stamped_pdfs",
        "document_blobs",
        "validation_dossiers",
    ]
    with _session_app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql("RESET ROLE")
            conn.exec_driver_sql(
                """
                CREATE OR REPLACE FUNCTION trustseal_reject_snapshot_mutation()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    RAISE EXCEPTION 'evidence snapshots are append-only'
                        USING ERRCODE = '23514';
                END;
                $$;
                """
            )
            existing = {
                r[0] for r in conn.exec_driver_sql(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                ).fetchall()
            }
            installed_triggers = []
            for table in append_only_tables:
                if table not in existing:
                    continue
                trigger_name = f"trg_{table}_append_only"
                conn.exec_driver_sql(
                    f'DROP TRIGGER IF EXISTS {trigger_name} ON "{table}"'
                )
                conn.exec_driver_sql(
                    f"""
                    CREATE TRIGGER {trigger_name}
                    BEFORE UPDATE OR DELETE ON "{table}"
                    FOR EACH ROW
                    EXECUTE FUNCTION trustseal_reject_snapshot_mutation()
                    """
                )
                installed_triggers.append((trigger_name, table))
    yield _session_app
    # Tear the triggers down so non-integration test modules that run
    # later in the same pytest session (e.g.
    # tests/test_envelope_orchestrator.py) still see a schema without
    # append-only enforcement. The autouse fixture reinstalls them for
    # the next integration module.
    with _session_app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql("RESET ROLE")
            for trigger_name, table in installed_triggers:
                conn.exec_driver_sql(
                    f'DROP TRIGGER IF EXISTS {trigger_name} ON "{table}"'
                )


def certificate(subject, issuer, public_key, signer_key, is_ca, now):
    builder = (
        x509.CertificateBuilder().subject_name(subject).issuer_name(issuer)
        .public_key(public_key).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(
            x509.BasicConstraints(ca=is_ca, path_length=0 if is_ca else None),
            critical=True,
        )
    )
    if is_ca:
        usage = x509.KeyUsage(
            digital_signature=True, content_commitment=False,
            key_encipherment=False, data_encipherment=False,
            key_agreement=False, key_cert_sign=True, crl_sign=True,
            encipher_only=False, decipher_only=False,
        )
    else:
        usage = x509.KeyUsage(
            digital_signature=True, content_commitment=True,
            key_encipherment=False, data_encipherment=False,
            key_agreement=False, key_cert_sign=False, crl_sign=False,
            encipher_only=False, decipher_only=False,
        )
    return builder.add_extension(usage, critical=True).sign(signer_key, hashes.SHA256())


@pytest.fixture
def signing_config(tmp_path):
    now = datetime.now(timezone.utc)
    root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    root_name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Disposable TrustSeal Test Root")
    ])
    root_cert = certificate(
        root_name, root_name, root_key.public_key(), root_key, True, now,
    )
    seal_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    seal_name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Disposable TrustSeal Platform Seal")
    ])
    seal_cert = certificate(
        seal_name, root_name, seal_key.public_key(), root_key, False, now,
    )
    password = b"disposable-test-password"
    bundle = pkcs12.serialize_key_and_certificates(
        b"disposable-seal", seal_key, seal_cert, [root_cert],
        serialization.BestAvailableEncryption(password),
    )
    bundle_path = tmp_path / "seal.p12"
    bundle_path.write_bytes(bundle)
    bundle_path.chmod(0o600)
    root_path = tmp_path / "root.pem"
    root_path.write_bytes(root_cert.public_bytes(serialization.Encoding.PEM))
    return {
        "PDF_PLATFORM_PKCS12": str(bundle_path),
        "PDF_PLATFORM_PKCS12_PASSWORD": password.decode("ascii"),
        "PDF_TRUST_ROOT_PEM": str(root_path),
        "PDF_FINALIZATION_ENABLED": True,
    }
