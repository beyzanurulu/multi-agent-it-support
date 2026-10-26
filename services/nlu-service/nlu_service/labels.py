"""Label schema shared by the NLU service and the ml/ training pipeline."""

INTENTS = [
    "password_reset", "vpn_issue", "email_issue", "software_install", "hardware_issue",
    "network_issue", "access_request", "printer_issue", "account_locked", "ticket_status",
    "report_request", "other",
]
ENTITIES = ["YAZILIM", "CIHAZ", "HATA_KODU", "DEPARTMAN", "KISI", "IP_ADRESI", "TARIH"]
BIO_LABELS = ["O"] + [f"{p}-{e}" for e in ENTITIES for p in ("B", "I")]
