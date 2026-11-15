"""Thin adapters around external infrastructure.

Provider-specific code lives behind narrow interfaces so object storage,
KMS/HSM, scanner, email/SMS, timestamp, and payment providers can be
swapped out without touching domain services.
"""
