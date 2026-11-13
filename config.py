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
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

    # === New private document ingest service (not the legacy upload path) ===
    # Must be an absolute path outside the Flask static directory, backed up
    # separately, writable only by the application service account.
    PRIVATE_DOCUMENT_ROOT = os.getenv('PRIVATE_DOCUMENT_ROOT')
    DOCUMENT_CLAMSCAN_BINARY = os.getenv('DOCUMENT_CLAMSCAN_BINARY')
    DOCUMENT_SCAN_TIMEOUT = int(os.getenv('DOCUMENT_SCAN_TIMEOUT', '30'))

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
