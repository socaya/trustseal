import logging
import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()

class Config:

    # === Core Flask Settings ===
    SECRET_KEY = os.getenv('SECRET_KEY')
    API_BASE_URL = os.getenv('API_BASE_URL', 'http://127.0.0.1:5000/api')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'postgresql://trustseal:password@localhost/trustseal')
    SQLALCHEMY_TRACK_MODIFICATIONS = os.getenv('SQLALCHEMY_TRACK_MODIFICATIONS', 'false').lower() == 'true'
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', '1') == '1'

    # === File Uploads ===
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static/uploads')
    QR_CODE_FOLDER = os.path.join(os.path.dirname(__file__), 'static/qrcodes')
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'docx'}
    MAX_CONTENT_LENGTH = 17 * 1024 * 1024  # 16 MiB file plus multipart framing

    # === New private document ingest service (not the legacy upload path) ===
    # Must be an absolute path outside the Flask static directory, backed up
    # separately, writable only by the application service account.
    PRIVATE_DOCUMENT_ROOT = os.getenv('PRIVATE_DOCUMENT_ROOT')
    DOCUMENT_CLAMSCAN_BINARY = os.getenv('DOCUMENT_CLAMSCAN_BINARY')
    DOCUMENT_SCAN_TIMEOUT = int(os.getenv('DOCUMENT_SCAN_TIMEOUT', '30'))

    # === Detached review attestation keys (operator issuance only) ===
    # Protected private key path, never a URL, static asset or checked-in secret.
    REVIEW_RECEIPT_PRIVATE_KEY = os.getenv('REVIEW_RECEIPT_PRIVATE_KEY')
    REVIEW_RECEIPT_PUBLIC_KEY = os.getenv('REVIEW_RECEIPT_PUBLIC_KEY')
    REVIEW_RECEIPT_TRUSTED_KEYS_JSON = os.getenv('REVIEW_RECEIPT_TRUSTED_KEYS_JSON')

    # === Gated platform PDF seal (not individual signer credentials) ===
    PDF_PLATFORM_PKCS12 = os.getenv('PDF_PLATFORM_PKCS12')
    PDF_PLATFORM_PKCS12_PASSWORD = os.getenv('PDF_PLATFORM_PKCS12_PASSWORD')
    PDF_TRUST_ROOT_PEM = os.getenv('PDF_TRUST_ROOT_PEM')
    PDF_SEAL_OPERATOR_ID = os.getenv('PDF_SEAL_OPERATOR_ID')
    PDF_FINALIZATION_ENABLED = os.getenv('PDF_FINALIZATION_ENABLED', 'false').lower() == 'true'
    PUBLIC_PDF_VERIFICATION_ENABLED = os.getenv('PUBLIC_PDF_VERIFICATION_ENABLED', 'false').lower() == 'true'
    PUBLIC_PDF_VERIFICATION_CERT_SHA256 = os.getenv('PUBLIC_PDF_VERIFICATION_CERT_SHA256')

    # === Governed organizational stamp issuance (operator-only) ===
    STAMP_ATTESTATION_ENABLED = os.getenv('STAMP_ATTESTATION_ENABLED', 'false').lower() == 'true'
    STAMP_PDF_RENDER_ENABLED = os.getenv('STAMP_PDF_RENDER_ENABLED', 'false').lower() == 'true'
    STAMP_ATTESTATION_PRIVATE_KEY = os.getenv('STAMP_ATTESTATION_PRIVATE_KEY')
    STAMP_ATTESTATION_PUBLIC_KEY = os.getenv('STAMP_ATTESTATION_PUBLIC_KEY')
    STAMP_ATTESTATION_TRUSTED_KEYS_JSON = os.getenv('STAMP_ATTESTATION_TRUSTED_KEYS_JSON')
    STAMP_ATTESTATION_OPERATOR_ID = os.getenv('STAMP_ATTESTATION_OPERATOR_ID')

    # === Evidence preservation and independent checkpoint attestations ===
    EVIDENCE_CHECKPOINT_ENABLED = os.getenv('EVIDENCE_CHECKPOINT_ENABLED', 'false').lower() == 'true'
    EVIDENCE_CHECKPOINT_PRIVATE_KEY = os.getenv('EVIDENCE_CHECKPOINT_PRIVATE_KEY')
    EVIDENCE_CHECKPOINT_PUBLIC_KEY = os.getenv('EVIDENCE_CHECKPOINT_PUBLIC_KEY')
    EVIDENCE_CHECKPOINT_TRUSTED_KEYS_JSON = os.getenv('EVIDENCE_CHECKPOINT_TRUSTED_KEYS_JSON')
    EVIDENCE_CHECKPOINT_OPERATOR_ID = os.getenv('EVIDENCE_CHECKPOINT_OPERATOR_ID')

    # === Detached RFC 3161 TSA integration (network disabled by default) ===
    RFC3161_ENABLED = os.getenv('RFC3161_ENABLED', 'false').lower() == 'true'
    RFC3161_TSA_URL = os.getenv('RFC3161_TSA_URL')
    RFC3161_TSA_CERT_PEM = os.getenv('RFC3161_TSA_CERT_PEM')
    RFC3161_TRUST_ROOT_PEM = os.getenv('RFC3161_TRUST_ROOT_PEM')
    RFC3161_OPENSSL_BINARY = os.getenv('RFC3161_OPENSSL_BINARY', 'openssl')

    # === Controlled TSA issuer CRL evidence; no arbitrary remote fetching ===
    CRL_EVIDENCE_ENABLED = os.getenv('CRL_EVIDENCE_ENABLED', 'false').lower() == 'true'
    CRL_EVIDENCE_DER = os.getenv('CRL_EVIDENCE_DER')
    CRL_ISSUER_CERT_PEM = os.getenv('CRL_ISSUER_CERT_PEM')

    # === Pinned, operator-supplied TSA OCSP response evidence ===
    OCSP_EVIDENCE_ENABLED = os.getenv('OCSP_EVIDENCE_ENABLED', 'false').lower() == 'true'
    OCSP_EVIDENCE_DER = os.getenv('OCSP_EVIDENCE_DER')
    OCSP_ISSUER_CERT_PEM = os.getenv('OCSP_ISSUER_CERT_PEM')

    # === Immutable partial PKIX evidence dossier ===
    VALIDATION_DOSSIER_ENABLED = os.getenv('VALIDATION_DOSSIER_ENABLED', 'false').lower() == 'true'

    # Bounded explicit TSA certificate chain (JSON array of approved PEM paths).
    VALIDATION_TSA_INTERMEDIATES_JSON = os.getenv('VALIDATION_TSA_INTERMEDIATES_JSON', '[]')

    # Optional issuer-signed DER CRLs aligned with non-root chain positions.
    # JSON array: leaf first, then each intermediate; null means absent.
    VALIDATION_CHAIN_CRL_PATHS_JSON = os.getenv('VALIDATION_CHAIN_CRL_PATHS_JSON')

    # === JWT Configuration ===
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=5)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

    # === Email Configuration ===
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.trustseal.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USERNAME = os.getenv('MAIL_USERNAME', 'noreply@trustseal.com')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.getenv('DEFAULT_MAIL_SENDER', 'TrustSeal <noreply@trustseal.com>')

    # # === Subscription Plan Config (static app-level override for dev/test use) ===
    # SUBSCRIPTION_PLANS = {
    #     'free': {'stamps': 10, 'esign': False, 'contracts': False},
    #     'pro': {'stamps': None, 'esign': True, 'contracts': False},
    #     'business': {'stamps': None, 'esign': True, 'contracts': True}
    # }

    LOGGING_LEVEL = logging.DEBUG

    PERMANENT_SESSION_LIFETIME = timedelta(minutes=5)
    SESSION_PERMANENT = True
