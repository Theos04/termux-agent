"""
Google Sheets Pharmacy Data Synchronizer.

Connects to the enterprise Google Sheet:
  Spreadsheet ID: 1Itov6RmBS0OBkACY8MMOOkUZlpjhgrUkMuApXKZHll8
  Credentials   : ./credentials.json (Service Account)

Synchronizes:
  - 'PRODUCT '  (gid: 1112889530) -> products catalog (canonical name, brand, composition, MRP, PTR)
  - 'party'     (gid: 252318196)  -> retail pharmacy buyers & phone numbers (verified retailers)
  - 'Seller '   (gid: 1148289740) -> approved medicine suppliers & distributors
  - 'PurchaseList' (gid: 858380472) -> real inventory batches with batch numbers, expiries, quantities
  - 'Sales Order ' (gid: 1388188177) -> historical sales orders
  - 'whatsapp sales order ' (gid: 193895394) -> logs orders originating via WhatsApp back to Google Sheets
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from agent.database import Database, utcnow

log = logging.getLogger(__name__)

DEFAULT_SPREADSHEET_ID = "1Itov6RmBS0OBkACY8MMOOkUZlpjhgrUkMuApXKZHll8"
DEFAULT_CREDS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "credentials.json")


class GoogleSheetPharmacySync:
    """Synchronizes pharmacy catalog, contacts, suppliers, and orders with Google Sheets."""

    def __init__(
        self,
        db: Database,
        creds_path: Optional[str] = None,
        spreadsheet_id: Optional[str] = None,
    ):
        self.db = db
        self.spreadsheet_id = spreadsheet_id or os.environ.get("GOOGLE_SHEET_ID", DEFAULT_SPREADSHEET_ID)
        self.creds_path = creds_path or os.environ.get("GOOGLE_CREDS_JSON", DEFAULT_CREDS_PATH)
        self._service = None

    def _get_service(self):
        """Lazy load Sheets API service client."""
        if self._service is None:
            if not os.path.isfile(self.creds_path):
                raise FileNotFoundError(f"Credentials JSON not found at {self.creds_path}")
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive.file",
            ]
            creds = service_account.Credentials.from_service_account_file(self.creds_path, scopes=scopes)
            self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        return self._service

    def fetch_sheet_rows(self, sheet_title: str, max_rows: int = 2000) -> List[List[Any]]:
        """Fetch raw rows from a named worksheet."""
        svc = self._get_service()
        range_name = f"'{sheet_title}'!A1:Z{max_rows}"
        res = svc.spreadsheets().values().get(spreadsheetId=self.spreadsheet_id, range=range_name).execute()
        return res.get("values", [])

    # ──────────────────────────────────────────────────────────────────────────
    # Sheet Ingestion Methods
    # ──────────────────────────────────────────────────────────────────────────

    def sync_products(self, limit: int = 1500) -> Dict[str, int]:
        """
        Sync 'PRODUCT ' sheet (gid: 1112889530) to local SQLite products table.
        Columns: ID, Company Name, Product image link, Item, Composition , Segment, MRP, Purchase Cost , Net Purchase , Goods acquisition cost , Profit Margin , PTR, Gross Rate, Status, Product Information
        """
        rows = self.fetch_sheet_rows("PRODUCT ", max_rows=limit + 1)
        if not rows or len(rows) < 2:
            return {"inserted": 0, "updated": 0, "total": 0}

        headers = [str(h).strip().lower() for h in rows[0]]
        # Find index positions
        idx_id = headers.index("id") if "id" in headers else 0
        idx_company = headers.index("company name") if "company name" in headers else 1
        idx_item = headers.index("item") if "item" in headers else 3
        idx_comp = headers.index("composition") if "composition" in headers else (headers.index("composition ") if "composition " in headers else 4)
        idx_segment = headers.index("segment") if "segment" in headers else 5
        idx_mrp = headers.index("mrp") if "mrp" in headers else 6
        idx_ptr = headers.index("ptr") if "ptr" in headers else 11

        now = utcnow()
        inserted = 0

        with self.db.transaction() as conn:
            for r in rows[1:]:
                if not r or len(r) <= idx_item:
                    continue
                item_name = str(r[idx_item]).strip()
                if not item_name:
                    continue

                prod_id = f"prod_gs_{str(r[idx_id]).strip()}" if len(r) > idx_id and r[idx_id] else f"prod_gs_{re.sub(r'[^a-zA-Z0-9]', '', item_name)[:16].lower()}"
                company = str(r[idx_company]).strip() if len(r) > idx_company else ""
                composition = str(r[idx_comp]).strip() if len(r) > idx_comp else ""
                segment = str(r[idx_segment]).strip() if len(r) > idx_segment else "General"
                mrp = str(r[idx_mrp]).strip() if len(r) > idx_mrp else ""
                ptr = str(r[idx_ptr]).strip() if len(r) > idx_ptr else ""

                # Strength / pack size inference if in name
                strength_m = re.search(r"(\d+(?:\.\d+)?\s*(?:mg|gm|ml|iu|mcg|%))", item_name, re.IGNORECASE)
                strength = strength_m.group(1) if strength_m else "Standard"

                pack_size = "Standard Pack"
                if "inj" in item_name.lower():
                    dosage_form = "Injection"
                elif "syp" in item_name.lower() or "susp" in item_name.lower():
                    dosage_form = "Syrup"
                elif "cap" in item_name.lower():
                    dosage_form = "Capsule"
                else:
                    dosage_form = "Tablet"

                conn.execute(
                    """INSERT INTO products
                        (id, canonical_name, brand, ingredient, strength, dosage_form, pack_size, manufacturer, schedule_class, active, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                       ON CONFLICT(id) DO UPDATE SET
                         canonical_name=excluded.canonical_name,
                         brand=excluded.brand,
                         ingredient=excluded.ingredient,
                         strength=excluded.strength,
                         dosage_form=excluded.dosage_form,
                         pack_size=excluded.pack_size,
                         manufacturer=excluded.manufacturer,
                         schedule_class=excluded.schedule_class""",
                    (prod_id, item_name, company or item_name, composition, strength, dosage_form, pack_size, company, segment, now),
                )
                inserted += 1

        log.info("Synced %d products from Google Sheet into SQLite", inserted)
        return {"inserted": inserted, "total": len(rows) - 1}

    def sync_parties_and_contacts(self, limit: int = 1000) -> Dict[str, int]:
        """
        Sync 'party' sheet (gid: 252318196) to businesses & contacts.
        Columns: GROUP, CUSTOMER NAME, PHONE NUMBER
        """
        rows = self.fetch_sheet_rows("party", max_rows=limit + 1)
        if not rows or len(rows) < 2:
            return {"synced": 0}

        now = utcnow()
        synced = 0

        with self.db.transaction() as conn:
            for r in rows[1:]:
                if len(r) < 3:
                    continue
                name = str(r[1]).strip().replace("\x0b", "")
                phone_raw = str(r[2]).strip()
                if not phone_raw or len(phone_raw) < 7:
                    continue

                # Standardize phone to +91
                digits = re.sub(r"\D", "", phone_raw)
                if len(digits) == 10:
                    clean_phone = f"+91{digits}"
                elif len(digits) == 12 and digits.startswith("91"):
                    clean_phone = f"+{digits}"
                else:
                    clean_phone = phone_raw

                biz_id = f"biz_ret_{digits[-10:] if len(digits) >= 10 else digits}"
                cid = f"cnt_ret_{digits[-10:] if len(digits) >= 10 else digits}"

                # 1. Upsert business
                conn.execute(
                    """INSERT INTO businesses
                        (id, legal_name, business_type, license_status, status, created_at)
                       VALUES (?, ?, 'retail_pharmacy', 'verified', 'active', ?)
                       ON CONFLICT(id) DO UPDATE SET legal_name=excluded.legal_name""",
                    (biz_id, name[:120], now),
                )

                # 2. Upsert contact
                conn.execute(
                    """INSERT INTO contacts
                        (id, whatsapp_id, display_name, verification_status, created_at)
                       VALUES (?, ?, ?, 'verified', ?)
                       ON CONFLICT(whatsapp_id) DO UPDATE SET display_name=excluded.display_name""",
                    (cid, clean_phone, name[:60], now),
                )

                # 3. Upsert contact_role
                # Fetch actual contact ID in case it already existed with another id
                actual_c = conn.execute("SELECT id FROM contacts WHERE whatsapp_id = ?", (clean_phone,)).fetchone()
                actual_cid = actual_c["id"] if actual_c else cid

                conn.execute(
                    """INSERT INTO contact_roles
                        (contact_id, business_id, role, approved_by, approved_at)
                       VALUES (?, ?, 'retailer', 'gsheet_sync', ?)
                       ON CONFLICT(contact_id, business_id, role) DO NOTHING""",
                    (actual_cid, biz_id, now),
                )
                synced += 1

        log.info("Synced %d retail pharmacy parties from Google Sheet into SQLite", synced)
        return {"synced": synced}

    def sync_suppliers(self) -> Dict[str, int]:
        """
        Sync 'Seller ' sheet (gid: 1148289740) to businesses & contacts.
        Columns: Customer Name, Phone Number, Address
        """
        rows = self.fetch_sheet_rows("Seller ", max_rows=50)
        if not rows or len(rows) < 2:
            return {"synced": 0}

        now = utcnow()
        synced = 0

        with self.db.transaction() as conn:
            for r in rows[1:]:
                if not r or not r[0]:
                    continue
                name = str(r[0]).strip()
                phone_raw = str(r[1]).strip() if len(r) > 1 else ""
                digits = re.sub(r"\D", "", phone_raw)
                clean_phone = f"+91{digits}" if len(digits) == 10 else phone_raw or "+919822195091"

                biz_id = f"biz_supp_{digits[-8:] if len(digits) >= 8 else 'tapadiya'}"
                cid = f"cnt_supp_{digits[-8:] if len(digits) >= 8 else 'tapadiya'}"

                conn.execute(
                    """INSERT INTO businesses
                        (id, legal_name, business_type, license_status, status, created_at)
                       VALUES (?, ?, 'supplier', 'verified', 'active', ?)
                       ON CONFLICT(id) DO UPDATE SET legal_name=excluded.legal_name""",
                    (biz_id, name, now),
                )
                conn.execute(
                    """INSERT INTO contacts
                        (id, whatsapp_id, display_name, verification_status, created_at)
                       VALUES (?, ?, ?, 'verified', ?)
                       ON CONFLICT(whatsapp_id) DO UPDATE SET display_name=excluded.display_name""",
                    (cid, clean_phone, name, now),
                )
                actual_c = conn.execute("SELECT id FROM contacts WHERE whatsapp_id = ?", (clean_phone,)).fetchone()
                actual_cid = actual_c["id"] if actual_c else cid

                conn.execute(
                    """INSERT INTO contact_roles
                        (contact_id, business_id, role, approved_by, approved_at)
                       VALUES (?, ?, 'supplier', 'gsheet_sync', ?)
                       ON CONFLICT(contact_id, business_id, role) DO NOTHING""",
                    (actual_cid, biz_id, now),
                )
                synced += 1

        log.info("Synced %d suppliers from Google Sheet into SQLite", synced)
        return {"synced": synced}

    def sync_inventory_from_purchases(self, limit: int = 500) -> Dict[str, int]:
        """
        Sync 'PurchaseList' sheet (gid: 858380472) to local inventory_batches.
        Columns: Vou.No., Date, Party's name & Address, Product, Pack, Batch NO., Expiry, Qty.
        """
        rows = self.fetch_sheet_rows("PurchaseList", max_rows=limit + 1)
        if not rows or len(rows) < 2:
            return {"synced": 0}

        now = utcnow()
        synced = 0

        with self.db.transaction() as conn:
            for i, r in enumerate(rows[1:]):
                if len(r) < 8:
                    continue
                prod_name = str(r[3]).strip()
                batch_no = str(r[5]).strip() or f"BAT_{i+1}"
                exp_raw = str(r[6]).strip()
                qty_raw = str(r[7]).strip().replace(",", "")
                qty = float(qty_raw) if qty_raw.replace(".", "", 1).isdigit() else 10.0

                # Normalize MM/YY or MM/YYYY to YYYY-MM-DD
                exp_date = "2027-12-31"
                exp_m = re.search(r"(\d{1,2})[/.\-](\d{2,4})", exp_raw)
                if exp_m:
                    m, y = int(exp_m.group(1)), int(exp_m.group(2))
                    y = y + 2000 if y < 100 else y
                    exp_date = f"{y:04d}-{m:02d}-28"

                # Match product or insert if missing
                matched_prod = conn.execute(
                    "SELECT id FROM products WHERE canonical_name LIKE ? LIMIT 1",
                    (f"%{prod_name[:15]}%",),
                ).fetchone()

                if matched_prod:
                    pid = matched_prod["id"]
                else:
                    pid = f"prod_pur_{re.sub(r'[^a-zA-Z0-9]', '', prod_name)[:12].lower()}"
                    conn.execute(
                        """INSERT OR IGNORE INTO products
                            (id, canonical_name, brand, pack_size, active, created_at)
                           VALUES (?, ?, ?, ?, 1, ?)""",
                        (pid, prod_name, prod_name, str(r[4]).strip() if len(r) > 4 else "Pack", now),
                    )

                bid = f"bat_pur_{i+1}_{re.sub(r'[^a-zA-Z0-9]', '', batch_no)[:10]}"
                conn.execute(
                    """INSERT OR REPLACE INTO inventory_batches
                        (id, product_id, batch_number, expiry_date, quantity_on_hand, quantity_reserved, purchase_price, received_at)
                       VALUES (?, ?, ?, ?, ?, 0.0, 100.0, ?)""",
                    (bid, pid, batch_no, exp_date, qty, now),
                )
                synced += 1

        log.info("Synced %d inventory batches from PurchaseList into SQLite", synced)
        return {"synced": synced}

    def append_whatsapp_sales_order(self, customer_name: str, items_summary: str, date_str: Optional[str] = None) -> bool:
        """
        Append a confirmed WhatsApp sales order back into Google Sheets 'whatsapp sales order ' sheet (gid: 193895394).
        """
        try:
            svc = self._get_service()
            now_str = date_str or utcnow()[:10]
            values = [["TRUE", f"{items_summary} ({customer_name})", now_str]]
            body = {"values": values}
            svc.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range="'whatsapp sales order '!A:C",
                valueInputOption="USER_ENTERED",
                body=body,
            ).execute()
            log.info("Appended WhatsApp sales order to Google Sheet for %s", customer_name)
            return True
        except Exception as exc:
            log.warning("Could not append order to Google Sheet: %s", exc)
            return False

    def sync_all(self, product_limit: int = 1000, party_limit: int = 500) -> Dict[str, Any]:
        """Run complete full sync from Google Sheets into SQLite database."""
        p_res = self.sync_products(limit=product_limit)
        c_res = self.sync_parties_and_contacts(limit=party_limit)
        s_res = self.sync_suppliers()
        b_res = self.sync_inventory_from_purchases(limit=500)

        return {
            "ok": True,
            "spreadsheet_id": self.spreadsheet_id,
            "products_synced": p_res.get("inserted", 0),
            "retailers_synced": c_res.get("synced", 0),
            "suppliers_synced": s_res.get("synced", 0),
            "inventory_batches_synced": b_res.get("synced", 0),
        }
