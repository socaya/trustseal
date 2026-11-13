from enum import Enum

class PermissionEnum(str, Enum):
    ALL = "all"

    # User Management
    MANAGE_USERS = "manage_users"
    INVITE_USERS = "invite_users"
    ASSIGN_ROLES = "assign_roles"
    RESET_PASSWORDS = "reset_passwords"

    # Organizations
    MANAGE_ORGANIZATIONS = "manage_organizations"
    VERIFY_ORGANIZATIONS = "verify_organizations"
    VIEW_ORGANIZATION_PROFILE = "view_organization_profile"

    # Clients
    CREATE_CLIENT = "create_client"
    EDIT_CLIENT = "edit_client"
    DELETE_CLIENT = "delete_client"
    VIEW_CLIENT = "view_client"
    EXPORT_CLIENT_DATA = "export_client_data"

    # Documents
    CREATE_DOCUMENTS = "create_documents"
    VIEW_DOCUMENTS = "view_documents"
    EDIT_DOCUMENTS = "edit_documents"
    DELETE_DOCUMENTS = "delete_documents"
    SHARE_DOCUMENTS = "share_documents"
    TRACK_DOCUMENT_STATUS = "track_document_status"
    DOWNLOAD_DOCUMENTS = "download_documents"
    MANAGE_DOCUMENT_TEMPLATES = "manage_document_templates"

    # Stamps
    CREATE_STAMP = "create_stamp"
    EDIT_STAMP = "edit_stamp"
    DELETE_STAMP = "delete_stamp"
    VIEW_STAMP = "view_stamp"
    ASSIGN_STAMP = "assign_stamp"
    DOWNLOAD_STAMP = "download_stamp"
    APPLY_STAMP = "apply_stamp"
    APPLY_STAMP_MULTIPLE = "apply_stamp_multiple"
    PREVIEW_STAMP = "preview_stamp"
    REMOVE_STAMP = "remove_stamp"
    SELECT_STAMP_POSITION = "select_stamp_position"
    USE_CUSTOM_STAMP = "use_custom_stamp"
    AUTO_STAMP_ON_UPLOAD = "auto_stamp_on_upload"

    # Signatures
    APPLY_SIGNATURE = "apply_signature"
    ASSIGN_SIGNATURE_ROLE = "assign_signature_role"
    SET_SIGNATURE_ORDER = "set_signature_order"
    PREVIEW_SIGNATURE = "preview_signature"
    REMOVE_SIGNATURE = "remove_signature"
    USE_CUSTOM_SIGNATURE = "use_custom_signature"
    REJECT_SIGNATURE_REQUEST = "reject_signature_request"
    SIGN_WITH_AUTHENTICATION = "sign_with_authentication"
    VIEW_SIGNATURE_LOGS = "view_signature_logs"
    RESEND_SIGNATURE_REMINDER = "resend_signature_reminder"
    CANCEL_SIGNATURE_REQUEST = "cancel_signature_request"
    SEND_SIGNATURE_REQUEST = "send_signature_request"
    VIEW_SIGNATURE_STATUS = "view_signature_status"

    # Subscriptions & Billing
    VIEW_SUBSCRIPTION = "view_subscription"
    MANAGE_SUBSCRIPTION = "manage_subscription"
    MANAGE_SUBSCRIPTION_PLANS = "manage_subscription_plans"
    VIEW_INVOICES = "view_invoices"
    MANAGE_PAYMENTS = "manage_payments"

    # System Settings
    VIEW_SYSTEM_SETTINGS = "view_system_settings"
    EDIT_SYSTEM_SETTINGS = "edit_system_settings"
    MANAGE_NOTIFICATION_TEMPLATES = "manage_notification_templates"

    # RBAC
    MANAGE_ROLES = "manage_roles"
    MANAGE_PERMISSIONS = "manage_permissions"

    # Logs & Reports
    VIEW_AUDIT_LOGS = "view_audit_logs"
    VIEW_REPORTS = "view_reports"
    GENERATE_REPORTS = "generate_reports"

    # Contracts & Workflows
    DRAFT_CONTRACTS = "draft_contracts"
    APPROVE_CONTRACTS = "approve_contracts"
    MANAGE_CONTRACT_TEMPLATES = "manage_contract_templates"
    MANAGE_WORKFLOWS = "manage_workflows"

    # Developer & Integration
    MANAGE_API_KEYS = "manage_api_keys"
    CONFIGURE_WEBHOOKS = "configure_webhooks"