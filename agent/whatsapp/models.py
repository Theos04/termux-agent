"""Data models for WhatsApp Pharmacy Trading system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class ContactRole(str, Enum):
    RETAILER = "retailer"
    SUPPLIER = "supplier"
    PATIENT = "patient"
    PHARMACIST = "pharmacist"
    ADMIN = "admin"
    UNVERIFIED = "unverified"


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    REJECTED = "rejected"
    PENDING = "pending"


class IntentType(str, Enum):
    ADDRESS_CHANGE = "address_change"
    CHECK_STOCK = "check_stock"
    CATALOG_SEARCH = "catalog_search"
    SUPPLIER_QUOTE_REPLY = "supplier_quote_reply"
    SUPPLIER_RFQ_REQUEST = "supplier_rfq_request"
    ORDER_STATUS = "order_status"
    CREATE_ORDER = "create_order"
    WHOLESALE_PRICE_ENQUIRY = "wholesale_price_enquiry"
    MEDICAL_ADVICE = "medical_advice"
    HUMAN_ESCALATION = "human_escalation"
    GREETING = "greeting"
    UNKNOWN = "unknown"


@dataclass
class ContactInfo:
    id: str
    whatsapp_id: str
    display_name: Optional[str]
    verification_status: VerificationStatus
    roles: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def primary_role(self) -> ContactRole:
        if self.verification_status != VerificationStatus.VERIFIED:
            return ContactRole.UNVERIFIED
        for r in self.roles:
            role_str = (r.get("role") or "").lower()
            if role_str == "retailer":
                return ContactRole.RETAILER
            if role_str == "supplier":
                return ContactRole.SUPPLIER
            if role_str == "patient":
                return ContactRole.PATIENT
        return ContactRole.UNVERIFIED

    @property
    def business_id(self) -> Optional[str]:
        if self.roles:
            return self.roles[0].get("business_id")
        return None

    @property
    def business_name(self) -> Optional[str]:
        if self.roles:
            return self.roles[0].get("legal_name")
        return None


@dataclass
class IntentResult:
    intent: IntentType
    confidence: float
    product_query: Optional[str] = None
    order_id: Optional[str] = None
    new_address: Optional[str] = None
    quantity: Optional[float] = None
    quoted_price: Optional[float] = None
    expiry_date: Optional[str] = None
    pack_size: Optional[str] = None
    raw_text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DispatchResult:
    ok: bool
    intent: IntentType
    response_text: str
    execution_trace: List[str] = field(default_factory=list)
    action_taken: Optional[str] = None
    requires_human_review: bool = False
    audit_event_id: Optional[int] = None
    details: Dict[str, Any] = field(default_factory=dict)
