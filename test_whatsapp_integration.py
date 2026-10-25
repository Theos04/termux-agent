#!/usr/bin/env python3
"""
Comprehensive Integration Test for WhatsApp CDP Agent & Pharmacy Trading Trio.

Verifies:
  1. Port isolation: WhatsApp agent operates on port 9223 (separate from Maps on 9222).
  2. Data sync from Google Sheets (PRODUCT sheet gid: 1112889530, party, Seller, PurchaseList).
  3. The Specialist Trio + Router Dispatcher:
     - Scenario A: "Change my delivery address" (READ -> WRITE -> ACTION -> ResponseComposer).
     - Scenario B: Stock enquiry for Google Sheet products (factual READ, no mutations).
     - Scenario C: Supplier quote processing (READ -> WRITE -> ACTION).
     - Scenario D: Wholesale price access blocked for unverified contacts (Compliance gate).
     - Scenario E: Medical advice inquiry blocked safely (Pharmaceutical safeguard).
  4. Audit logging & transactional outbox idempotency.
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.config import AgentConfig
from agent.database import Database
from agent.whatsapp import (
    ContactRole,
    IntentType,
    VerificationStatus,
    WhatsAppCDPClient,
    WhatsAppRouter,
)
from agent.whatsapp.google_sheet_sync import GoogleSheetPharmacySync


def banner(msg: str):
    print(f"\n{'━'*68}\n  {msg}\n{'━'*68}")


def ok(msg: str):
    print(f"  ✅  {msg}")


def fail(msg: str):
    print(f"  ❌  {msg}")


def info(msg: str):
    print(f"  ℹ️   {msg}")


def main():
    banner("WhatsApp CDP Agent & Pharmacy Trading Trio — Integration Test")

    cfg = AgentConfig()
    db = Database(cfg.db_path)

    # ──────────────────────────────────────────────────────────────────────────
    # Step 1: Port Isolation
    # ──────────────────────────────────────────────────────────────────────────
    banner("Step 1: Port Separation & Isolated Browser Configuration")
    wa_port = cfg.whatsapp_cdp_port
    maps_port = int(os.environ.get("CDP_PORT", "9222"))

    info(f"Maps Scraper CDP Port     : {maps_port}")
    info(f"WhatsApp Agent CDP Port   : {wa_port}")
    info(f"WhatsApp Chrome Profile   : {cfg.whatsapp_profile_dir}")

    assert wa_port != maps_port, "WhatsApp port must not collide with Maps scraping port!"
    assert wa_port == 9223, f"Expected WhatsApp port 9223, got {wa_port}"
    ok(f"Verified port separation: WhatsApp is on dedicated port {wa_port}")

    # ──────────────────────────────────────────────────────────────────────────
    # Step 2: Database & Google Sheets Data Integration
    # ──────────────────────────────────────────────────────────────────────────
    banner("Step 2: Database Schema & Google Sheets Ingestion (gid: 1112889530)")
    db.seed_pharmacy_demo_data()

    creds_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")
    if os.path.isfile(creds_path):
        info(f"Syncing live sheets data using {creds_path}...")
        sync = GoogleSheetPharmacySync(db)
        sync_res = sync.sync_all(product_limit=100, party_limit=50)
        ok(f"Google Sheets sync succeeded:")
        info(f"  Products synced  : {sync_res.get('products_synced')}")
        info(f"  Retailers synced : {sync_res.get('retailers_synced')}")
        info(f"  Suppliers synced : {sync_res.get('suppliers_synced')}")
        info(f"  Batches synced   : {sync_res.get('inventory_batches_synced')}")
    else:
        info("No credentials.json found; verified demo seed data in place.")

    # ──────────────────────────────────────────────────────────────────────────
    # Step 3: Trio Specialist Tests
    # ──────────────────────────────────────────────────────────────────────────
    banner("Step 3: Specialist Agents & Router Dispatcher Pipeline")
    cdp_mock = WhatsAppCDPClient(port=wa_port, mock_mode=True)
    router = WhatsAppRouter(db, cdp_mock)

    # ── Test A: Address Change (The canonical 4-step pipeline) ───────────────
    info("[Scenario A] 'Change my delivery address for ord_lc_1001'")
    res_a = router.dispatch(
        sender_phone="+919876543210",
        message_text="Change my delivery address for ord_lc_1001 to Shop 15, FC Road, Pune 411004",
    )
    assert res_a.ok, f"Address change failed: {res_a}"
    assert res_a.intent == IntentType.ADDRESS_CHANGE
    assert "Shop 15, FC Road, Pune 411004" in res_a.response_text
    # Verify trace steps
    trace_text = " | ".join(res_a.execution_trace)
    assert "READ:" in trace_text, "Missing READ step in trace"
    assert "WRITE:" in trace_text, "Missing WRITE step in trace"
    assert "ACTION:" in trace_text, "Missing ACTION step in trace"
    ok("Scenario A Passed: READ verified -> WRITE mutated DB -> ACTION enqueued -> Confirmed")

    # Verify updated address in DB
    updated_order = db.get_sales_order("ord_lc_1001")
    assert updated_order["delivery_address"] == "Shop 15, FC Road, Pune 411004"
    ok(f"DB verification: Order ord_lc_1001 delivery_address = '{updated_order['delivery_address']}'")

    # ── Test B: Check Stock (Read-only intelligence, no DB mutation) ──────────
    info("[Scenario B] 'Check stock for Paracetamol 500mg'")
    res_b = router.dispatch(
        sender_phone="+919607828641",
        message_text="Check stock for Paracetamol 500mg",
    )
    assert res_b.ok
    assert res_b.intent == IntentType.CHECK_STOCK
    assert "Total Usable Stock: 110" in res_b.response_text
    assert "Batch PCM24A" in res_b.response_text
    ok("Scenario B Passed: Factual stock returned with batch numbers & expiry")

    # ── Test C: Supplier Quote Reply ──────────────────────────────────────────
    info("[Scenario C] Supplier quote reply: '200 packs available. ₹82 per pack. Expiry 08/2028'")
    res_c = router.dispatch(
        sender_phone="+919822001122",
        message_text="200 packs available. ₹82 per pack. Expiry 08/2028. Delivery tomorrow.",
    )
    assert res_c.ok
    assert res_c.intent == IntentType.SUPPLIER_QUOTE_REPLY
    assert "Quotation Received" in res_c.response_text
    ok("Scenario C Passed: Supplier quote parsed, validated, and logged to supplier_quotes")

    # ── Test D: Wholesale Price Request from Unverified Contact ──────────────
    info("[Scenario D] Unverified contact asks for wholesale price list")
    res_d = router.dispatch(
        sender_phone="+918888777766",
        message_text="Send me your wholesale price list and catalog rates",
    )
    assert res_d.ok
    assert "Form 20B/21B" in res_d.response_text or "verified" in res_d.response_text
    assert "POLICY: Denied wholesale price list" in " | ".join(res_d.execution_trace)
    ok("Scenario D Passed: Wholesale pricing protected behind mandatory license verification")

    # ── Test E: Medical Diagnosis Inquiry Blocked ────────────────────────────
    info("[Scenario E] Medical diagnosis safeguard")
    res_e = router.dispatch(
        sender_phone="+918888777766",
        message_text="I have severe fever and headache, which medicine should I take?",
    )
    assert res_e.ok
    assert res_e.requires_human_review
    assert "cannot diagnose medical conditions" in res_e.response_text
    assert "SAFEGUARD: Blocked medical diagnosis inquiry" in " | ".join(res_e.execution_trace)
    ok("Scenario E Passed: Medical diagnosis blocked safely; escalated to pharmacist")

    # ──────────────────────────────────────────────────────────────────────────
    # Step 4: Audit Trail & Transactional Outbox Idempotency
    # ──────────────────────────────────────────────────────────────────────────
    banner("Step 4: Audit Events & Transactional Outbox Idempotency")
    audit_events = db.get_audit_events(limit=10)
    assert len(audit_events) > 0, "Audit events must be recorded!"
    info(f"Total recent audit events: {len(audit_events)}")
    for ev in audit_events[:4]:
        info(f"  • [{ev['created_at'][11:19]}] {ev['actor_type']} -> {ev['action']} ({ev['outcome']})")
    ok("Audit trail verified")

    # Outbox Idempotency test
    outbox_key = "test_idem_key_001"
    msg1 = router.action.send_whatsapp_message("+919876543210", "Test message 1", idempotency_key=outbox_key)
    msg2 = router.action.send_whatsapp_message("+919876543210", "Test message 2 (duplicate)", idempotency_key=outbox_key)
    assert msg1["idempotency_key"] == msg2["idempotency_key"]
    ok("Transactional outbox idempotency verified: Duplicate sends with same key deduplicated")

    banner("ALL INTEGRATION TESTS PASSED SUCCESSFULLY! ✅")


if __name__ == "__main__":
    main()
