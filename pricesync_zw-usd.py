"""
Rate-Price Sync — Automated Retail Pricing in Zimbabwe
============================================================
Automated exchange rate system that improves pricing accuracy in retail.

Architecture:
  - Multi-source system architecture (RateService)
  - Automatic rate retrieval module (RateService._run + threading)
  - Automated pricing engine (PricingEngine)
  - POS/inventory integration hooks (IntegrationBridge)
  - Manager UI with pricing rules (RatePriceSyncApp)
  - Live retail deployment (main + auto-refresh)
  - Performance metrics & evaluation log (MetricsCollector)

Requires: requests, openpyxl, beautifulsoup4
  pip install requests openpyxl beautifulsoup4
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import requests
import json
import csv
import os
import sqlite3
import time
import statistics
import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path

# ─── Optional deps ────────────────────────────────────────
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

# ─── PATHS ───────────────────────────────────────────────
APP_DIR = Path.home() / "RatePriceSyncZW"
APP_DIR.mkdir(exist_ok=True)
DB_PATH    = APP_DIR / "pricesync.db"
LOG_PATH   = APP_DIR / "system_metrics.log"

# ─── COLORS ──────────────────────────────────────────────
BG        = "#0a0f0d"
SURFACE   = "#111814"
SURFACE2  = "#182218"
SURFACE3  = "#1e2d1e"
BORDER    = "#2a3d2a"
ACCENT    = "#4cff91"
ACCENT2   = "#2de07a"
TEXT      = "#e8f5e8"
TEXT2     = "#8aab8a"
TEXT3     = "#4a6b4a"
DANGER    = "#ff6b6b"
WARNING   = "#ffd166"
INFO      = "#74c0fc"
WHITE     = "#ffffff"

FONT_BODY   = ("Segoe UI", 10)
FONT_BOLD   = ("Segoe UI", 10, "bold")
FONT_SMALL  = ("Segoe UI", 9)
FONT_LARGE  = ("Segoe UI", 16, "bold")
FONT_XLARGE = ("Segoe UI", 24, "bold")
FONT_MONO   = ("Consolas", 10)
FONT_TITLE  = ("Segoe UI", 13, "bold")

# ─── METRICS COLLECTOR ───────────────────────────────────
class MetricsCollector:
    """
    Logs rate fetch latency, pricing accuracy events, source availability,
    and system uptime for performance evaluation.
    """
    def __init__(self, log_path=LOG_PATH):
        self.log_path = log_path
        self._latencies   = []
        self._fetch_count = 0
        self._fail_count  = 0
        self._start_time  = datetime.now()

    def record_fetch(self, source: str, latency_ms: float, success: bool):
        self._fetch_count += 1
        if not success:
            self._fail_count += 1
        if success:
            self._latencies.append(latency_ms)
        with open(self.log_path, "a", encoding="utf-8") as f:
            status = "OK" if success else "FAIL"
            f.write(f"{datetime.now().isoformat()}|{source}|{status}|{latency_ms:.0f}ms\n")

    def record_pricing_event(self, product_count: int, rate: float):
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()}|PRICING_UPDATE|products={product_count}|rate={rate:.4f}\n")

    @property
    def availability(self) -> float:
        if self._fetch_count == 0:
            return 100.0
        return round((1 - self._fail_count / self._fetch_count) * 100, 2)

    @property
    def avg_latency_ms(self) -> float:
        return round(statistics.mean(self._latencies), 1) if self._latencies else 0.0

    @property
    def uptime_str(self) -> str:
        delta = datetime.now() - self._start_time
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s   = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def summary(self) -> dict:
        return {
            "uptime":       self.uptime_str,
            "fetch_count":  self._fetch_count,
            "availability": f"{self.availability}%",
            "avg_latency":  f"{self.avg_latency_ms} ms",
            "fail_count":   self._fail_count,
        }


# ─── PRICING ENGINE ──────────────────────────────────────
class PricingEngine:
    """
    Automated pricing engine: converts USD prices into ZWG using
    live rates and configurable margin rules. Supports tiered margins,
    category overrides, and rounding strategies.
    """
    ROUNDING_NONE     = "none"
    ROUNDING_NEAREST5 = "nearest_5"
    ROUNDING_CEIL10   = "ceil_10"

    def __init__(self):
        self.global_margin   = 10.0
        self.category_margins = {}           # e.g. {"Pharmacy": 5.0}
        self.rounding_mode   = self.ROUNDING_NONE
        self.markup_type     = "percentage"  # "percentage" | "fixed"

    def zwg_price(self, usd: float, rate: float, category: str = "", margin: float = None) -> float:
        if margin is None:
            margin = self.category_margins.get(category, self.global_margin)
        base = usd * rate
        if self.markup_type == "percentage":
            priced = base * (1 + margin / 100)
        else:
            priced = base + margin
        return self._apply_rounding(priced)

    def _apply_rounding(self, value: float) -> float:
        if self.rounding_mode == self.ROUNDING_NEAREST5:
            return round(value / 5) * 5
        elif self.rounding_mode == self.ROUNDING_CEIL10:
            import math
            return math.ceil(value / 10) * 10
        return round(value, 2)

    def bulk_price(self, products: list, rate: float) -> list:
        """Returns list of (product_row, zwg_base, zwg_with_margin) tuples."""
        results = []
        for p in products:
            base  = p["usd_price"] * rate
            final = self.zwg_price(p["usd_price"], rate, p["category"], p["margin"])
            results.append((p, round(base, 2), final))
        return results


# ─── INTEGRATION BRIDGE ──────────────────────────────────
class IntegrationBridge:
    """
    POS / Inventory integration: exposes a simple interface for
    pushing updated prices to external systems via webhook or file drop.
    Retailers can plug in their POS endpoint (e.g. Pastel, Sage, custom REST).
    """
    def __init__(self):
        self.pos_webhook_url = ""   # e.g. http://localhost:8080/api/prices
        self.export_dir      = str(APP_DIR / "pos_sync")
        os.makedirs(self.export_dir, exist_ok=True)

    def push_to_pos(self, price_data: list, rate: float) -> dict:
        """Attempt HTTP POST to configured POS webhook."""
        if not self.pos_webhook_url:
            return {"status": "skipped", "reason": "No webhook configured"}
        payload = {
            "timestamp": datetime.now().isoformat(),
            "rate_usd_zwg": rate,
            "products": [
                {"id": p["id"], "name": p["name"], "zwg_price": zwg_m}
                for p, _, zwg_m in price_data
            ]
        }
        try:
            r = requests.post(self.pos_webhook_url, json=payload, timeout=5)
            return {"status": "ok", "http_code": r.status_code}
        except Exception as e:
            return {"status": "error", "reason": str(e)}

    def write_sync_file(self, price_data: list, rate: float):
        """Write a JSON sync file for inventory systems to poll."""
        out = APP_DIR / "pos_sync" / f"sync_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        payload = {
            "generated": datetime.now().isoformat(),
            "rate": rate,
            "products": [
                {"id": p["id"], "name": p["name"],
                 "usd": p["usd_price"], "zwg": zwg_m, "category": p["category"]}
                for p, _, zwg_m in price_data
            ]
        }
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return str(out)


# ─── DATABASE ────────────────────────────────────────────
class Database:
    def __init__(self):
        self.conn = sqlite3.connect(str(DB_PATH))
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        c = self.conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT DEFAULT 'General',
                usd_price REAL NOT NULL,
                margin REAL DEFAULT 10,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS rate_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rate REAL NOT NULL,
                source TEXT DEFAULT 'live',
                fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pricing_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL UNIQUE,
                margin REAL DEFAULT 10,
                rounding TEXT DEFAULT 'none'
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_login TEXT,
                failed_attempts INTEGER DEFAULT 0,
                lockout_until TEXT DEFAULT NULL,
                force_password_change INTEGER DEFAULT 0,
                suspended INTEGER DEFAULT 0
            )
        """)
        # Migrate existing db: add new columns if they don't exist
        for col, defval in [
            ("failed_attempts",      "INTEGER DEFAULT 0"),
            ("lockout_until",        "TEXT DEFAULT NULL"),
            ("force_password_change","INTEGER DEFAULT 0"),
            ("suspended",            "INTEGER DEFAULT 0"),
        ]:
            try:
                c.execute(f"ALTER TABLE users ADD COLUMN {col} {defval}")
            except Exception:
                pass
        c.execute("""
            CREATE TABLE IF NOT EXISTS pending_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                requested_at TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending'
            )
        """)
        self.conn.commit()
        self._seed_admin()
        self._seed_products()

    @staticmethod
    def hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def _seed_admin(self):
        c = self.conn.cursor()
        new_hash = self.hash_password("Project@26")
        # Migrate old "admini" username to "admin" AND update password
        old = c.execute("SELECT id FROM users WHERE username=?", ("admini",)).fetchone()
        if old:
            try:
                c.execute(
                    "UPDATE users SET username='admin', password_hash=?, failed_attempts=0, lockout_until=NULL WHERE username='admini'",
                    (new_hash,)
                )
                self.conn.commit()
                return
            except Exception:
                pass
        exists = c.execute("SELECT id FROM users WHERE username=?", ("admin",)).fetchone()
        if not exists:
            c.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?,?,?)",
                ("admin", new_hash, "admin")
            )
            self.conn.commit()

    def verify_user(self, username: str, password: str):
        """Returns user dict if valid, else None. Handles lockout and attempt tracking."""
        c = self.conn.cursor()
        row = c.execute(
            """SELECT id, username, password_hash, role, is_active,
                      failed_attempts, lockout_until, force_password_change, suspended
               FROM users WHERE username=?""",
            (username,)
        ).fetchone()
        if not row:
            return None
        if not row["is_active"] or row["suspended"]:
            return "suspended"
        # Check lockout
        if row["lockout_until"]:
            lockout_dt = datetime.strptime(row["lockout_until"], "%Y-%m-%d %H:%M:%S")
            if datetime.now() < lockout_dt:
                remaining = int((lockout_dt - datetime.now()).total_seconds() // 60) + 1
                return {"locked": True, "minutes": remaining}
            else:
                # Lockout expired — reset
                c.execute("UPDATE users SET failed_attempts=0, lockout_until=NULL WHERE id=?",
                          (row["id"],))
                self.conn.commit()
        if row["password_hash"] != self.hash_password(password):
            attempts = row["failed_attempts"] + 1
            if attempts >= 4:
                lockout_time = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
                c.execute("UPDATE users SET failed_attempts=?, lockout_until=? WHERE id=?",
                          (attempts, lockout_time, row["id"]))
            else:
                c.execute("UPDATE users SET failed_attempts=? WHERE id=?",
                          (attempts, row["id"]))
            self.conn.commit()
            return {"bad_password": True, "attempts": attempts}
        # Successful login — reset attempts
        c.execute("""UPDATE users SET last_login=?, failed_attempts=0, lockout_until=NULL
                     WHERE username=?""",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), username))
        self.conn.commit()
        return {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "force_password_change": bool(row["force_password_change"]),
        }

    def get_users(self):
        c = self.conn.cursor()
        return c.execute(
            """SELECT id, username, role, is_active, created_at, last_login,
                      force_password_change, suspended
               FROM users ORDER BY id"""
        ).fetchall()

    def add_user(self, username: str, password: str, role: str = "user") -> bool:
        try:
            c = self.conn.cursor()
            c.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?,?,?)",
                (username, self.hash_password(password), role)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def update_user_password(self, uid: int, new_password: str, force_change: bool = False):
        c = self.conn.cursor()
        c.execute("UPDATE users SET password_hash=?, force_password_change=? WHERE id=?",
                  (self.hash_password(new_password), 1 if force_change else 0, uid))
        self.conn.commit()

    def clear_force_password_change(self, uid: int):
        c = self.conn.cursor()
        c.execute("UPDATE users SET force_password_change=0 WHERE id=?", (uid,))
        self.conn.commit()

    def reset_password_to_changeme(self, uid: int):
        """Admin resets a user's password to ChangeMe and forces change on next login."""
        c = self.conn.cursor()
        c.execute("UPDATE users SET password_hash=?, force_password_change=1 WHERE id=?",
                  (self.hash_password("ChangeMe"), uid))
        self.conn.commit()

    def suspend_user(self, uid: int, suspend: bool):
        c = self.conn.cursor()
        c.execute("UPDATE users SET suspended=? WHERE id=?", (1 if suspend else 0, uid))
        self.conn.commit()

    def toggle_user_active(self, uid: int):
        c = self.conn.cursor()
        c.execute("UPDATE users SET is_active = CASE WHEN is_active=1 THEN 0 ELSE 1 END WHERE id=?", (uid,))
        self.conn.commit()

    def delete_user(self, uid: int):
        c = self.conn.cursor()
        c.execute("DELETE FROM users WHERE id=? AND username != 'admin'", (uid,))
        self.conn.commit()

    # ── Pending users (account requests) ─────────────────
    def add_pending_user(self, username: str, password: str) -> bool:
        try:
            c = self.conn.cursor()
            # Check not already a real user
            if c.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
                return False
            c.execute(
                "INSERT OR REPLACE INTO pending_users (username, password_hash, status) VALUES (?,?,?)",
                (username, self.hash_password(password), "pending")
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_pending_users(self):
        c = self.conn.cursor()
        return c.execute(
            "SELECT id, username, requested_at, status FROM pending_users WHERE status='pending' ORDER BY requested_at"
        ).fetchall()

    def approve_pending_user(self, pending_id: int) -> bool:
        c = self.conn.cursor()
        row = c.execute("SELECT username, password_hash FROM pending_users WHERE id=?",
                        (pending_id,)).fetchone()
        if not row:
            return False
        try:
            c.execute("INSERT INTO users (username, password_hash, role) VALUES (?,?,?)",
                      (row["username"], row["password_hash"], "user"))
            c.execute("UPDATE pending_users SET status='approved' WHERE id=?", (pending_id,))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            c.execute("UPDATE pending_users SET status='approved' WHERE id=?", (pending_id,))
            self.conn.commit()
            return False

    def decline_pending_user(self, pending_id: int):
        c = self.conn.cursor()
        c.execute("UPDATE pending_users SET status='declined' WHERE id=?", (pending_id,))
        self.conn.commit()

    def _seed_products(self):
        c = self.conn.cursor()
        count = c.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if count < 149:
            # Clear stale/partial data from older version before re-seeding
            c.execute("DELETE FROM products")
            self.conn.commit()
        if c.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            defaults = [
                # ── Fuel & Automotive (ZERA regulated) ──────────────────
                ("Petrol (E20 Blend, per Litre)",        "Fuel & Automotive",  1.65, 5),
                ("Diesel (D50, per Litre)",               "Fuel & Automotive",  1.68, 5),
                ("LPG Gas (per kg)",                      "Fuel & Automotive",  1.56, 5),
                ("Engine Oil (Castrol GTX, 5L)",          "Fuel & Automotive", 28.00, 8),
                ("Engine Oil (Shell Helix, 5L)",          "Fuel & Automotive", 32.00, 8),
                ("Brake Fluid (Dot 4, 500ml)",            "Fuel & Automotive",  4.50, 8),
                ("Antifreeze/Coolant (1L)",               "Fuel & Automotive",  3.80, 8),
                ("Car Battery (Exide 619)",               "Fuel & Automotive", 65.00, 8),
                ("Car Battery (Exide 652)",               "Fuel & Automotive", 95.00, 8),
                ("Tyres (175/70/R13 - Budget)",           "Fuel & Automotive", 35.00, 10),
                ("Tyres (205/55/R16 - Mid-range)",        "Fuel & Automotive", 65.00, 10),
                # ── Basic Staples & Grains ───────────────────────────────
                ("Sugar (Gold Star White, 2kg)",          "Groceries",  2.85, 10),
                ("Sugar (Huletts Brown, 2kg)",            "Groceries",  2.85, 10),
                ("Mealie Meal (Roller Meal, 10kg)",       "Groceries",  5.40, 10),
                ("Mealie Meal (Pearlenta, 10kg)",         "Groceries",  8.30, 10),
                ("Mealie Meal (Ngwerewere, 10kg)",        "Groceries",  7.95, 10),
                ("Flour (Gloria Self-Raising, 2kg)",      "Groceries",  2.09, 10),
                ("Flour (Blue Ribbon Cake, 2kg)",         "Groceries",  1.95, 10),
                ("Rice (Mahatma, 2kg)",                   "Groceries",  2.80, 10),
                ("Rice (Red Seal Thai Long Grain, 2kg)",  "Groceries",  2.45, 10),
                ("Rice (Mama Africa, 2kg)",               "Groceries",  2.10, 10),
                ("Rice (Basmati, 1kg)",                   "Groceries",  3.20, 10),
                ("Spaghetti (Ekono, 400g)",               "Groceries",  0.50, 10),
                ("Pasta (Santa Lucia Fusilli, 500g)",     "Groceries",  1.10, 10),
                ("Macaroni (Red Seal, 500g)",             "Groceries",  0.95, 10),
                ("Sugar Beans (Red Seal, 500g)",          "Groceries",  1.50, 10),
                ("Popcorn (Red Seal, 500g)",              "Groceries",  0.85, 10),
                ("Table Salt (Red Seal, 2kg)",            "Groceries",  0.95, 10),
                ("Soya Chunks (Pro-Soya, 250g)",          "Groceries",  0.80, 10),
                # ── Oils, Fats & Dairy ───────────────────────────────────
                ("Cooking Oil (Raha, 2L)",                "Oils & Dairy",  3.15, 10),
                ("Cooking Oil (Zimgold, 2L)",             "Oils & Dairy",  3.25, 10),
                ("Cooking Oil (Olivine, 2L)",             "Oils & Dairy",  3.40, 10),
                ("Margarine (Jade, 500g)",                "Oils & Dairy",  1.65, 10),
                ("Margarine (Buttercup, 500g)",           "Oils & Dairy",  2.10, 10),
                ("Cooking Fat (Holsum, 500g)",            "Oils & Dairy",  1.45, 10),
                ("Fresh Milk (Dairibord, 1L)",            "Oils & Dairy",  1.40, 10),
                ("Long Life Milk (Dendairy, 1L)",         "Oils & Dairy",  1.45, 10),
                ("Sour Milk (Lacto, 500ml)",              "Oils & Dairy",  0.65, 10),
                ("Full Cream Milk (Chimombe, 1L)",        "Oils & Dairy",  1.55, 10),
                ("Cheddar Cheese (Kefalos, per kg)",      "Oils & Dairy", 11.50, 12),
                ("Gouda Cheese (Kefalos, per kg)",        "Oils & Dairy", 12.50, 12),
                ("Mozzarella (Kefalos, 500g)",            "Oils & Dairy",  6.80, 12),
                ("Eggs (Large, 30 pack)",                 "Oils & Dairy",  4.80, 10),
                ("Yoghurt (Dairibord Fruit Tree, 500g)",  "Oils & Dairy",  1.85, 10),
                # ── Butchery & Poultry ───────────────────────────────────
                ("Whole Chicken (Frozen, 1.4kg)",         "Butchery",  5.50, 12),
                ("Chicken Breasts (Fillets)",             "Butchery",  7.20, 12),
                ("Chicken Wings",                         "Butchery",  4.80, 12),
                ("Chicken Drumsticks",                    "Butchery",  5.10, 12),
                ("Chicken Gizzards",                      "Butchery",  3.20, 12),
                ("Beef Economy Blade",                    "Butchery",  6.50, 12),
                ("Beef Brisket",                          "Butchery",  5.80, 12),
                ("Beef Chuck",                            "Butchery",  6.80, 12),
                ("Beef T-Bone",                           "Butchery",  9.50, 12),
                ("Beef Fillet",                           "Butchery", 12.50, 12),
                ("Beef Mince (Standard)",                 "Butchery",  6.20, 12),
                ("Beef Mince (Lean/Topside)",             "Butchery",  8.50, 12),
                ("Pork Chops",                            "Butchery",  7.40, 12),
                ("Pork Sausages (Colcom, 500g)",          "Butchery",  3.80, 12),
                ("Beef Sausages (Standard, 500g)",        "Butchery",  3.50, 12),
                ("Bacon (Colcom, 250g)",                  "Butchery",  3.20, 12),
                ("French Polony (Colcom, 500g)",          "Butchery",  2.40, 12),
                ("Garlic Polony (Colcom, 500g)",          "Butchery",  2.60, 12),
                ("Boerewors (Beef)",                      "Butchery",  7.50, 12),
                ("Goat Meat",                             "Butchery",  7.00, 12),
                # ── Pharmacy & Medicine ──────────────────────────────────
                ("Paracetamol (Panado, 20s)",             "Pharmacy",  1.50, 5),
                ("Ibuprofen (400mg, 10s)",                "Pharmacy",  2.00, 5),
                ("Aspirin (Disprin, 24s)",                "Pharmacy",  2.50, 5),
                ("Cough Syrup (Benylin, 100ml)",          "Pharmacy",  4.50, 5),
                ("Antacid (Eno Sachet)",                  "Pharmacy",  0.50, 5),
                ("Antacid (Gaviscon Liquid, 200ml)",      "Pharmacy",  8.50, 5),
                ("Vitamin C (1000mg Effervescent, 10s)",  "Pharmacy",  3.50, 5),
                ("Multivitamins (Centrum, 30s)",          "Pharmacy", 12.00, 5),
                ("Co-trimoxazole (Antibiotic, 10s)",      "Pharmacy",  2.50, 5),
                ("Amoxicillin (500mg, 10s)",              "Pharmacy",  3.00, 5),
                ("Blood Pressure Meds (Amlodipine 5mg)",  "Pharmacy",  5.00, 5),
                ("Antimalarial (Coartem, 24s)",           "Pharmacy",  8.00, 5),
                ("Band-Aids (Plasters, 20 pack)",         "Pharmacy",  1.00, 5),
                ("Cotton Wool (100g)",                    "Pharmacy",  1.20, 5),
                ("Surgical Spirit (100ml)",               "Pharmacy",  1.50, 5),
                # ── Toiletries & Personal Care ───────────────────────────
                ("Bath Soap (Geisha, 225g)",              "Toiletries",  0.95, 10),
                ("Bath Soap (Jade, 250g)",                "Toiletries",  0.85, 10),
                ("Bath Soap (Lifebuoy, 175g)",            "Toiletries",  1.10, 10),
                ("Bath Soap (Lux, 175g)",                 "Toiletries",  1.25, 10),
                ("Toothpaste (Colgate, 100ml)",           "Toiletries",  1.20, 10),
                ("Toothpaste (Aquafresh, 100ml)",         "Toiletries",  1.10, 10),
                ("Toothbrush (Dr. Best / Colgate)",       "Toiletries",  0.80, 10),
                ("Shaving Cream (Gillette, 200ml)",       "Toiletries",  3.50, 10),
                ("Disposable Razors (Bic 3-pack)",        "Toiletries",  1.50, 10),
                ("Deodorant (Shield Roll-on, 50ml)",      "Toiletries",  1.35, 10),
                ("Body Spray (Axe/Playboy, 150ml)",       "Toiletries",  2.80, 10),
                ("Body Lotion (Vaseline, 400ml)",         "Toiletries",  3.20, 10),
                ("Petroleum Jelly (Vaseline Blue Seal)",  "Toiletries",  1.80, 10),
                ("Shampoo (Organics, 400ml)",             "Toiletries",  3.50, 10),
                ("Conditioner (Organics, 400ml)",         "Toiletries",  3.50, 10),
                ("Sanitary Pads (Stayfree, 10s)",         "Toiletries",  1.15, 10),
                ("Sanitary Pads (Always Ultra, 8s)",      "Toiletries",  2.10, 10),
                ("Toilet Paper (Softly, 4 pack)",         "Toiletries",  1.80, 10),
                ("Toilet Paper (Baby Soft, 9 pack)",      "Toiletries",  5.50, 10),
                # ── Cleaning Agents ──────────────────────────────────────
                ("Washing Powder (Boom, 500g)",           "Cleaning",  1.10, 10),
                ("Washing Powder (Maq, 2kg)",             "Cleaning",  4.50, 10),
                ("Washing Powder (Ariel, 2kg)",           "Cleaning",  6.20, 10),
                ("Laundry Soap (Perfection Bar)",         "Cleaning",  0.90, 10),
                ("Dishwashing Liquid (Sunlight, 750ml)",  "Cleaning",  2.20, 10),
                ("All Purpose Cleaner (Handy Andy)",      "Cleaning",  2.10, 10),
                ("Bleach (Jik, 750ml)",                   "Cleaning",  1.65, 10),
                ("Fabric Softener (Sta-Soft, 2L)",        "Cleaning",  4.80, 10),
                ("Floor Polish (Cobra, 350ml)",           "Cleaning",  2.50, 10),
                ("Toilet Cleaner (Harpic, 500ml)",        "Cleaning",  2.40, 10),
                ("Scouring Powder (Vim, 500g)",           "Cleaning",  1.20, 10),
                # ── Beverages & Alcohol ──────────────────────────────────
                ("Beer (Zambezi Lager, 330ml can)",       "Beverages",  0.80, 15),
                ("Beer (Castle Lager, 375ml bottle)",     "Beverages",  0.90, 15),
                ("Beer (Golden Pilsener, 330ml)",         "Beverages",  0.85, 15),
                ("Beer (Heineken, 330ml)",                "Beverages",  1.50, 15),
                ("Cider (Savanna Dry, 330ml)",            "Beverages",  1.40, 15),
                ("Whiskey (Jameson, 750ml)",              "Beverages", 24.00, 15),
                ("Whiskey (Johnnie Walker Red, 750ml)",   "Beverages", 18.00, 15),
                ("Gin (Gordon's London Dry, 750ml)",      "Beverages", 14.00, 15),
                ("Vodka (Smirnoff, 750ml)",               "Beverages", 12.00, 15),
                ("Wine (4th Street Sweet Red, 750ml)",    "Beverages",  4.50, 15),
                ("Wine (Nederburg Merlot, 750ml)",        "Beverages",  9.00, 15),
                ("Soft Drink (Coke/Fanta, 2L)",           "Beverages",  1.95, 12),
                ("Soft Drink (Pepsi, 500ml)",             "Beverages",  0.55, 12),
                ("Fruit Juice (Ceres, 1L)",               "Beverages",  2.10, 12),
                ("Mineral Water (500ml)",                 "Beverages",  0.25, 12),
                # ── Hardware & Construction ──────────────────────────────
                ("Cement (PC 32.5, 50kg)",                "Hardware",   9.50, 8),
                ("Cement (MC 42.5, 50kg)",                "Hardware",  10.80, 8),
                ("Brick Force (150mm)",                   "Hardware",   2.50, 8),
                ("Common Bricks (per 1000)",              "Hardware",  80.00, 8),
                ("Face Bricks (per 1000)",                "Hardware", 140.00, 8),
                ("River Sand (per Cubic Meter)",          "Hardware",  15.00, 8),
                ("Pit Sand (per Cubic Meter)",            "Hardware",  12.00, 8),
                ("Timber (38x114 Treated, 6m)",           "Hardware",  12.50, 8),
                ("Roofing Sheets (IBR, 0.4mm, per m)",    "Hardware",   6.50, 8),
                ("Door Frame (Steel, Standard)",          "Hardware",  22.00, 8),
                ("Window Frame (NC4)",                    "Hardware",  18.00, 8),
                # ── Vegetables & Fruits ──────────────────────────────────
                ("Potatoes (10kg Pocket)",                "Produce",  6.00, 15),
                ("Tomatoes (Small Crate)",                "Produce",  4.50, 15),
                ("Onions (10kg Pocket)",                  "Produce",  7.00, 15),
                ("Cabbage (Large Head)",                  "Produce",  1.00, 15),
                ("Bananas (per kg)",                      "Produce",  0.90, 15),
                ("Apples (Red, 1.5kg bag)",               "Produce",  2.50, 15),
                ("Carrots (Bundle)",                      "Produce",  0.80, 15),
                ("Garlic (per 100g)",                     "Produce",  1.00, 15),
                ("Ginger (per 100g)",                     "Produce",  0.85, 15),
                # ── Snacks & Confectionery ───────────────────────────────
                ("Willards Things (150g)",                "Snacks",  1.15, 12),
                ("Willards Jupiters (150g)",              "Snacks",  1.10, 12),
                ("Simba Chips (125g)",                    "Snacks",  1.85, 12),
                ("Charhons Biscuits (150g)",              "Snacks",  0.75, 12),
                ("Chocolate (Cadbury, 80g)",              "Snacks",  1.65, 12),
            ]
            c.executemany(
                "INSERT INTO products (name, category, usd_price, margin) VALUES (?,?,?,?)",
                defaults
            )
            self.conn.commit()

    def get_products(self, search="", category=""):
        c = self.conn.cursor()
        q = "SELECT * FROM products WHERE 1=1"
        params = []
        if search:
            q += " AND (name LIKE ? OR category LIKE ?)"
            params += [f"%{search}%", f"%{search}%"]
        if category and category not in ("All", ""):
            q += " AND category = ?"
            params.append(category)
        q += " ORDER BY category, name"
        return c.execute(q, params).fetchall()

    def add_product(self, name, category, usd_price, margin):
        c = self.conn.cursor()
        c.execute("INSERT INTO products (name, category, usd_price, margin) VALUES (?,?,?,?)",
                  (name, category, usd_price, margin))
        self.conn.commit()
        return c.lastrowid

    def update_product(self, pid, name, category, usd_price, margin):
        c = self.conn.cursor()
        c.execute("UPDATE products SET name=?, category=?, usd_price=?, margin=? WHERE id=?",
                  (name, category, usd_price, margin, pid))
        self.conn.commit()

    def delete_product(self, pid):
        c = self.conn.cursor()
        c.execute("DELETE FROM products WHERE id=?", (pid,))
        self.conn.commit()

    def get_categories(self):
        c = self.conn.cursor()
        rows = c.execute("SELECT DISTINCT category FROM products ORDER BY category").fetchall()
        return [r[0] for r in rows]

    def save_rate(self, rate, source, timestamp: datetime = None):
        c = self.conn.cursor()
        ts = (timestamp or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO rate_history (rate, source, fetched_at) VALUES (?,?,?)",
                  (rate, source, ts))
        self.conn.commit()

    def get_rate_history(self, limit=100):
        c = self.conn.cursor()
        return c.execute(
            "SELECT * FROM rate_history ORDER BY fetched_at DESC LIMIT ?", (limit,)
        ).fetchall()

    def clear_products(self):
        self.conn.execute("DELETE FROM products")
        self.conn.commit()

    def clear_history(self):
        self.conn.execute("DELETE FROM rate_history")
        self.conn.commit()

    def close(self):
        self.conn.close()


# ─── RATE SERVICE (Multi-source architecture) ────────────
class RateResult:
    """Full rate payload: mid, bid, ask, source, percent change."""
    def __init__(self, mid, bid=None, ask=None, source="unknown",
                 pct_change=None, currency="ZWG", latency_ms=0.0):
        self.mid        = round(mid, 4)
        self.bid        = round(bid, 4)  if bid  else mid
        self.ask        = round(ask, 4)  if ask  else mid
        self.source     = source
        self.pct_change = pct_change
        self.currency   = currency
        self.latency_ms = latency_ms
        self.fetched_at = datetime.now()

    @property
    def spread(self):
        return round(self.ask - self.bid, 4)


class RateService:
    """
    Multi-source system architecture: integrates multiple real-time exchange
    rate sources in a prioritised failover chain. Each source is tried in
    order; on failure the next source is attempted. All calls are non-blocking
    (daemon thread).

    Source priority:
      1. ZimRate API         — rbz-sourced daily rates (zimrate.statotec.com)
      2. RBZ GitHub API      — scraped from rbz.co.zw PDF (brendmung vercel)
      3. RBZ Website scrape  — direct parse of rbz.co.zw exchange rate page
      4. ZimPriceCheck       — community aggregated rates (zimpricecheck.com)
      5. Estimated fallback  — last known rate or hard-coded baseline

    Reference / price intelligence sources (not rate APIs — used for
    category-level price benchmarking):
      - ZERA (zera.co.zw)              — regulated fuel prices
      - TMPNP Online (tmpnponline.co.zw)
      - Halsteds (halsteds.co.zw)
      - Electrosales (electrosales.co.zw)
      - ZimStat (zimstat.co.zw)        — CPI / inflation data
      - Greenwood Pharmacy
    """
    # ── Rate API endpoints ────────────────────────────────
    ZIMRATE_URL     = "https://zimrate.statotec.com/api/v1/rates"
    RBZ_GITHUB_URL  = "https://rbz-exchange-rates-api.vercel.app/api/rates"
    RBZ_WEBSITE_URL = "https://www.rbz.co.zw/index.php/research/markets/exchange-rates"
    ZIMPRICECHECK_URL = "https://zimpricecheck.com/api/exchange-rate"   # if public endpoint exists

    # ── Reference / price intelligence sources ───────────
    REFERENCE_SOURCES = {
        "ZERA (Fuel Prices)":        "https://www.zera.co.zw/",
        "TMPNP Online":              "https://www.tmpnponline.co.zw/",
        "ZimPriceCheck":             "https://zimpricecheck.com/",
        "Halsteds Hardware":         "https://www.halsteds.co.zw/",
        "Electrosales":              "https://www.electrosales.co.zw/",
        "ZimStat (CPI/Inflation)":   "https://www.zimstat.co.zw/",
        "Greenwood Pharmacy":        "http://www.greenwoodpharmacy.co.zw/",
    }

    FALLBACK_RATE = 25.30    # USD/ZWG baseline (March 2026)

    def fetch(self, on_success, on_error):
        """Non-blocking rate retrieval via daemon thread."""
        threading.Thread(
            target=self._run, args=(on_success, on_error), daemon=True
        ).start()

    def _run(self, on_success, on_error):
        # ── Source 1: ZimRate API ─────────────────────────
        result = self._try_zimrate()
        if result:
            on_success(result)
            return

        # ── Source 2: RBZ GitHub API ──────────────────────
        result = self._try_rbz_github()
        if result:
            on_success(result)
            return

        # ── Source 3: RBZ Website scrape ──────────────────
        result = self._try_rbz_website()
        if result:
            on_success(result)
            return

        # ── Source 4: ZimPriceCheck ───────────────────────
        result = self._try_zimpricecheck()
        if result:
            on_success(result)
            return

        # ── Source 5: Estimated fallback ──────────────────
        result = RateResult(self.FALLBACK_RATE, source="Estimated (offline — all sources failed)")
        on_error(result)

    def _try_zimrate(self) -> "RateResult | None":
        try:
            t0 = time.time()
            r  = requests.get(self.ZIMRATE_URL, params={"pair": "USD/ZWG"}, timeout=10)
            r.raise_for_status()
            latency = (time.time() - t0) * 1000
            data    = r.json()
            rates_list = data.get("data", {}).get("rates", [])
            if rates_list:
                entry = rates_list[0]
                mid   = float(entry.get("avg") or entry.get("mid") or entry.get("rate"))
                bid   = float(entry.get("bid", mid))
                ask   = float(entry.get("ask", mid))
                pct   = entry.get("percent_change") or entry.get("change")
                return RateResult(mid, bid, ask, "ZimRate (RBZ-sourced)", pct, latency_ms=latency)
        except Exception:
            return None

    def _try_rbz_github(self) -> "RateResult | None":
        try:
            t0 = time.time()
            r  = requests.get(self.RBZ_GITHUB_URL, params={"currency": "USD"}, timeout=10)
            r.raise_for_status()
            latency = (time.time() - t0) * 1000
            data    = r.json()
            usd     = data["rates"]["USD"]
            mid     = float(usd.get("avg") or usd.get("mid"))
            bid     = float(usd.get("bid", mid))
            ask     = float(usd.get("ask", mid))
            pct     = usd.get("percent_change")
            return RateResult(mid, bid, ask, "RBZ GitHub API (rbz.co.zw)", pct, latency_ms=latency)
        except Exception:
            return None

    def _try_rbz_website(self) -> "RateResult | None":
        """Scrape the RBZ exchange rates page directly."""
        if not BS4_AVAILABLE:
            return None
        try:
            t0      = time.time()
            headers = {"User-Agent": "Mozilla/5.0 (RatePriceSyncZW/1.0)"}
            r       = requests.get(self.RBZ_WEBSITE_URL, headers=headers, timeout=12)
            r.raise_for_status()
            latency = (time.time() - t0) * 1000
            soup    = BeautifulSoup(r.text, "html.parser")
            # RBZ tables typically have currency codes in td cells; look for ZWG row
            for row in soup.find_all("tr"):
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) >= 3 and "USD" in cells[0]:
                    try:
                        mid = float(cells[1].replace(",", ""))
                        return RateResult(mid, source="RBZ Website (rbz.co.zw)", latency_ms=latency)
                    except ValueError:
                        continue
        except Exception:
            pass
        return None

    def _try_zimpricecheck(self) -> "RateResult | None":
        """ZimPriceCheck community aggregated rate."""
        try:
            t0 = time.time()
            r  = requests.get(self.ZIMPRICECHECK_URL, timeout=8)
            r.raise_for_status()
            latency = (time.time() - t0) * 1000
            data    = r.json()
            mid     = float(data.get("rate") or data.get("usd_zwg") or data["mid"])
            return RateResult(mid, source="ZimPriceCheck (community)", latency_ms=latency)
        except Exception:
            return None

    def fetch_zera_fuel_prices(self) -> dict:
        """
        Reference source — ZERA regulated fuel prices.
        Returns dict of fuel type → USD price, or empty dict on failure.
        """
        if not BS4_AVAILABLE:
            return {}
        try:
            headers = {"User-Agent": "Mozilla/5.0 (RatePriceSyncZW/1.0)"}
            r       = requests.get("https://www.zera.co.zw/", headers=headers, timeout=10)
            soup    = BeautifulSoup(r.text, "html.parser")
            # Parse ZERA fuel price tables — structure may vary
            prices  = {}
            for row in soup.find_all("tr"):
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) >= 2 and any(k in cells[0].upper() for k in ["PETROL","DIESEL","LPG"]):
                    try:
                        prices[cells[0]] = float(cells[1].replace("$","").replace(",",""))
                    except ValueError:
                        pass
            return prices
        except Exception:
            return {}


# ─── STYLED WIDGETS ──────────────────────────────────────
def make_frame(parent, **kw):
    kw.setdefault("bg", SURFACE)
    return tk.Frame(parent, **kw)

def make_label(parent, text, fg=TEXT, font=FONT_BODY, bg=None, **kw):
    bg = bg or parent.cget("bg")
    return tk.Label(parent, text=text, fg=fg, bg=bg, font=font, **kw)

def make_button(parent, text, command, bg=SURFACE3, fg=TEXT, font=FONT_BODY, **kw):
    return tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                     font=font, relief="flat", cursor="hand2",
                     activebackground=SURFACE2, activeforeground=ACCENT,
                     padx=12, pady=6, **kw)

def make_accent_button(parent, text, command, **kw):
    return tk.Button(parent, text=text, command=command, bg=ACCENT, fg="#001a06",
                     font=FONT_BOLD, relief="flat", cursor="hand2",
                     activebackground=ACCENT2, activeforeground="#001a06",
                     padx=14, pady=7, **kw)

def make_entry(parent, textvariable=None, width=20, **kw):
    kw.setdefault("bg", SURFACE2)
    kw.setdefault("fg", TEXT)
    kw.setdefault("insertbackground", ACCENT)
    kw.setdefault("relief", "flat")
    kw.setdefault("font", FONT_MONO)
    kw.setdefault("highlightthickness", 1)
    kw.setdefault("highlightbackground", BORDER)
    kw.setdefault("highlightcolor", ACCENT)
    return tk.Entry(parent, textvariable=textvariable, width=width, **kw)

def styled_treeview(parent):
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Dark.Treeview",
        background=SURFACE2, foreground=TEXT2,
        fieldbackground=SURFACE2, rowheight=28,
        font=FONT_BODY, borderwidth=0
    )
    style.configure("Dark.Treeview.Heading",
        background=SURFACE3, foreground=TEXT3,
        font=("Segoe UI", 9, "bold"), relief="flat", borderwidth=0
    )
    style.map("Dark.Treeview",
        background=[("selected", SURFACE3)],
        foreground=[("selected", ACCENT)]
    )
    return style


# ─── LOGIN APPLICATION ───────────────────────────────────
DEFAULT_OTP = "343434"

class LoginApp(tk.Tk):
    """Standalone login window with OTP, lockout, account creation & forgot password."""

    def __init__(self):
        super().__init__()
        self.title("Rate-Price Sync — Login")
        self.geometry("480x620")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self._db = Database()
        self._build_ui()
        self._center()

    def _center(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x  = (sw - 480) // 2
        y  = (sh - 620) // 2
        self.geometry(f"480x620+{x}+{y}")

    def _build_ui(self):
        # ── Top brand bar ──────────────────────────────────
        bar = tk.Frame(self, bg="#ffffff", padx=20, pady=12)
        bar.pack(fill="x")
        make_label(bar, "Rate-Price Sync",
                   fg="#cc0000", bg="#ffffff",
                   font=("Segoe UI", 16, "bold")).pack(anchor="w")
        make_label(bar, "Automated Retail Pricing in Zimbabwe",
                   fg="#444444", bg="#ffffff",
                   font=("Segoe UI", 8, "bold")).pack(anchor="w")

        # ── Tab switcher ──────────────────────────────────
        tab_bar = tk.Frame(self, bg=SURFACE2)
        tab_bar.pack(fill="x")
        self._tab_btns = {}
        for key, label in [("signin", "Sign In"), ("register", "Create Account")]:
            btn = tk.Button(tab_bar, text=label, font=("Segoe UI", 9, "bold"),
                            relief="flat", cursor="hand2", padx=18, pady=8,
                            bg=SURFACE2, fg=TEXT3,
                            activebackground=SURFACE3, activeforeground=ACCENT,
                            command=lambda k=key: self._switch_tab(k))
            btn.pack(side="left")
            self._tab_btns[key] = btn

        # ── Tab frames ────────────────────────────────────
        self._tab_frames = {}
        for key in ("signin", "register"):
            f = tk.Frame(self, bg=BG)
            f.place(x=0, y=110, relwidth=1, relheight=1)
            self._tab_frames[key] = f

        self._build_signin_tab(self._tab_frames["signin"])
        self._build_register_tab(self._tab_frames["register"])
        self._switch_tab("signin")

    def _switch_tab(self, key):
        self._active_tab = key
        for k, btn in self._tab_btns.items():
            if k == key:
                btn.configure(bg=ACCENT, fg=BG)
            else:
                btn.configure(bg=SURFACE2, fg=TEXT3)
        self._tab_frames[key].lift()

    # ── Sign-In Tab ───────────────────────────────────────
    def _build_signin_tab(self, parent):
        card = tk.Frame(parent, bg=SURFACE, padx=36, pady=28)
        card.pack(fill="both", expand=True, padx=28, pady=20)

        make_label(card, "Sign In", fg=TEXT,
                   font=("Segoe UI", 18, "bold"), bg=SURFACE).pack(anchor="w")
        make_label(card, "Enter your credentials to access the system.",
                   fg=TEXT2, font=FONT_SMALL, bg=SURFACE).pack(anchor="w", pady=(2, 18))

        make_label(card, "Username", fg=TEXT2, font=FONT_SMALL, bg=SURFACE).pack(anchor="w")
        self._username_var = tk.StringVar()
        user_entry = make_entry(card, textvariable=self._username_var, width=30)
        user_entry.pack(fill="x", pady=(4, 12))
        user_entry.bind("<Return>", lambda e: self._pw_entry.focus_set())

        make_label(card, "Password", fg=TEXT2, font=FONT_SMALL, bg=SURFACE).pack(anchor="w")
        self._password_var = tk.StringVar()
        self._pw_entry = make_entry(card, textvariable=self._password_var, width=30, show="●")
        self._pw_entry.pack(fill="x", pady=(4, 4))
        self._pw_entry.bind("<Return>", lambda e: self._do_login())

        self._show_pw = tk.BooleanVar(value=False)
        tk.Checkbutton(card, text="Show password",
                       variable=self._show_pw,
                       bg=SURFACE, fg=TEXT3, selectcolor=SURFACE3,
                       activebackground=SURFACE, activeforeground=TEXT2,
                       font=FONT_SMALL,
                       command=self._toggle_pw).pack(anchor="w", pady=(0, 4))

        # Forgot password link — only visible after a failed attempt
        self._forgot_link = tk.Button(
            card, text="Forgot password?",
            font=("Segoe UI", 8, "underline"),
            fg=INFO, bg=SURFACE, relief="flat", cursor="hand2",
            activebackground=SURFACE, activeforeground=ACCENT,
            bd=0, padx=0, pady=0,
            command=self._show_forgot_popup
        )
        self._forgot_link.pack(anchor="w", pady=(0, 12))
        self._forgot_link.pack_forget()  # hidden initially

        self._err_lbl = make_label(card, "", fg=DANGER, bg=SURFACE, font=FONT_SMALL)
        self._err_lbl.pack(anchor="w", pady=(0, 8))

        self._login_btn = tk.Button(
            card, text="Sign In →", font=("Segoe UI", 11, "bold"),
            bg=ACCENT, fg=BG, relief="flat", cursor="hand2",
            padx=20, pady=10, bd=0,
            activebackground=ACCENT2, activeforeground=BG,
            command=self._do_login
        )
        self._login_btn.pack(fill="x")

        tk.Frame(card, bg=BORDER, height=1).pack(fill="x", pady=(22, 10))
        make_label(card, "© Rate-Price Sync v2.0  |  Vietlas Systems",
                   fg=TEXT3, font=("Segoe UI", 8), bg=SURFACE).pack(anchor="center")
        user_entry.focus_set()

    def _toggle_pw(self):
        self._pw_entry.configure(show="" if self._show_pw.get() else "●")

    def _do_login(self):
        username = self._username_var.get().strip()
        password = self._password_var.get()
        if not username or not password:
            self._err_lbl.configure(text="⚠  Please enter both username and password.")
            return

        self._login_btn.configure(text="Signing in…", state="disabled")
        self.update()

        result = self._db.verify_user(username, password)

        if result == "suspended":
            self._login_btn.configure(text="Sign In →", state="normal")
            self._err_lbl.configure(
                text="⚠  Your account has been suspended.\n   Please contact the administrator.")
            self._password_var.set("")
            return

        if isinstance(result, dict) and result.get("locked"):
            self._login_btn.configure(text="Sign In →", state="normal")
            self._err_lbl.configure(
                text=f"⛔  Account locked. Try again in {result['minutes']} minute(s).")
            self._password_var.set("")
            return

        if isinstance(result, dict) and result.get("bad_password"):
            self._login_btn.configure(text="Sign In →", state="normal")
            attempts = result["attempts"]
            if attempts >= 4:
                self._err_lbl.configure(
                    text="⛔  Too many attempts. Account locked for 10 minutes.")
            else:
                remaining = 4 - attempts
                self._err_lbl.configure(
                    text=f"⚠  Invalid credentials. {remaining} attempt(s) remaining.")
            self._forgot_link.pack(anchor="w", pady=(0, 12))  # reveal link
            self._password_var.set("")
            self._pw_entry.focus_set()
            return

        if not result:
            self._login_btn.configure(text="Sign In →", state="normal")
            self._err_lbl.configure(text="⚠  Invalid username or password.")
            self._password_var.set("")
            self._pw_entry.focus_set()
            return

        # Valid credentials — show OTP dialog
        self._login_btn.configure(text="Sign In →", state="normal")
        self._pending_user = result
        self._show_otp_dialog()

    def _show_otp_dialog(self):
        """Show 6-digit OTP verification dialog."""
        dlg = tk.Toplevel(self)
        dlg.title("Two-Factor Verification")
        dlg.geometry("380x280")
        dlg.configure(bg=SURFACE)
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()
        # Center
        self.update_idletasks()
        x = self.winfo_x() + (480 - 380) // 2
        y = self.winfo_y() + (620 - 280) // 2
        dlg.geometry(f"380x280+{x}+{y}")

        make_label(dlg, "🔐  Two-Factor Verification", fg=ACCENT,
                   font=("Segoe UI", 13, "bold"), bg=SURFACE).pack(padx=28, pady=(24, 4), anchor="w")
        make_label(dlg, "Enter your 6-digit OTP to continue.",
                   fg=TEXT2, font=FONT_SMALL, bg=SURFACE).pack(padx=28, anchor="w", pady=(0, 14))

        otp_var = tk.StringVar()
        otp_entry = make_entry(dlg, textvariable=otp_var, width=14,
                               font=("Consolas", 18, "bold"))
        otp_entry.pack(padx=28, anchor="w")
        otp_entry.focus_set()

        err_lbl = make_label(dlg, "", fg=DANGER, font=FONT_SMALL, bg=SURFACE)
        err_lbl.pack(padx=28, pady=(6, 0), anchor="w")

        def _verify_otp():
            entered = otp_var.get().strip()
            if entered == DEFAULT_OTP:
                dlg.destroy()
                self._on_login_success()
            else:
                err_lbl.configure(text="⚠  Incorrect OTP. Please try again.")
                otp_var.set("")

        btn = make_accent_button(dlg, "Verify →", _verify_otp)
        btn.pack(padx=28, pady=14, anchor="w")
        otp_entry.bind("<Return>", lambda e: _verify_otp())

    def _on_login_success(self):
        user = self._pending_user
        if user.get("force_password_change"):
            self._show_force_password_change(user)
        else:
            self._launch_app(user)

    def _show_force_password_change(self, user):
        """Prompt user to change their temporary password."""
        dlg = tk.Toplevel(self)
        dlg.title("Change Password Required")
        dlg.geometry("420x340")
        dlg.configure(bg=SURFACE)
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()
        self.update_idletasks()
        x = self.winfo_x() + (480 - 420) // 2
        y = self.winfo_y() + (620 - 340) // 2
        dlg.geometry(f"420x340+{x}+{y}")

        make_label(dlg, "🔑  Password Change Required", fg=WARNING,
                   font=("Segoe UI", 13, "bold"), bg=SURFACE).pack(padx=28, pady=(24, 4), anchor="w")
        make_label(dlg, "Your password has been reset by the administrator.\nPlease set a new password to continue.",
                   fg=TEXT2, font=FONT_SMALL, bg=SURFACE).pack(padx=28, anchor="w", pady=(0, 16))

        make_label(dlg, "New Password", fg=TEXT2, font=FONT_SMALL, bg=SURFACE).pack(padx=28, anchor="w")
        pw1_var = tk.StringVar()
        e1 = make_entry(dlg, textvariable=pw1_var, width=30, show="●")
        e1.pack(padx=28, anchor="w", pady=(4, 10))

        make_label(dlg, "Confirm Password", fg=TEXT2, font=FONT_SMALL, bg=SURFACE).pack(padx=28, anchor="w")
        pw2_var = tk.StringVar()
        e2 = make_entry(dlg, textvariable=pw2_var, width=30, show="●")
        e2.pack(padx=28, anchor="w", pady=(4, 6))

        err_lbl = make_label(dlg, "", fg=DANGER, font=FONT_SMALL, bg=SURFACE)
        err_lbl.pack(padx=28, anchor="w", pady=(0, 8))

        def _do_change():
            p1, p2 = pw1_var.get(), pw2_var.get()
            if len(p1) < 6:
                err_lbl.configure(text="⚠  Password must be at least 6 characters.")
                return
            if p1 != p2:
                err_lbl.configure(text="⚠  Passwords do not match.")
                return
            if p1 == "ChangeMe":
                err_lbl.configure(text="⚠  Please choose a different password.")
                return
            self._db.update_user_password(user["id"], p1, force_change=False)
            dlg.destroy()
            self._launch_app(user)

        make_accent_button(dlg, "Set New Password →", _do_change).pack(padx=28, anchor="w")
        e1.focus_set()
        e2.bind("<Return>", lambda e: _do_change())

    def _launch_app(self, user):
        self._db.close()
        self.destroy()
        app = RatePriceSyncApp(user)
        app.mainloop()

    def _show_forgot_popup(self):
        messagebox.showinfo(
            "Forgot Password",
            "Please contact the administrator to reset your password."
        )

    # ── Register Tab ──────────────────────────────────────
    def _build_register_tab(self, parent):
        card = tk.Frame(parent, bg=SURFACE, padx=36, pady=28)
        card.pack(fill="both", expand=True, padx=28, pady=20)

        make_label(card, "Create Account", fg=TEXT,
                   font=("Segoe UI", 18, "bold"), bg=SURFACE).pack(anchor="w")
        make_label(card, "Your request will be reviewed by the administrator.",
                   fg=TEXT2, font=FONT_SMALL, bg=SURFACE).pack(anchor="w", pady=(2, 18))

        make_label(card, "Desired Username", fg=TEXT2, font=FONT_SMALL, bg=SURFACE).pack(anchor="w")
        self._reg_user_var = tk.StringVar()
        make_entry(card, textvariable=self._reg_user_var, width=30).pack(fill="x", pady=(4, 12))

        make_label(card, "Password", fg=TEXT2, font=FONT_SMALL, bg=SURFACE).pack(anchor="w")
        self._reg_pw_var = tk.StringVar()
        make_entry(card, textvariable=self._reg_pw_var, width=30, show="●").pack(fill="x", pady=(4, 12))

        make_label(card, "Confirm Password", fg=TEXT2, font=FONT_SMALL, bg=SURFACE).pack(anchor="w")
        self._reg_pw2_var = tk.StringVar()
        make_entry(card, textvariable=self._reg_pw2_var, width=30, show="●").pack(fill="x", pady=(4, 16))

        self._reg_msg = make_label(card, "", fg=DANGER, font=FONT_SMALL, bg=SURFACE)
        self._reg_msg.pack(anchor="w", pady=(0, 10))

        tk.Button(card, text="Submit Request →",
                  font=("Segoe UI", 11, "bold"),
                  bg=INFO, fg=BG, relief="flat", cursor="hand2",
                  padx=20, pady=10, bd=0,
                  activebackground="#5aabec", activeforeground=BG,
                  command=self._do_register).pack(fill="x")

        tk.Frame(card, bg=BORDER, height=1).pack(fill="x", pady=(20, 10))
        make_label(card, "Once approved by the admin, you can sign in with your credentials.",
                   fg=TEXT3, font=("Segoe UI", 8), bg=SURFACE, wraplength=350, justify="left").pack(anchor="w")

    def _do_register(self):
        username = self._reg_user_var.get().strip()
        pw1      = self._reg_pw_var.get()
        pw2      = self._reg_pw2_var.get()

        if not username:
            self._reg_msg.configure(text="⚠  Username is required.", fg=DANGER)
            return
        if len(username) < 3:
            self._reg_msg.configure(text="⚠  Username must be at least 3 characters.", fg=DANGER)
            return
        if len(pw1) < 6:
            self._reg_msg.configure(text="⚠  Password must be at least 6 characters.", fg=DANGER)
            return
        if pw1 != pw2:
            self._reg_msg.configure(text="⚠  Passwords do not match.", fg=DANGER)
            return

        ok = self._db.add_pending_user(username, pw1)
        if ok:
            self._reg_msg.configure(
                text=f"✓  Request submitted for '{username}'.\n   Awaiting administrator approval.",
                fg=ACCENT)
            self._reg_user_var.set("")
            self._reg_pw_var.set("")
            self._reg_pw2_var.set("")
        else:
            self._reg_msg.configure(
                text=f"⚠  Username '{username}' is already taken or request already submitted.",
                fg=DANGER)





# ─── MAIN APPLICATION ────────────────────────────────────
class RatePriceSyncApp(tk.Tk):
    def __init__(self, session: dict = None):
        super().__init__()
        self._session = session or {"username": "admin", "role": "admin"}
        self.title("Rate-Price Sync — Automated Retail Pricing in Zimbabwe")
        self.geometry("1200x750")
        self.minsize(1000, 620)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.db           = Database()
        self.rate_service = RateService()
        self.pricing      = PricingEngine()
        self.integration  = IntegrationBridge()
        self.metrics      = MetricsCollector()

        self.current_rate   = tk.DoubleVar(value=0.0)
        self.rate_source    = tk.StringVar(value="pending")
        self.rate_time      = None
        self.current_result = None

        styled_treeview(self)
        self._build_ui()
        self._auto_fetch_rate()

    def _build_ui(self):
        self.sidebar = make_frame(self, bg=SURFACE, width=210)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self._build_sidebar()

        tk.Frame(self, bg=BORDER, width=1).pack(side="left", fill="y")

        self.content = make_frame(self, bg=BG)
        self.content.pack(side="left", fill="both", expand=True)

        self.pages = {}
        for name in ["dashboard","rates","converter","products","pricelist",
                      "history","integration","metrics","settings","users","about"]:
            frame = make_frame(self.content, bg=BG)
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.pages[name] = frame

        self._build_dashboard()
        self._build_rates()
        self._build_converter()
        self._build_products()
        self._build_pricelist()
        self._build_history()
        self._build_integration()
        self._build_metrics()
        self._build_settings()
        self._build_users()
        self._build_about()
        self._show_page("dashboard")

    def _build_sidebar(self):
        # App name block — Image 3 style: white bg, bold red text like the bar chart graphic
        logo_outer = tk.Frame(self.sidebar, bg="#ffffff", padx=10, pady=8)
        logo_outer.pack(fill="x", padx=12, pady=(16, 10))
        make_label(logo_outer, "Rate-Price Sync",
                   fg="#cc0000", bg="#ffffff",
                   font=("Segoe UI", 13, "bold")).pack(anchor="w")
        make_label(logo_outer, "Automated Retail Pricing in Zimbabwe",
                   fg="#444444", bg="#ffffff",
                   font=("Segoe UI", 7, "bold")).pack(anchor="w")
        tk.Frame(self.sidebar, bg=BORDER, height=1).pack(fill="x")

        self.nav_buttons = {}
        nav_items = [
            ("dashboard",   "⊞  Dashboard"),
            ("rates",       "↗  Live Rates"),
            ("converter",   "⇅  Converter"),
            ("products",    "☰  Products"),
            ("pricelist",   "⎙  Price Lists"),
            ("history",     "◷  Rate History"),
            ("integration", "⇌  POS Integration"),
            ("metrics",     "◈  System Metrics"),
            ("settings",    "⚙  Settings"),
            ("about",       "ℹ  About Us"),
        ]
        if self._session.get("role") == "admin":
            nav_items.append(("users", "👤  User Management"))

        nav_frame = make_frame(self.sidebar, bg=SURFACE)
        nav_frame.pack(fill="x", pady=10)
        for key, label in nav_items:
            btn = tk.Button(nav_frame, text=label, anchor="w",
                            bg=SURFACE, fg=TEXT2, font=FONT_BODY,
                            relief="flat", cursor="hand2", padx=16, pady=8,
                            activebackground=SURFACE3, activeforeground=ACCENT,
                            command=lambda k=key: self._show_page(k))
            btn.pack(fill="x", padx=8, pady=1)
            self.nav_buttons[key] = btn

        # ── Logout + user box at bottom ────────────────────
        tk.Frame(self.sidebar, bg=BORDER, height=1).pack(fill="x", side="bottom")

        logout_btn = tk.Button(
            self.sidebar, text="⏻  Sign Out", anchor="w",
            bg=SURFACE, fg=DANGER, font=FONT_SMALL,
            relief="flat", cursor="hand2", padx=16, pady=6,
            activebackground=SURFACE3, activeforeground=DANGER,
            command=self._logout
        )
        logout_btn.pack(side="bottom", fill="x", padx=8, pady=(0, 4))

        user_box = tk.Frame(self.sidebar, bg=SURFACE3, padx=12, pady=8)
        user_box.pack(side="bottom", fill="x", padx=10, pady=(8, 2))
        role_color = ACCENT if self._session.get("role") == "admin" else INFO
        make_label(user_box, f"● {self._session.get('role','user').upper()}",
                   fg=role_color, font=("Segoe UI", 7, "bold"), bg=SURFACE3).pack(anchor="w")
        make_label(user_box, self._session.get("username", ""),
                   fg=TEXT, font=("Segoe UI", 10, "bold"), bg=SURFACE3).pack(anchor="w")

        rate_box = make_frame(self.sidebar, bg=SURFACE2)
        rate_box.pack(side="bottom", fill="x", padx=10, pady=4)
        inner = tk.Frame(rate_box, bg=SURFACE2)
        inner.pack(padx=12, pady=10)
        make_label(inner, "USD / ZWG", fg=TEXT3, font=("Segoe UI", 8), bg=SURFACE2).pack(anchor="w")
        self.sb_rate_label = make_label(inner, "Loading…", fg=ACCENT,
                                        font=("Consolas", 13, "bold"), bg=SURFACE2)
        self.sb_rate_label.pack(anchor="w")
        self.sb_source_label = make_label(inner, "—", fg=TEXT3, font=("Segoe UI", 8), bg=SURFACE2)
        self.sb_source_label.pack(anchor="w")
        self.sb_time_label = make_label(inner, "—", fg=TEXT3, font=("Segoe UI", 8), bg=SURFACE2)
        self.sb_time_label.pack(anchor="w")

    def _show_page(self, name):
        self.pages[name].lift()
        for k, btn in self.nav_buttons.items():
            btn.configure(bg=SURFACE3 if k == name else SURFACE,
                          fg=ACCENT   if k == name else TEXT2)
        refresh = {
            "dashboard":   self._refresh_dashboard,
            "products":    self._refresh_products,
            "history":     self._refresh_history,
            "settings":    self._refresh_settings,
            "pricelist":   self._refresh_pricelist_summary,
            "converter":   self._refresh_converter,
            "integration": self._refresh_integration,
            "metrics":     self._refresh_metrics,
            "users":       lambda: (self._refresh_users(), self._refresh_pending()),
        }
        if name in refresh:
            refresh[name]()

    def _logout(self):
        if messagebox.askyesno("Sign Out", "Sign out and return to the login screen?"):
            self.db.close()
            self.destroy()
            login = LoginApp()
            login.mainloop()

    # ────── ACCESS CONTROL ────────────────────────────────
    def _is_admin(self) -> bool:
        return self._session.get("role") == "admin"

    def _require_admin(self, action: str = "This action") -> bool:
        """Show a denial message and return False if the user is not admin."""
        if not self._is_admin():
            messagebox.showerror(
                "Access Denied",
                f"{action} requires Administrator privileges.\n\n"
                f"Your role:  {self._session.get('role', 'user').upper()}\n"
                f"You have READ-ONLY access to this system."
            )
            return False
        return True

    def _readonly_banner(self, parent) -> None:
        """Insert a read-only notice bar on a page for non-admin users."""
        if not self._is_admin():
            banner = tk.Frame(parent, bg="#2a1a00", padx=16, pady=8)
            banner.pack(fill="x", padx=28, pady=(8, 0))
            make_label(banner,
                       "🔒  Read-Only Access — You can view data but cannot make changes. "
                       "Contact your administrator to request write access.",
                       fg=WARNING, bg="#2a1a00", font=FONT_SMALL).pack(anchor="w")



    # ────── DASHBOARD ──────────────────────────────────────
    def _build_dashboard(self):
        p = self.pages["dashboard"]
        p.configure(bg=BG)
        hdr = tk.Frame(p, bg=BG)
        hdr.pack(fill="x", padx=28, pady=(24,0))
        make_label(hdr, "Dashboard", font=("Segoe UI", 20, "bold"), bg=BG).pack(anchor="w")
        make_label(hdr, "Live pricing overview — Rate-Price Sync Automated Retail Pricing",
                   fg=TEXT2, bg=BG).pack(anchor="w")

        self.status_frame = tk.Frame(p, bg=SURFACE2)
        self.status_frame.pack(fill="x", padx=28, pady=(14,0))
        self.status_dot = tk.Canvas(self.status_frame, width=10, height=10,
                                    bg=SURFACE2, highlightthickness=0)
        self.status_dot.pack(side="left", padx=(12,6), pady=8)
        self.status_dot.create_oval(2,2,8,8, fill=ACCENT, outline="")
        self.status_lbl = make_label(self.status_frame, "Connecting…",
                                     fg=TEXT2, bg=SURFACE2, font=FONT_SMALL)
        self.status_lbl.pack(side="left", pady=8)
        self.status_badge = make_label(self.status_frame, "", fg=ACCENT,
                                       bg=SURFACE2, font=("Consolas", 8))
        self.status_badge.pack(side="right", padx=12, pady=8)

        metrics_frame = tk.Frame(p, bg=BG)
        metrics_frame.pack(fill="x", padx=28, pady=14)
        self.d_metrics = {}
        for key, lbl, val, color in [
            ("rate",     "Current Rate",   "—",  ACCENT),
            ("products", "Total Products", "0",  TEXT),
            ("checks",   "Rate Checks",    "0",  TEXT),
            ("updated",  "Last Updated",   "—",  TEXT),
        ]:
            card = tk.Frame(metrics_frame, bg=SURFACE2, padx=16, pady=12)
            card.pack(side="left", fill="x", expand=True, padx=(0,12))
            make_label(card, lbl, fg=TEXT3, font=("Segoe UI", 8), bg=SURFACE2).pack(anchor="w")
            v_lbl = make_label(card, val, fg=color, font=("Consolas", 16, "bold"), bg=SURFACE2)
            v_lbl.pack(anchor="w", pady=(4,0))
            self.d_metrics[key] = v_lbl

        bottom = tk.Frame(p, bg=BG)
        bottom.pack(fill="both", expand=True, padx=28, pady=(0,24))
        qc = tk.Frame(bottom, bg=SURFACE, padx=18, pady=14)
        qc.pack(side="left", fill="both", expand=True, padx=(0,12))
        make_label(qc, "QUICK CONVERT", fg=TEXT3, font=("Segoe UI", 8, "bold"), bg=SURFACE).pack(anchor="w")
        make_label(qc, "USD Amount", fg=TEXT2, bg=SURFACE, font=FONT_SMALL).pack(anchor="w", pady=(10,4))
        self.qc_var = tk.StringVar()
        self.qc_var.trace_add("write", lambda *a: self._quick_convert())
        make_entry(qc, textvariable=self.qc_var, width=22).pack(anchor="w")
        make_label(qc, "⇅", fg=TEXT3, bg=SURFACE, font=("Segoe UI", 16)).pack(anchor="w", pady=4)
        self.qc_result = make_label(qc, "ZWG —", fg=ACCENT, bg=SURFACE,
                                    font=("Consolas", 18, "bold"))
        self.qc_result.pack(anchor="w")

        rp = tk.Frame(bottom, bg=SURFACE, padx=18, pady=14)
        rp.pack(side="left", fill="both", expand=True)
        make_label(rp, "RECENT PRODUCTS", fg=TEXT3,
                   font=("Segoe UI", 8, "bold"), bg=SURFACE).pack(anchor="w", pady=(0,8))
        cols = ("Product","Category","USD","ZWG + Margin")
        self.dash_tree = ttk.Treeview(rp, columns=cols, show="headings",
                                      height=6, style="Dark.Treeview")
        for col, w in zip(cols, [180,110,70,110]):
            self.dash_tree.heading(col, text=col)
            self.dash_tree.column(col, width=w, anchor="w")
        self.dash_tree.pack(fill="both", expand=True)

    def _refresh_dashboard(self):
        r        = self.current_rate.get()
        products = self.db.get_products()
        checks   = len(self.db.get_rate_history())
        self.d_metrics["rate"].configure(text=f"{r:.2f}" if r else "—")
        self.d_metrics["products"].configure(text=str(len(products)))
        self.d_metrics["checks"].configure(text=str(checks))
        self.d_metrics["updated"].configure(
            text=self.rate_time.strftime("%H:%M:%S") if self.rate_time else "—")
        src = self.rate_source.get()
        self.status_lbl.configure(
            text=f"{'Live rate active' if 'Estimated' not in src else 'Estimated rate'} — "
                 f"{datetime.now().strftime('%d %b %Y %H:%M')}")
        self.status_badge.configure(
            text="● LIVE" if "Estimated" not in src else "● EST",
            fg="#ff3333" if "Estimated" not in src else WARNING)
        for item in self.dash_tree.get_children():
            self.dash_tree.delete(item)
        for prod in products[:7]:
            zwg_m = self.pricing.zwg_price(prod["usd_price"], r, prod["category"], prod["margin"]) if r else 0
            self.dash_tree.insert("", "end", values=(
                prod["name"], prod["category"],
                f"${prod['usd_price']:.2f}",
                f"ZWG {zwg_m:.2f}" if r else "—"
            ))
        self._quick_convert()

    def _quick_convert(self):
        try:
            usd = float(self.qc_var.get())
            r   = self.current_rate.get()
            self.qc_result.configure(text=f"ZWG {usd*r:.2f}" if r else "ZWG —")
        except ValueError:
            self.qc_result.configure(text="ZWG —")

    # ────── LIVE RATES ─────────────────────────────────────
    def _build_rates(self):
        p = self.pages["rates"]
        p.configure(bg=BG)
        hdr = tk.Frame(p, bg=BG)
        hdr.pack(fill="x", padx=28, pady=(24,0))
        make_label(hdr, "Live Rates", font=("Segoe UI", 20, "bold"), bg=BG).pack(anchor="w")
        make_label(hdr, "Live USD/ZWG rates. Sources: RBZ → ZimRate → ZimPriceCheck → fallback.",
                   fg=TEXT2, bg=BG).pack(anchor="w")

        rate_card = tk.Frame(p, bg=SURFACE, padx=24, pady=18)
        rate_card.pack(fill="x", padx=28, pady=14)
        top_row = tk.Frame(rate_card, bg=SURFACE)
        top_row.pack(fill="x")
        left = tk.Frame(top_row, bg=SURFACE)
        left.pack(side="left", fill="x", expand=True)
        make_label(left, "MID-MARKET RATE  (USD → ZWG)",
                   fg=TEXT3, font=("Segoe UI", 8, "bold"), bg=SURFACE).pack(anchor="w")
        rate_row = tk.Frame(left, bg=SURFACE)
        rate_row.pack(anchor="w", pady=(6,0))
        self.rate_big = make_label(rate_row, "—", fg=ACCENT,
                                   font=("Consolas", 36, "bold"), bg=SURFACE)
        self.rate_big.pack(side="left")
        make_label(rate_row, " ZWG per 1 USD",
                   fg=TEXT2, bg=SURFACE).pack(side="left", padx=(8,0), pady=(12,0))
        self.rate_pct_lbl  = make_label(left, "", fg=ACCENT, font=("Consolas", 11), bg=SURFACE)
        self.rate_pct_lbl.pack(anchor="w", pady=(2,0))
        self.rate_time_lbl = make_label(left, "—", fg=TEXT3, font=FONT_SMALL, bg=SURFACE)
        self.rate_time_lbl.pack(anchor="w", pady=(4,0))
        self.rate_api_lbl  = make_label(left, "—", fg=TEXT3, font=("Segoe UI", 8), bg=SURFACE)
        self.rate_api_lbl.pack(anchor="w", pady=(2,0))

        right = tk.Frame(top_row, bg=SURFACE)
        right.pack(side="right")
        self.rate_src_lbl = make_label(right, "● PENDING",
                                       fg=WARNING, font=("Consolas", 9, "bold"), bg=SURFACE)
        self.rate_src_lbl.pack(anchor="e", pady=(0,10))
        make_accent_button(right, "↻  Refresh Rate", self._fetch_rate_manual).pack(anchor="e")

        mf = tk.Frame(p, bg=BG)
        mf.pack(fill="x", padx=28, pady=(0,14))
        self.rate_metrics = {}
        for key, lbl in [("bid","Bid Rate"),("ask","Ask Rate"),
                          ("spread","Spread"),("latency","Fetch Latency")]:
            c = tk.Frame(mf, bg=SURFACE2, padx=16, pady=12)
            c.pack(side="left", fill="x", expand=True, padx=(0,12))
            make_label(c, lbl.upper(), fg=TEXT3, font=("Segoe UI", 8), bg=SURFACE2).pack(anchor="w")
            v = make_label(c, "—", fg=ACCENT, font=("Consolas", 14, "bold"), bg=SURFACE2)
            v.pack(anchor="w", pady=(4,0))
            self.rate_metrics[key] = v

        ref_frame = tk.Frame(p, bg=SURFACE, padx=18, pady=14)
        ref_frame.pack(fill="both", expand=True, padx=28, pady=(0,24))
        make_label(ref_frame, "REFERENCE TABLE", fg=TEXT3,
                   font=("Segoe UI", 8, "bold"), bg=SURFACE).pack(anchor="w", pady=(0,8))
        cols = ("USD Amount","ZWG Equivalent (Mid)","ZWG (Ask/Bank Rate)","Notes")
        self.ref_tree = ttk.Treeview(ref_frame, columns=cols, show="headings",
                                     height=8, style="Dark.Treeview")
        for col, w in zip(cols, [150, 180, 180, 160]):
            self.ref_tree.heading(col, text=col)
            self.ref_tree.column(col, width=w, anchor="w")
        self.ref_tree.pack(fill="both", expand=True)

    def _refresh_rates_page(self):
        r = self.current_rate.get()
        if not r:
            return
        res = self.current_result
        self.rate_big.configure(text=f"{r:.4f}")
        ts = self.rate_time.strftime("%d %b %Y at %H:%M:%S") if self.rate_time else "—"
        self.rate_time_lbl.configure(text=f"Last updated: {ts}")
        if res and res.pct_change is not None:
            pct   = res.pct_change
            arrow = "▲" if pct >= 0 else "▼"
            self.rate_pct_lbl.configure(
                text=f"{arrow} {abs(pct):.2f}% from previous session",
                fg=ACCENT if pct >= 0 else DANGER)
        else:
            self.rate_pct_lbl.configure(text="")
        src     = self.rate_source.get()
        is_live = "Estimated" not in src
        self.rate_src_lbl.configure(text="● LIVE" if is_live else "● ESTIMATED",
                                    fg="#ff3333" if is_live else WARNING)
        self.rate_api_lbl.configure(text=f"Source: {src}" if res else "")
        if res:
            self.rate_metrics["bid"].configure(text=f"{res.bid:.4f} ZWG")
            self.rate_metrics["ask"].configure(text=f"{res.ask:.4f} ZWG")
            self.rate_metrics["spread"].configure(text=f"{res.spread:.4f}")
            self.rate_metrics["latency"].configure(text=f"{res.latency_ms:.0f} ms")
        amounts = [1,5,10,20,50,100,200,500,1000]
        notes   = {1:"Unit",5:"Small pack",10:"Budget",20:"Common",
                   50:"Mid-range",100:"Bulk",200:"",500:"High-value",1000:"Premium"}
        ask_r   = res.ask if res else r
        for item in self.ref_tree.get_children():
            self.ref_tree.delete(item)
        for a in amounts:
            self.ref_tree.insert("", "end", values=(
                f"${a:.2f}", f"ZWG {a*r:.2f}", f"ZWG {a*ask_r:.2f}", notes.get(a,"")))

    # ────── CONVERTER ──────────────────────────────────────
    def _build_converter(self):
        p = self.pages["converter"]
        p.configure(bg=BG)
        hdr = tk.Frame(p, bg=BG)
        hdr.pack(fill="x", padx=28, pady=(24,0))
        make_label(hdr, "Currency Converter", font=("Segoe UI", 20, "bold"), bg=BG).pack(anchor="w")
        make_label(hdr, "Convert USD ↔ ZWG using the live market rate.", fg=TEXT2, bg=BG).pack(anchor="w")
        mid = tk.Frame(p, bg=BG)
        mid.pack(fill="x", padx=28, pady=14)
        c1 = tk.Frame(mid, bg=SURFACE, padx=20, pady=16)
        c1.pack(side="left", fill="both", expand=True, padx=(0,12))
        make_label(c1, "USD → ZWG", fg=TEXT3, font=("Segoe UI", 8, "bold"), bg=SURFACE).pack(anchor="w")
        make_label(c1, "Enter USD", fg=TEXT2, bg=SURFACE, font=FONT_SMALL).pack(anchor="w", pady=(10,4))
        self.c1_var = tk.StringVar()
        self.c1_var.trace_add("write", lambda *a: self._conv1())
        make_entry(c1, textvariable=self.c1_var, width=24).pack(anchor="w")
        res1 = tk.Frame(c1, bg=SURFACE3, padx=14, pady=10)
        res1.pack(fill="x", pady=(12,0))
        make_label(res1, "ZWG RESULT", fg=TEXT3, font=("Segoe UI", 8), bg=SURFACE3).pack(anchor="w")
        self.c1_result = make_label(res1, "—", fg=ACCENT,
                                    font=("Consolas", 20, "bold"), bg=SURFACE3)
        self.c1_result.pack(anchor="w", pady=(4,0))
        self.c1_note = make_label(c1, "", fg=TEXT3, font=("Segoe UI", 8), bg=SURFACE)
        self.c1_note.pack(anchor="w", pady=(6,0))
        c2 = tk.Frame(mid, bg=SURFACE, padx=20, pady=16)
        c2.pack(side="left", fill="both", expand=True)
        make_label(c2, "ZWG → USD", fg=TEXT3, font=("Segoe UI", 8, "bold"), bg=SURFACE).pack(anchor="w")
        make_label(c2, "Enter ZWG", fg=TEXT2, bg=SURFACE, font=FONT_SMALL).pack(anchor="w", pady=(10,4))
        self.c2_var = tk.StringVar()
        self.c2_var.trace_add("write", lambda *a: self._conv2())
        make_entry(c2, textvariable=self.c2_var, width=24).pack(anchor="w")
        res2 = tk.Frame(c2, bg=SURFACE3, padx=14, pady=10)
        res2.pack(fill="x", pady=(12,0))
        make_label(res2, "USD RESULT", fg=TEXT3, font=("Segoe UI", 8), bg=SURFACE3).pack(anchor="w")
        self.c2_result = make_label(res2, "—", fg=INFO,
                                    font=("Consolas", 20, "bold"), bg=SURFACE3)
        self.c2_result.pack(anchor="w", pady=(4,0))
        self.c2_note = make_label(c2, "", fg=TEXT3, font=("Segoe UI", 8), bg=SURFACE)
        self.c2_note.pack(anchor="w", pady=(6,0))
        bulk = tk.Frame(p, bg=SURFACE, padx=18, pady=14)
        bulk.pack(fill="both", expand=True, padx=28, pady=(0,24))
        bh = tk.Frame(bulk, bg=SURFACE)
        bh.pack(fill="x", pady=(0,8))
        make_label(bh, "BULK CONVERSION TABLE", fg=TEXT3,
                   font=("Segoe UI", 8, "bold"), bg=SURFACE).pack(side="left")
        make_label(bh, "Base USD:", fg=TEXT2, bg=SURFACE, font=FONT_SMALL).pack(side="left", padx=(16,4))
        self.bulk_base_var = tk.StringVar(value="1")
        self.bulk_base_var.trace_add("write", lambda *a: self._build_bulk())
        make_entry(bh, textvariable=self.bulk_base_var, width=8).pack(side="left")
        cols = ("USD Amount","ZWG Equivalent","ZWG (Rounded)")
        self.bulk_tree = ttk.Treeview(bulk, columns=cols, show="headings",
                                      height=7, style="Dark.Treeview")
        for col, w in zip(cols, [160,180,180]):
            self.bulk_tree.heading(col, text=col)
            self.bulk_tree.column(col, width=w, anchor="w")
        self.bulk_tree.pack(fill="both", expand=True)

    def _conv1(self):
        try:
            usd = float(self.c1_var.get())
            r   = self.current_rate.get()
            self.c1_result.configure(text=f"ZWG {usd*r:.2f}" if r else "—")
        except ValueError:
            self.c1_result.configure(text="—")

    def _conv2(self):
        try:
            zwl = float(self.c2_var.get())
            r   = self.current_rate.get()
            self.c2_result.configure(text=f"USD {zwl/r:.4f}" if r else "—")
        except ValueError:
            self.c2_result.configure(text="—")

    def _refresh_converter(self):
        r    = self.current_rate.get()
        note = f"Rate: 1 USD = {r:.2f} ZWG" if r else "No rate loaded"
        self.c1_note.configure(text=note)
        self.c2_note.configure(text=note)
        self._build_bulk()

    def _build_bulk(self):
        r = self.current_rate.get()
        try:
            base = float(self.bulk_base_var.get()) if self.bulk_base_var.get() else 1
        except ValueError:
            base = 1
        for item in self.bulk_tree.get_children():
            self.bulk_tree.delete(item)
        for m in [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]:
            usd = base * m
            if r:
                zwl = usd * r
                self.bulk_tree.insert("", "end", values=(
                    f"${usd:.2f}", f"ZWG {zwl:.2f}", f"ZWG {round(zwl):,}"))
            else:
                self.bulk_tree.insert("", "end", values=(f"${usd:.2f}", "—", "—"))

    # ────── PRODUCTS ───────────────────────────────────────
    def _build_products(self):
        p = self.pages["products"]
        p.configure(bg=BG)
        hdr = tk.Frame(p, bg=BG)
        hdr.pack(fill="x", padx=28, pady=(24,0))
        make_label(hdr, "Products", font=("Segoe UI", 20, "bold"), bg=BG).pack(anchor="w")
        make_label(hdr, "149 preloaded products across 11 categories.",
                   fg=TEXT2, bg=BG).pack(anchor="w")

        self._readonly_banner(p)

        if self._is_admin():
            form = tk.Frame(p, bg=SURFACE, padx=20, pady=14)
            form.pack(fill="x", padx=28, pady=14)
            make_label(form, "ADD PRODUCT", fg=TEXT3,
                       font=("Segoe UI", 8, "bold"), bg=SURFACE).pack(anchor="w", pady=(0,8))
            row = tk.Frame(form, bg=SURFACE)
            row.pack(fill="x")
            self.p_name_var   = tk.StringVar()
            self.p_cat_var    = tk.StringVar()
            self.p_usd_var    = tk.StringVar()
            self.p_margin_var = tk.StringVar(value="10")
            for lbl, var, w in [
                ("Product Name", self.p_name_var, 22),
                ("Category",     self.p_cat_var,  14),
                ("USD Price",    self.p_usd_var,  10),
                ("Margin %",     self.p_margin_var, 8),
            ]:
                col = tk.Frame(row, bg=SURFACE)
                col.pack(side="left", padx=(0,12))
                make_label(col, lbl, fg=TEXT2, bg=SURFACE, font=FONT_SMALL).pack(anchor="w", pady=(0,3))
                make_entry(col, textvariable=var, width=w).pack()
            make_accent_button(row, "+ Add", self._add_product).pack(side="left", pady=(16,0))
        else:
            # Provide stub vars so refresh methods don't fail
            self.p_name_var   = tk.StringVar()
            self.p_cat_var    = tk.StringVar()
            self.p_usd_var    = tk.StringVar()
            self.p_margin_var = tk.StringVar(value="10")

        # Toolbar with category filter
        tb = tk.Frame(p, bg=BG)
        tb.pack(fill="x", padx=28, pady=(0,8))
        self.p_search_var = tk.StringVar()
        self.p_search_var.trace_add("write", lambda *a: self._refresh_products())
        make_label(tb, "Search:", fg=TEXT2, bg=BG, font=FONT_SMALL).pack(side="left", padx=(0,4))
        make_entry(tb, textvariable=self.p_search_var, width=20).pack(side="left", padx=(0,12))
        make_label(tb, "Category:", fg=TEXT2, bg=BG, font=FONT_SMALL).pack(side="left", padx=(0,4))
        self.p_cat_filter = tk.StringVar(value="All")
        self.p_cat_combo  = ttk.Combobox(tb, textvariable=self.p_cat_filter,
                                          width=18, state="readonly")
        self.p_cat_combo.pack(side="left")
        self.p_cat_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_products())
        make_button(tb, "⬇ CSV",   self._export_products_csv,   bg=SURFACE3).pack(side="right")
        make_button(tb, "⬇ Excel", self._export_products_excel, bg=SURFACE3).pack(side="right", padx=(0,8))
        if self._is_admin():
            make_button(tb, "⇌ Sync POS", self._sync_pos_products, bg=SURFACE3, fg=INFO).pack(side="right", padx=(0,8))

        tree_frame = tk.Frame(p, bg=BG)
        tree_frame.pack(fill="both", expand=True, padx=28, pady=(0,8))
        cols = ("ID","Product","Category","USD Price","ZWG Price","Margin %","ZWG + Margin")
        self.p_tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                   style="Dark.Treeview")
        for col, w in zip(cols, [0, 220, 120, 90, 110, 70, 120]):
            self.p_tree.heading(col, text=col)
            self.p_tree.column(col, width=w if col != "ID" else 0, anchor="w",
                               stretch=col != "ID")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.p_tree.yview)
        self.p_tree.configure(yscrollcommand=vsb.set)
        self.p_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        if self._is_admin():
            make_button(p, "✕  Delete Selected", self._delete_product,
                        bg=SURFACE2, fg=DANGER).pack(padx=28, anchor="w", pady=(0,16))

    def _add_product(self):
        if not self._require_admin("Adding products"):
            return
        name   = self.p_name_var.get().strip()
        cat    = self.p_cat_var.get().strip() or "General"
        try:
            usd    = float(self.p_usd_var.get())
            margin = float(self.p_margin_var.get() or 10)
        except ValueError:
            messagebox.showerror("Error", "Enter a valid USD price and margin.")
            return
        if not name:
            messagebox.showerror("Error", "Product name is required.")
            return
        self.db.add_product(name, cat, usd, margin)
        self.p_name_var.set("")
        self.p_cat_var.set("")
        self.p_usd_var.set("")
        self._refresh_products()
        self._refresh_dashboard()

    def _delete_product(self):
        if not self._require_admin("Deleting products"):
            return
        sel = self.p_tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Select a product to delete.")
            return
        if messagebox.askyesno("Confirm", f"Delete {len(sel)} product(s)?"):
            for item in sel:
                pid = int(self.p_tree.item(item)["values"][0])
                self.db.delete_product(pid)
            self._refresh_products()
            self._refresh_dashboard()

    def _refresh_products(self):
        r      = self.current_rate.get()
        search = self.p_search_var.get() if hasattr(self, "p_search_var") else ""
        cat    = self.p_cat_filter.get() if hasattr(self, "p_cat_filter") else "All"
        # Update category dropdown
        cats = ["All"] + self.db.get_categories()
        if hasattr(self, "p_cat_combo"):
            self.p_cat_combo["values"] = cats
        prods  = self.db.get_products(search=search, category=cat if cat != "All" else "")
        for item in self.p_tree.get_children():
            self.p_tree.delete(item)
        for prod in prods:
            zwl   = f"ZWG {prod['usd_price']*r:.2f}" if r else "—"
            zwl_m = f"ZWG {self.pricing.zwg_price(prod['usd_price'], r, prod['category'], prod['margin']):.2f}" if r else "—"
            self.p_tree.insert("", "end", values=(
                prod["id"], prod["name"], prod["category"],
                f"${prod['usd_price']:.2f}", zwl, f"{prod['margin']}%", zwl_m
            ))
        if r:
            self.metrics.record_pricing_event(len(prods), r)

    def _sync_pos_products(self):
        if not self._require_admin("POS sync"):
            return
        r = self.current_rate.get()
        if not r:
            messagebox.showwarning("No Rate", "Fetch a live rate first.")
            return
        prods      = self.db.get_products()
        price_data = self.pricing.bulk_price(prods, r)
        out_path   = self.integration.write_sync_file(price_data, r)
        messagebox.showinfo("POS Sync", f"Sync file written:\n{out_path}")

    def _export_products_csv(self):
        r = self.current_rate.get()
        if not r:
            messagebox.showwarning("No Rate", "Fetch a live rate first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                             filetypes=[("CSV","*.csv")],
                                             initialfile="products.csv")
        if not path:
            return
        prods = self.db.get_products()
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Product","Category","USD Price","ZWG Price","Margin %","ZWG + Margin"])
            for prod in prods:
                zwl   = prod["usd_price"] * r
                zwl_m = self.pricing.zwg_price(prod["usd_price"], r, prod["category"], prod["margin"])
                writer.writerow([prod["name"], prod["category"],
                                  f"{prod['usd_price']:.2f}", f"{zwl:.2f}",
                                  prod["margin"], f"{zwl_m:.2f}"])
            writer.writerow([])
            writer.writerow([f"Rate: 1 USD = {r:.2f} ZWG",
                             f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M')}"])
        messagebox.showinfo("Exported", f"Saved to {path}")

    def _export_products_excel(self):
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment
        except ImportError:
            messagebox.showerror("Missing Library", "Install openpyxl:\npip install openpyxl")
            return
        r = self.current_rate.get()
        if not r:
            messagebox.showwarning("No Rate", "Fetch a live rate first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                             filetypes=[("Excel","*.xlsx")],
                                             initialfile="products.xlsx")
        if not path:
            return
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Products"
        headers   = ["Product","Category","USD Price","ZWG Price","Margin %","ZWG + Margin"]
        hfill     = PatternFill("solid", fgColor="111e30")
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.font      = Font(bold=True, color="3b9eff")
            cell.fill      = hfill
            cell.alignment = Alignment(horizontal="left")
        ws.column_dimensions["A"].width = 35
        ws.column_dimensions["B"].width = 18
        for c in ["C","D","E","F"]:
            ws.column_dimensions[c].width = 16
        prods = self.db.get_products()
        for row_i, prod in enumerate(prods, 2):
            zwl   = prod["usd_price"] * r
            zwl_m = self.pricing.zwg_price(prod["usd_price"], r, prod["category"], prod["margin"])
            ws.cell(row=row_i, column=1, value=prod["name"])
            ws.cell(row=row_i, column=2, value=prod["category"])
            ws.cell(row=row_i, column=3, value=round(prod["usd_price"], 2))
            ws.cell(row=row_i, column=4, value=round(zwl, 2))
            ws.cell(row=row_i, column=5, value=prod["margin"])
            ws.cell(row=row_i, column=6, value=round(zwl_m, 2))
        note_row = len(prods) + 3
        ws.cell(row=note_row, column=1, value=f"Rate used: 1 USD = {r:.2f} ZWG")
        ws.cell(row=note_row, column=3, value=f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        wb.save(path)
        messagebox.showinfo("Exported", f"Saved to {path}")

    # ────── PRICE LIST ─────────────────────────────────────
    def _build_pricelist(self):
        p = self.pages["pricelist"]
        p.configure(bg=BG)
        hdr = tk.Frame(p, bg=BG)
        hdr.pack(fill="x", padx=28, pady=(24,0))
        make_label(hdr, "Price Lists", font=("Segoe UI", 20, "bold"), bg=BG).pack(anchor="w")
        make_label(hdr, "Generate and export formatted retail price lists.",
                   fg=TEXT2, bg=BG).pack(anchor="w")
        top = tk.Frame(p, bg=BG)
        top.pack(fill="x", padx=28, pady=14)
        sf = tk.Frame(top, bg=SURFACE, padx=18, pady=14)
        sf.pack(side="left", fill="y", padx=(0,12))
        make_label(sf, "GENERATE PRICE LIST", fg=TEXT3,
                   font=("Segoe UI", 8, "bold"), bg=SURFACE).pack(anchor="w", pady=(0,10))
        self.pl_title_var  = tk.StringVar(value="Retail Price List")
        self.pl_biz_var    = tk.StringVar()
        self.pl_margin_var = tk.StringVar(value="10")
        self.pl_cat_var    = tk.StringVar()
        for lbl, var in [("List Title", self.pl_title_var),
                          ("Business Name", self.pl_biz_var),
                          ("Global Margin (%)", self.pl_margin_var),
                          ("Filter by Category", self.pl_cat_var)]:
            make_label(sf, lbl, fg=TEXT2, bg=SURFACE, font=FONT_SMALL).pack(anchor="w", pady=(6,2))
            make_entry(sf, textvariable=var, width=22).pack(anchor="w")
        make_accent_button(sf, "Generate Preview", self._generate_pricelist).pack(anchor="w", pady=(14,4))
        make_button(sf, "⬇ Export CSV",   self._export_pricelist_csv,   bg=SURFACE3).pack(anchor="w", pady=3)
        make_button(sf, "⬇ Export Excel", self._export_pricelist_excel, bg=SURFACE3).pack(anchor="w", pady=3)
        sumf = tk.Frame(top, bg=SURFACE, padx=18, pady=14)
        sumf.pack(side="left", fill="y")
        make_label(sumf, "SUMMARY", fg=TEXT3,
                   font=("Segoe UI", 8, "bold"), bg=SURFACE).pack(anchor="w", pady=(0,10))
        self.pl_sum = {}
        for key, lbl in [("count","Products included"),("rate","Rate used"),("time","Generated at")]:
            make_label(sumf, lbl, fg=TEXT2, bg=SURFACE, font=FONT_SMALL).pack(anchor="w", pady=(6,2))
            v = make_label(sumf, "—", fg=ACCENT, font=("Consolas", 12, "bold"), bg=SURFACE)
            v.pack(anchor="w")
            self.pl_sum[key] = v
        prev = tk.Frame(p, bg=SURFACE, padx=18, pady=14)
        prev.pack(fill="both", expand=True, padx=28, pady=(0,24))
        pv_hdr = tk.Frame(prev, bg=SURFACE)
        pv_hdr.pack(fill="x", pady=(0,8))
        self.pl_prev_title = make_label(pv_hdr, "Price List Preview",
                                        fg=TEXT, font=FONT_TITLE, bg=SURFACE)
        self.pl_prev_title.pack(side="left")
        self.pl_prev_meta = make_label(pv_hdr, "", fg=TEXT3, font=FONT_SMALL, bg=SURFACE)
        self.pl_prev_meta.pack(side="left", padx=16)
        cols = ("#","Product","Category","USD","ZWG (Base)","ZWG + Margin")
        self.pl_tree = ttk.Treeview(prev, columns=cols, show="headings",
                                    style="Dark.Treeview")
        for col, w in zip(cols, [40,210,120,90,120,130]):
            self.pl_tree.heading(col, text=col)
            self.pl_tree.column(col, width=w, anchor="w")
        vsb2 = ttk.Scrollbar(prev, orient="vertical", command=self.pl_tree.yview)
        self.pl_tree.configure(yscrollcommand=vsb2.set)
        self.pl_tree.pack(side="left", fill="both", expand=True)
        vsb2.pack(side="right", fill="y")

    def _refresh_pricelist_summary(self):
        r     = self.current_rate.get()
        prods = self.db.get_products()
        self.pl_sum["count"].configure(text=str(len(prods)))
        self.pl_sum["rate"].configure(text=f"{r:.2f} ZWG/USD" if r else "—")

    def _generate_pricelist(self):
        r = self.current_rate.get()
        if not r:
            messagebox.showwarning("No Rate", "Fetch a live rate first.")
            return
        try:
            margin = float(self.pl_margin_var.get() or 0)
        except ValueError:
            margin = 0
        cat_filter = self.pl_cat_var.get().strip()
        prods = self.db.get_products(category=cat_filter) if cat_filter else self.db.get_products()
        if not prods:
            messagebox.showinfo("No Products", "No products match the filter.")
            return
        now = datetime.now()
        self.pl_sum["count"].configure(text=str(len(prods)))
        self.pl_sum["rate"].configure(text=f"{r:.2f} ZWG/USD")
        self.pl_sum["time"].configure(text=now.strftime("%d %b %Y %H:%M"))
        title = self.pl_title_var.get() or "Price List"
        biz   = self.pl_biz_var.get()
        self.pl_prev_title.configure(text=title)
        meta  = f"{biz + ' · ' if biz else ''}Rate: 1 USD = {r:.2f} ZWG · {now.strftime('%d/%m/%Y')}"
        self.pl_prev_meta.configure(text=meta)
        for item in self.pl_tree.get_children():
            self.pl_tree.delete(item)
        for i, prod in enumerate(prods, 1):
            zwl   = prod["usd_price"] * r
            zwl_m = self.pricing.zwg_price(prod["usd_price"], r, prod["category"], margin)
            self.pl_tree.insert("", "end", values=(
                i, prod["name"], prod["category"],
                f"${prod['usd_price']:.2f}", f"ZWG {zwl:.2f}", f"ZWG {zwl_m:.2f}"
            ))

    def _export_pricelist_csv(self):
        r = self.current_rate.get()
        if not r:
            messagebox.showwarning("No Rate", "Fetch a live rate first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                             filetypes=[("CSV","*.csv")],
                                             initialfile="price_list.csv")
        if not path:
            return
        try:
            margin = float(self.pl_margin_var.get() or 0)
        except ValueError:
            margin = 0
        cat_filter = self.pl_cat_var.get().strip()
        prods = self.db.get_products(category=cat_filter) if cat_filter else self.db.get_products()
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([self.pl_title_var.get() or "Price List"])
            writer.writerow([f"Rate: 1 USD = {r:.2f} ZWG",
                             f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"])
            writer.writerow([])
            writer.writerow(["#","Product","Category","USD Price","ZWG Price","ZWG + Margin"])
            for i, prod in enumerate(prods, 1):
                zwl   = prod["usd_price"] * r
                zwl_m = self.pricing.zwg_price(prod["usd_price"], r, prod["category"], margin)
                writer.writerow([i, prod["name"], prod["category"],
                                  f"{prod['usd_price']:.2f}", f"{zwl:.2f}", f"{zwl_m:.2f}"])
        messagebox.showinfo("Exported", f"Saved to {path}")

    def _export_pricelist_excel(self):
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment
        except ImportError:
            messagebox.showerror("Missing Library", "Install openpyxl:\npip install openpyxl")
            return
        r = self.current_rate.get()
        if not r:
            messagebox.showwarning("No Rate", "Fetch a live rate first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                             filetypes=[("Excel","*.xlsx")],
                                             initialfile="price_list.xlsx")
        if not path:
            return
        try:
            margin = float(self.pl_margin_var.get() or 0)
        except ValueError:
            margin = 0
        cat_filter = self.pl_cat_var.get().strip()
        prods = self.db.get_products(category=cat_filter) if cat_filter else self.db.get_products()
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Price List"
        title = self.pl_title_var.get() or "Retail Price List"
        biz   = self.pl_biz_var.get()
        ws.merge_cells("A1:F1")
        ws["A1"] = title
        ws["A1"].font = Font(bold=True, size=14, color="3b9eff")
        ws["A2"] = f"Business: {biz}" if biz else ""
        ws["C2"] = f"Rate: 1 USD = {r:.2f} ZWG"
        ws["E2"] = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        headers = ["#","Product","Category","USD Price","ZWG Price","ZWG + Margin"]
        hfill   = PatternFill("solid", fgColor="111e30")
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=4, column=col, value=h)
            cell.font = Font(bold=True, color="3b9eff")
            cell.fill = hfill
        ws.column_dimensions["A"].width = 6
        ws.column_dimensions["B"].width = 35
        ws.column_dimensions["C"].width = 18
        for c in ["D","E","F"]:
            ws.column_dimensions[c].width = 16
        for i, prod in enumerate(prods, 1):
            zwl   = prod["usd_price"] * r
            zwl_m = self.pricing.zwg_price(prod["usd_price"], r, prod["category"], margin)
            row   = 4 + i
            ws.cell(row=row, column=1, value=i)
            ws.cell(row=row, column=2, value=prod["name"])
            ws.cell(row=row, column=3, value=prod["category"])
            ws.cell(row=row, column=4, value=round(prod["usd_price"], 2))
            ws.cell(row=row, column=5, value=round(zwl, 2))
            ws.cell(row=row, column=6, value=round(zwl_m, 2))
        wb.save(path)
        messagebox.showinfo("Exported", f"Saved to {path}")

    # ────── HISTORY ────────────────────────────────────────
    def _build_history(self):
        p = self.pages["history"]
        p.configure(bg=BG)
        hdr = tk.Frame(p, bg=BG)
        hdr.pack(fill="x", padx=28, pady=(24,0))
        make_label(hdr, "Rate History", font=("Segoe UI", 20, "bold"), bg=BG).pack(anchor="w")
        make_label(hdr, "Historical USD/ZWG exchange rate records.",
                   fg=TEXT2, bg=BG).pack(anchor="w")
        sf = tk.Frame(p, bg=BG)
        sf.pack(fill="x", padx=28, pady=14)
        self.hist_metrics = {}
        for key, lbl in [("total","Total Records"),("high","Session High"),
                          ("low","Session Low"),("avg","Average Rate")]:
            c = tk.Frame(sf, bg=SURFACE2, padx=16, pady=12)
            c.pack(side="left", fill="x", expand=True, padx=(0,12))
            make_label(c, lbl.upper(), fg=TEXT3, font=("Segoe UI", 8), bg=SURFACE2).pack(anchor="w")
            v = make_label(c, "—", fg=ACCENT, font=("Consolas", 14, "bold"), bg=SURFACE2)
            v.pack(anchor="w", pady=(4,0))
            self.hist_metrics[key] = v
        tb = tk.Frame(p, bg=BG)
        tb.pack(fill="x", padx=28, pady=(0,8))
        make_button(tb, "⬇ Export CSV", self._export_history_csv, bg=SURFACE3).pack(side="right")
        tf = tk.Frame(p, bg=BG)
        tf.pack(fill="both", expand=True, padx=28, pady=(0,24))
        cols = ("Timestamp","Rate (ZWG/USD)","Change","Source")
        self.hist_tree = ttk.Treeview(tf, columns=cols, show="headings",
                                      style="Dark.Treeview")
        for col, w in zip(cols, [220, 160, 120, 180]):
            self.hist_tree.heading(col, text=col)
            self.hist_tree.column(col, width=w, anchor="w")
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self.hist_tree.yview)
        self.hist_tree.configure(yscrollcommand=vsb.set)
        self.hist_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    def _refresh_history(self):
        hist = self.db.get_rate_history()
        for item in self.hist_tree.get_children():
            self.hist_tree.delete(item)
        if not hist:
            self.hist_tree.insert("", "end", values=("No records yet","—","—","—"))
            return
        rates = [h["rate"] for h in hist]
        self.hist_metrics["total"].configure(text=str(len(hist)))
        self.hist_metrics["high"].configure(text=f"{max(rates):.2f}")
        self.hist_metrics["low"].configure(text=f"{min(rates):.2f}")
        self.hist_metrics["avg"].configure(text=f"{sum(rates)/len(rates):.2f}")
        for i, h in enumerate(hist):
            prev  = hist[i+1]["rate"] if i+1 < len(hist) else None
            delta = (f"▲ {h['rate']-prev:.2f}" if prev and h["rate"] > prev else
                     f"▼ {prev-h['rate']:.2f}" if prev and h["rate"] < prev else "—")
            # Parse stored timestamp and reformat to match app display (dd Mon YYYY HH:MM:SS)
            try:
                dt  = datetime.strptime(h["fetched_at"], "%Y-%m-%d %H:%M:%S")
                ts  = dt.strftime("%d %b %Y  %H:%M:%S")
            except Exception:
                ts  = h["fetched_at"]
            self.hist_tree.insert("", "end", values=(
                ts, f"{h['rate']:.4f}", delta, h["source"]
            ))

    def _export_history_csv(self):
        hist = self.db.get_rate_history()
        if not hist:
            messagebox.showinfo("No Data", "No rate history to export.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                             filetypes=[("CSV","*.csv")],
                                             initialfile="rate_history.csv")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp","Rate (ZWG/USD)","Source"])
            for h in hist:
                writer.writerow([h["fetched_at"], f"{h['rate']:.2f}", h["source"]])
        messagebox.showinfo("Exported", f"Saved to {path}")

    # ────── INTEGRATION ───────────────────────────────
    def _build_integration(self):
        p = self.pages["integration"]
        p.configure(bg=BG)
        hdr = tk.Frame(p, bg=BG)
        hdr.pack(fill="x", padx=28, pady=(24,0))
        make_label(hdr, "POS Integration", font=("Segoe UI", 20, "bold"), bg=BG).pack(anchor="w")
        make_label(hdr, "Connect Rate-Price Sync to Point-of-Sale and inventory systems",
                   fg=TEXT2, bg=BG).pack(anchor="w")

        self._readonly_banner(p)

        cfg = tk.Frame(p, bg=SURFACE, padx=20, pady=16)
        cfg.pack(fill="x", padx=28, pady=14)
        make_label(cfg, "WEBHOOK CONFIGURATION", fg=TEXT3,
                   font=("Segoe UI", 8, "bold"), bg=SURFACE).pack(anchor="w", pady=(0,10))
        make_label(cfg, "POS Webhook URL (POST endpoint that receives price updates)",
                   fg=TEXT2, bg=SURFACE, font=FONT_SMALL).pack(anchor="w", pady=(0,4))
        self.int_webhook_var = tk.StringVar()
        row1 = tk.Frame(cfg, bg=SURFACE)
        row1.pack(fill="x")
        entry_state = "normal" if self._is_admin() else "disabled"
        make_entry(row1, textvariable=self.int_webhook_var, width=50,
                   state=entry_state).pack(side="left")
        if self._is_admin():
            make_button(row1, "Save", self._save_webhook, bg=SURFACE3).pack(side="left", padx=8)
        make_label(cfg,
                   "Leave blank to use file-based sync only. Compatible with Pastel, Sage, and custom REST APIs.",
                   fg=TEXT3, font=("Segoe UI", 8), bg=SURFACE).pack(anchor="w", pady=(6,0))
        actions = tk.Frame(p, bg=BG)
        actions.pack(fill="x", padx=28, pady=(0,14))
        if self._is_admin():
            for txt, cmd in [
                ("⇌ Push Prices to POS", self._push_pos),
                ("⬇ Write JSON Sync File", self._write_sync_file),
                ("📂 Open Sync Folder", self._open_sync_folder),
            ]:
                make_button(actions, txt, cmd, bg=SURFACE3).pack(side="left", padx=(0,10))
        else:
            make_button(actions, "📂 Open Sync Folder", self._open_sync_folder,
                        bg=SURFACE3).pack(side="left", padx=(0,10))
        self.int_log = tk.Text(p, bg=SURFACE2, fg=TEXT2, font=FONT_MONO,
                                relief="flat", height=12, wrap="word",
                                insertbackground=ACCENT)
        self.int_log.pack(fill="both", expand=True, padx=28, pady=(0,24))
        self.int_log.insert("end",
            "POS Integration Log\n"
            "─────────────────────────────────────────────────────────────\n"
            "This log records all sync activity between Rate-Price Sync and your\n"
            "Point-of-Sale or inventory system.\n\n"
            "HOW IT WORKS:\n"
            "  • Webhook push  — enter your POS REST endpoint URL above, save,\n"
            "                    then click 'Push Prices to POS'. Rate-Price Sync will\n"
            "                    POST all product prices in JSON to that URL.\n"
            "  • JSON sync file — no POS API? Click 'Write JSON Sync File' to\n"
            "                    export a file your inventory system can poll/import.\n"
            "  • Compatible with: Pastel, Sage Evolution, QuickBooks, or any\n"
            "                    system that accepts JSON via HTTP POST or file.\n"
            "─────────────────────────────────────────────────────────────\n"
            "System ready. Waiting for action...\n\n"
        )
        self.int_log.configure(state="disabled")

    def _log_int(self, msg: str):
        self.int_log.configure(state="normal")
        self.int_log.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.int_log.see("end")
        self.int_log.configure(state="disabled")

    def _save_webhook(self):
        if not self._require_admin("Saving webhook configuration"):
            return
        self.integration.pos_webhook_url = self.int_webhook_var.get().strip()
        self._log_int(f"Webhook set: {self.integration.pos_webhook_url or '(none)'}")

    def _push_pos(self):
        if not self._require_admin("Pushing prices to POS"):
            return
        r = self.current_rate.get()
        if not r:
            messagebox.showwarning("No Rate", "Fetch a live rate first.")
            return
        prods      = self.db.get_products()
        price_data = self.pricing.bulk_price(prods, r)
        result     = self.integration.push_to_pos(price_data, r)
        status = result.get("status", "unknown")
        if status == "skipped":
            self._log_int(
                "⚠  POS push skipped — no webhook URL configured.\n"
                "   → Enter a webhook URL above and click Save, then try again.\n"
                "   → Or use 'Write JSON Sync File' to export prices for manual import."
            )
        elif status == "ok":
            code = result.get("http_code", "?")
            self._log_int(f"✔  POS push successful — HTTP {code}. {len(prods)} products sent at rate {r:.4f}.")
        else:
            reason = result.get("reason", "unknown error")
            self._log_int(f"✖  POS push failed — {reason}\n   → Check the webhook URL and that your POS server is running.")

    def _write_sync_file(self):
        if not self._require_admin("Writing sync files"):
            return
        r = self.current_rate.get()
        if not r:
            messagebox.showwarning("No Rate", "Fetch a live rate first.")
            return
        prods    = self.db.get_products()
        pd_list  = self.pricing.bulk_price(prods, r)
        out_path = self.integration.write_sync_file(pd_list, r)
        self._log_int(f"Sync file written: {out_path}")

    def _open_sync_folder(self):
        import subprocess, sys
        folder = self.integration.export_dir
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])

    def _refresh_integration(self):
        self.int_webhook_var.set(self.integration.pos_webhook_url)

    # ────── SYSTEM METRICS ────────────────────────────
    def _build_metrics(self):
        p = self.pages["metrics"]
        p.configure(bg=BG)
        hdr = tk.Frame(p, bg=BG)
        hdr.pack(fill="x", padx=28, pady=(24,0))
        make_label(hdr, "System Metrics", font=("Segoe UI", 20, "bold"), bg=BG).pack(anchor="w")
        make_label(hdr, "Performance monitoring dashboard for system evaluation",
                   fg=TEXT2, bg=BG).pack(anchor="w")
        mf = tk.Frame(p, bg=BG)
        mf.pack(fill="x", padx=28, pady=14)
        self.m_cards = {}
        for key, lbl in [("uptime","System Uptime"),("fetches","Rate Fetches"),
                          ("avail","Availability"),("latency","Avg Latency"),
                          ("fails","Failed Fetches"),("products","Products Priced")]:
            c = tk.Frame(mf, bg=SURFACE2, padx=16, pady=12)
            c.pack(side="left", fill="x", expand=True, padx=(0,10))
            make_label(c, lbl.upper(), fg=TEXT3, font=("Segoe UI", 8), bg=SURFACE2).pack(anchor="w")
            v = make_label(c, "—", fg=ACCENT, font=("Consolas", 13, "bold"), bg=SURFACE2)
            v.pack(anchor="w", pady=(4,0))
            self.m_cards[key] = v
        src_frame = tk.Frame(p, bg=SURFACE, padx=18, pady=14)
        src_frame.pack(fill="x", padx=28, pady=(0,14))

        # Legend row
        legend = tk.Frame(src_frame, bg=SURFACE)
        legend.pack(fill="x", pady=(0,10))
        make_label(legend, "DATA SOURCES REGISTERED", fg=TEXT3,
                   font=("Segoe UI", 8, "bold"), bg=SURFACE).pack(side="left")
        make_label(legend, "  ●  Rate API (active failover chain)",
                   fg=ACCENT, font=("Segoe UI", 8), bg=SURFACE).pack(side="left", padx=(16,0))
        make_label(legend, "  ◆  Price intelligence / reference",
                   fg=INFO, font=("Segoe UI", 8), bg=SURFACE).pack(side="left", padx=(12,0))

        # Colour constants for this section
        RATE_BG = "#0a1829"   # dark blue tint for rate APIs
        REF_BG  = "#0c1a2e"   # slightly lighter blue for reference sources

        all_sources = {
            "ZimRate API (RBZ-sourced)":     ("https://zimrate.statotec.com",              True),
            "RBZ GitHub API":                ("https://rbz-exchange-rates-api.vercel.app", True),
            "RBZ Website (direct)":          ("https://www.rbz.co.zw",                    True),
            "ZimPriceCheck":                 ("https://zimpricecheck.com",                 True),
            "ZERA (Fuel Prices)":            ("https://www.zera.co.zw/",                  False),
            "TMPNP Online":                  ("https://www.tmpnponline.co.zw/",            False),
            "Halsteds Hardware":             ("https://www.halsteds.co.zw/",               False),
            "Electrosales":                  ("https://www.electrosales.co.zw/",           False),
            "ZimStat (CPI/Inflation)":       ("https://www.zimstat.co.zw/",               False),
            "Greenwood Pharmacy":            ("http://www.greenwoodpharmacy.co.zw/",       False),
        }
        priority = 1
        for name, (url, is_rate) in all_sources.items():
            bg_col  = RATE_BG if is_rate else REF_BG
            row     = tk.Frame(src_frame, bg=bg_col, padx=10, pady=5)
            row.pack(fill="x", pady=2)
            if is_rate:
                dot_text  = f"● #{priority}"
                dot_color = ACCENT
                name_fg   = "#d4f5e4"
                url_fg    = TEXT2
                tag_text  = "RATE API"
                tag_fg    = ACCENT
                priority += 1
            else:
                dot_text  = "◆"
                dot_color = INFO
                name_fg   = "#b0cfe8"
                url_fg    = "#6a9abb"
                tag_text  = "REFERENCE"
                tag_fg    = INFO
            make_label(row, dot_text,  fg=dot_color, bg=bg_col,
                       font=("Consolas", 9, "bold"), width=4).pack(side="left")
            make_label(row, name,      fg=name_fg, bg=bg_col,
                       font=("Segoe UI", 9, "bold"), width=28, anchor="w").pack(side="left")
            make_label(row, url,       fg=url_fg, bg=bg_col,
                       font=("Consolas", 8)).pack(side="left", padx=(8,0))
            make_label(row, tag_text,  fg=tag_fg, bg=bg_col,
                       font=("Segoe UI", 7, "bold")).pack(side="right", padx=(0,4))
        log_btn = tk.Frame(p, bg=BG)
        log_btn.pack(fill="x", padx=28, pady=(0,8))
        make_button(log_btn, "📂 Open Metrics Log", self._open_metrics_log, bg=SURFACE3).pack(side="left")
        make_button(log_btn, "↻ Refresh", self._refresh_metrics, bg=SURFACE3).pack(side="left", padx=8)

    def _refresh_metrics(self):
        s = self.metrics.summary()
        prods = self.db.get_products()
        r     = self.current_rate.get()
        self.m_cards["uptime"].configure(text=s["uptime"])
        self.m_cards["fetches"].configure(text=str(s["fetch_count"]))
        self.m_cards["avail"].configure(text=s["availability"])
        self.m_cards["latency"].configure(text=s["avg_latency"])
        self.m_cards["fails"].configure(text=str(s["fail_count"]))
        self.m_cards["products"].configure(text=str(len(prods)))

    def _open_metrics_log(self):
        import subprocess, sys
        if sys.platform == "win32":
            os.startfile(str(LOG_PATH))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(LOG_PATH)])
        else:
            subprocess.Popen(["xdg-open", str(LOG_PATH)])

    # ────── SETTINGS ───────────────────────────────────────
    def _build_settings(self):
        p = self.pages["settings"]
        p.configure(bg=BG)
        hdr = tk.Frame(p, bg=BG)
        hdr.pack(fill="x", padx=28, pady=(24,0))
        make_label(hdr, "Settings", font=("Segoe UI", 20, "bold"), bg=BG).pack(anchor="w")
        make_label(hdr, "Configure preferences, pricing rules, and data management.",
                   fg=TEXT2, bg=BG).pack(anchor="w")

        self._readonly_banner(p)

        top = tk.Frame(p, bg=BG)
        top.pack(fill="x", padx=28, pady=14)
        pref = tk.Frame(top, bg=SURFACE, padx=20, pady=16)
        pref.pack(side="left", fill="both", expand=True, padx=(0,12))
        make_label(pref, "PRICING ENGINE ", fg=TEXT3,
                   font=("Segoe UI", 8, "bold"), bg=SURFACE).pack(anchor="w", pady=(0,10))
        self.s_default_margin = tk.StringVar(value="10")
        make_label(pref, "Default Margin (%)", fg=TEXT2, bg=SURFACE,
                   font=FONT_SMALL).pack(anchor="w", pady=(6,2))
        entry_state = "normal" if self._is_admin() else "disabled"
        make_entry(pref, textvariable=self.s_default_margin, width=10,
                   state=entry_state).pack(anchor="w")
        make_label(pref, "Rounding Mode", fg=TEXT2, bg=SURFACE,
                   font=FONT_SMALL).pack(anchor="w", pady=(10,2))
        self.s_rounding = tk.StringVar(value="none")
        rb_state = "normal" if self._is_admin() else "disabled"
        for val, lbl in [("none","None (2dp)"),("nearest_5","Nearest 5"),("ceil_10","Ceil to 10")]:
            rb = tk.Radiobutton(pref, text=lbl, variable=self.s_rounding, value=val,
                                bg=SURFACE, fg=TEXT2, selectcolor=SURFACE3,
                                activebackground=SURFACE, activeforeground=ACCENT,
                                font=FONT_SMALL, command=self._apply_pricing_settings,
                                state=rb_state)
            rb.pack(anchor="w")
        if self._is_admin():
            make_accent_button(pref, "Apply", self._apply_pricing_settings).pack(anchor="w", pady=(12,0))
        data = tk.Frame(top, bg=SURFACE, padx=20, pady=16)
        data.pack(side="left", fill="both", expand=True)
        make_label(data, "DATA MANAGEMENT", fg=TEXT3,
                   font=("Segoe UI", 8, "bold"), bg=SURFACE).pack(anchor="w", pady=(0,10))
        self.s_prod_count = make_label(data, "Products: —", fg=TEXT2,
                                       bg=SURFACE, font=FONT_BODY)
        self.s_prod_count.pack(anchor="w", pady=(4,0))
        self.s_hist_count = make_label(data, "Rate records: —", fg=TEXT2,
                                       bg=SURFACE, font=FONT_BODY)
        self.s_hist_count.pack(anchor="w", pady=(4,0))
        make_label(data, f"DB: {DB_PATH}", fg=TEXT3,
                   font=("Segoe UI", 8), bg=SURFACE).pack(anchor="w", pady=(8,0))
        if self._is_admin():
            make_button(data, "Clear All Products", self._clear_products,
                        bg=SURFACE3, fg=DANGER).pack(anchor="w", pady=(14,4))
            make_button(data, "Clear Rate History", self._clear_history,
                        bg=SURFACE3, fg=DANGER).pack(anchor="w", pady=4)
        about = tk.Frame(p, bg=SURFACE, padx=20, pady=16)
        about.pack(fill="x", padx=28)
        make_label(about, "ABOUT", fg=TEXT3,
                   font=("Segoe UI", 8, "bold"), bg=SURFACE).pack(anchor="w", pady=(0,8))
        txt = ("Rate-Price Sync v2.0 — Automated Retail Pricing in Zimbabwe\n"
               "Multi-source exchange rate system with automated pricing engine.\n"
               "  Multi-source architecture  |  Automatic rate retrieval\n"
               "  Automated pricing engine   |  POS/inventory integration\n"
               "  Manager UI & pricing rules |  Live retail deployment\n"
               "  Performance metrics & evaluation log\n\n"
               f"Rate sources: ZimRate → RBZ GitHub API → RBZ Website → ZimPriceCheck → Fallback\n"
               f"Products: 149 across 11 categories  |  Data: Vietlas Systems")
        make_label(about, txt, fg=TEXT2, bg=SURFACE,
                   font=FONT_SMALL, justify="left").pack(anchor="w")

    def _build_users(self):
        """User management page — admin only."""
        p = self.pages["users"]
        p.configure(bg=BG)

        # ── Scrollable wrapper ────────────────────────────
        canvas = tk.Canvas(p, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(p, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=BG)
        canvas_window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_resize(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", _on_resize)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        hdr = tk.Frame(inner, bg=BG)
        hdr.pack(fill="x", padx=28, pady=(24, 0))
        make_label(hdr, "User Management", font=("Segoe UI", 20, "bold"), bg=BG).pack(anchor="w")
        make_label(hdr, "Manage users, approve requests, reset passwords, and suspend accounts.",
                   fg=TEXT2, bg=BG).pack(anchor="w")

        # ── Pending account requests ───────────────────────
        pend_card = tk.Frame(inner, bg=SURFACE, padx=24, pady=18)
        pend_card.pack(fill="x", padx=28, pady=(16, 0))
        hdr2 = tk.Frame(pend_card, bg=SURFACE)
        hdr2.pack(fill="x")
        make_label(hdr2, "⏳  PENDING ACCOUNT REQUESTS", fg=WARNING,
                   font=("Segoe UI", 8, "bold"), bg=SURFACE).pack(side="left", pady=(0, 10))
        make_button(hdr2, "↻ Refresh", self._refresh_pending,
                    bg=SURFACE3, fg=TEXT2).pack(side="right")

        pend_cols = ("ID", "Username", "Requested At")
        self._pend_tree = ttk.Treeview(pend_card, columns=pend_cols, show="headings",
                                       height=4, style="Dark.Treeview")
        for col, w in zip(pend_cols, [40, 180, 180]):
            self._pend_tree.heading(col, text=col)
            self._pend_tree.column(col, width=w, anchor="w")
        self._pend_tree.pack(fill="x")

        pend_act = tk.Frame(pend_card, bg=SURFACE)
        pend_act.pack(fill="x", pady=(8, 0))
        make_accent_button(pend_act, "✓  Approve", self._approve_pending).pack(side="left", padx=(0, 8))
        make_button(pend_act, "✗  Decline", self._decline_pending,
                    bg=SURFACE3, fg=DANGER).pack(side="left")
        self._pend_msg = make_label(pend_card, "", fg=ACCENT, font=FONT_SMALL, bg=SURFACE)
        self._pend_msg.pack(anchor="w", pady=(8, 0))

        # ── Add-user form ──────────────────────────────────
        form_card = tk.Frame(inner, bg=SURFACE, padx=24, pady=18)
        form_card.pack(fill="x", padx=28, pady=12)
        make_label(form_card, "ADD NEW USER", fg=TEXT3,
                   font=("Segoe UI", 8, "bold"), bg=SURFACE).pack(anchor="w", pady=(0, 12))

        row = tk.Frame(form_card, bg=SURFACE)
        row.pack(fill="x")

        col1 = tk.Frame(row, bg=SURFACE)
        col1.pack(side="left", padx=(0, 12))
        make_label(col1, "Username", fg=TEXT2, font=FONT_SMALL, bg=SURFACE).pack(anchor="w")
        self._nu_username = tk.StringVar()
        make_entry(col1, textvariable=self._nu_username, width=18).pack(anchor="w", pady=(4, 0))

        col2 = tk.Frame(row, bg=SURFACE)
        col2.pack(side="left", padx=(0, 12))
        make_label(col2, "Password", fg=TEXT2, font=FONT_SMALL, bg=SURFACE).pack(anchor="w")
        self._nu_password = tk.StringVar()
        make_entry(col2, textvariable=self._nu_password, width=20, show="●").pack(anchor="w", pady=(4, 0))

        col3 = tk.Frame(row, bg=SURFACE)
        col3.pack(side="left", padx=(0, 12))
        make_label(col3, "Role", fg=TEXT2, font=FONT_SMALL, bg=SURFACE).pack(anchor="w")
        self._nu_role = tk.StringVar(value="user")
        role_cb = ttk.Combobox(col3, textvariable=self._nu_role,
                               values=["user", "admin"], width=10, state="readonly")
        role_cb.pack(anchor="w", pady=(4, 0))

        col4 = tk.Frame(row, bg=SURFACE)
        col4.pack(side="left")
        make_label(col4, " ", fg=TEXT2, font=FONT_SMALL, bg=SURFACE).pack(anchor="w")
        make_accent_button(col4, "＋ Add User", self._add_user).pack(anchor="w", pady=(4, 0))

        self._users_msg = make_label(form_card, "", fg=ACCENT, font=FONT_SMALL, bg=SURFACE)
        self._users_msg.pack(anchor="w", pady=(10, 0))

        # ── Users table ───────────────────────────────────
        tbl_card = tk.Frame(inner, bg=SURFACE, padx=24, pady=18)
        tbl_card.pack(fill="x", padx=28, pady=(0, 28))
        make_label(tbl_card, "ALL USERS", fg=TEXT3,
                   font=("Segoe UI", 8, "bold"), bg=SURFACE).pack(anchor="w", pady=(0, 10))

        cols = ("ID", "Username", "Role", "Status", "Created", "Last Login")
        self._users_tree = ttk.Treeview(tbl_card, columns=cols, show="headings",
                                        height=10, style="Dark.Treeview")
        for col, w in zip(cols, [40, 140, 80, 90, 140, 140]):
            self._users_tree.heading(col, text=col)
            self._users_tree.column(col, width=w, anchor="w")
        self._users_tree.pack(fill="x")

        act_row = tk.Frame(tbl_card, bg=SURFACE)
        act_row.pack(fill="x", pady=(10, 0))
        make_button(act_row, "🔑  Reset to ChangeMe", self._reset_to_changeme,
                    bg=SURFACE3, fg=WARNING).pack(side="left", padx=(0, 8))
        make_button(act_row, "🔑  Change Password", self._change_selected_password,
                    bg=SURFACE3, fg=INFO).pack(side="left", padx=(0, 8))
        make_button(act_row, "⛔  Suspend", self._suspend_selected_user,
                    bg=SURFACE3, fg=DANGER).pack(side="left", padx=(0, 8))
        make_button(act_row, "✓  Unsuspend", self._unsuspend_selected_user,
                    bg=SURFACE3, fg=ACCENT).pack(side="left", padx=(0, 8))
        make_button(act_row, "🗑  Delete", self._delete_selected_user,
                    bg=SURFACE3, fg=DANGER).pack(side="left", padx=(0, 8))
        make_button(act_row, "↻  Refresh", self._refresh_users,
                    bg=SURFACE3, fg=TEXT2).pack(side="right")

    def _refresh_pending(self):
        if not hasattr(self, "_pend_tree"):
            return
        for item in self._pend_tree.get_children():
            self._pend_tree.delete(item)
        for u in self.db.get_pending_users():
            self._pend_tree.insert("", "end", values=(
                u["id"], u["username"], u["requested_at"] or "—"
            ))

    def _approve_pending(self):
        sel = self._pend_tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select a pending request.")
            return
        row = self._pend_tree.item(sel[0])["values"]
        pid, uname = row[0], row[1]
        if self.db.approve_pending_user(pid):
            self._pend_msg.configure(text=f"✓  User '{uname}' approved and created.", fg=ACCENT)
            self._refresh_pending()
            self._refresh_users()
        else:
            self._pend_msg.configure(text=f"⚠  Username '{uname}' already exists.", fg=DANGER)

    def _decline_pending(self):
        sel = self._pend_tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select a pending request.")
            return
        row = self._pend_tree.item(sel[0])["values"]
        pid, uname = row[0], row[1]
        if messagebox.askyesno("Decline Request", f"Decline account request for '{uname}'?"):
            self.db.decline_pending_user(pid)
            self._pend_msg.configure(text=f"✗  Request from '{uname}' declined.", fg=WARNING)
            self._refresh_pending()

    def _refresh_users(self):
        if not hasattr(self, "_users_tree"):
            return
        for item in self._users_tree.get_children():
            self._users_tree.delete(item)
        for u in self.db.get_users():
            if u["suspended"]:
                status = "⛔ Suspended"
            elif u["is_active"]:
                status = "Active"
            else:
                status = "Disabled"
            self._users_tree.insert("", "end", values=(
                u["id"], u["username"], u["role"], status,
                u["created_at"] or "—", u["last_login"] or "Never"
            ))

    def _add_user(self):
        username = self._nu_username.get().strip()
        password = self._nu_password.get()
        role     = self._nu_role.get()
        if not username or not password:
            self._users_msg.configure(text="⚠  Username and password are required.", fg=DANGER)
            return
        if len(password) < 6:
            self._users_msg.configure(text="⚠  Password must be at least 6 characters.", fg=DANGER)
            return
        if self.db.add_user(username, password, role):
            self._nu_username.set("")
            self._nu_password.set("")
            self._users_msg.configure(text=f"✓  User '{username}' added successfully.", fg=ACCENT)
            self._refresh_users()
        else:
            self._users_msg.configure(text=f"⚠  Username '{username}' already exists.", fg=DANGER)

    def _get_selected_user(self):
        sel = self._users_tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select a user from the list.")
            return None
        return self._users_tree.item(sel[0])["values"]

    def _reset_to_changeme(self):
        """Admin resets selected user's password to ChangeMe (forces change on next login)."""
        row = self._get_selected_user()
        if not row:
            return
        uid, uname = row[0], row[1]
        if uname == "admin":
            messagebox.showerror("Denied", "Cannot reset the main administrator account.")
            return
        if messagebox.askyesno("Reset Password",
                               f"Reset '{uname}' password to 'ChangeMe'?\n\n"
                               f"They will be required to set a new password on next login."):
            self.db.reset_password_to_changeme(uid)
            self._users_msg.configure(
                text=f"✓  Password for '{uname}' reset to 'ChangeMe'. Force-change enabled.",
                fg=WARNING)

    def _change_selected_password(self):
        row = self._get_selected_user()
        if not row:
            return
        uid, uname = row[0], row[1]
        if uname == "admin" and self._session.get("username") != "admin":
            messagebox.showerror("Denied", "Cannot change the admin password from this account.")
            return
        dlg = tk.Toplevel(self)
        dlg.title("Change Password")
        dlg.geometry("380x280")
        dlg.configure(bg=SURFACE)
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()
        make_label(dlg, f"Set new password for '{uname}'",
                   fg=TEXT, font=FONT_BOLD, bg=SURFACE).pack(padx=24, pady=(20, 4), anchor="w")

        make_label(dlg, "New Password", fg=TEXT2, font=FONT_SMALL, bg=SURFACE).pack(padx=24, anchor="w")
        pw_var = tk.StringVar()
        e1 = make_entry(dlg, textvariable=pw_var, width=28, show="●")
        e1.pack(padx=24, anchor="w", pady=(4, 8))

        make_label(dlg, "Confirm Password", fg=TEXT2, font=FONT_SMALL, bg=SURFACE).pack(padx=24, anchor="w")
        pw2_var = tk.StringVar()
        e2 = make_entry(dlg, textvariable=pw2_var, width=28, show="●")
        e2.pack(padx=24, anchor="w", pady=(4, 6))
        e1.focus_set()

        msg = make_label(dlg, "", fg=DANGER, font=FONT_SMALL, bg=SURFACE)
        msg.pack(padx=24, pady=(4, 0), anchor="w")

        def _do_change():
            pw = pw_var.get()
            pw2 = pw2_var.get()
            if len(pw) < 6:
                msg.configure(text="⚠  Minimum 6 characters required.")
                return
            if pw != pw2:
                msg.configure(text="⚠  Passwords do not match.")
                return
            self.db.update_user_password(uid, pw, force_change=False)
            dlg.destroy()
            self._users_msg.configure(text=f"✓  Password updated for '{uname}'.", fg=ACCENT)

        make_accent_button(dlg, "Update Password", _do_change).pack(padx=24, pady=12, anchor="w")
        e2.bind("<Return>", lambda e: _do_change())

    def _suspend_selected_user(self):
        row = self._get_selected_user()
        if not row:
            return
        uid, uname = row[0], row[1]
        if uname == "admin":
            messagebox.showerror("Denied", "Cannot suspend the main administrator account.")
            return
        if messagebox.askyesno("Suspend User",
                               f"Suspend '{uname}'?\n\nThey will not be able to log in until unsuspended."):
            self.db.suspend_user(uid, True)
            self._refresh_users()
            self._users_msg.configure(text=f"⛔  User '{uname}' has been suspended.", fg=DANGER)

    def _unsuspend_selected_user(self):
        row = self._get_selected_user()
        if not row:
            return
        uid, uname = row[0], row[1]
        self.db.suspend_user(uid, False)
        self._refresh_users()
        self._users_msg.configure(text=f"✓  User '{uname}' has been unsuspended.", fg=ACCENT)

    def _toggle_selected_user(self):
        row = self._get_selected_user()
        if not row:
            return
        uid, uname = row[0], row[1]
        if uname == "admin":
            messagebox.showerror("Denied", "Cannot disable the main administrator account.")
            return
        self.db.toggle_user_active(uid)
        self._refresh_users()
        self._users_msg.configure(text=f"✓  User '{uname}' status toggled.", fg=ACCENT)

    def _delete_selected_user(self):
        row = self._get_selected_user()
        if not row:
            return
        uid, uname = row[0], row[1]
        if uname == "admin":
            messagebox.showerror("Denied", "Cannot delete the main administrator account.")
            return
        if messagebox.askyesno("Confirm Delete", f"Permanently delete user '{uname}'?"):
            self.db.delete_user(uid)
            self._refresh_users()
            self._users_msg.configure(text=f"✓  User '{uname}' deleted.", fg=ACCENT)

    def _build_about(self):
        p = self.pages["about"]
        p.configure(bg=BG)
        hdr = tk.Frame(p, bg=BG)
        hdr.pack(fill="x", padx=28, pady=(24, 0))
        make_label(hdr, "About Us", font=("Segoe UI", 20, "bold"), bg=BG).pack(anchor="w")
        make_label(hdr, "Rate-Price Sync — Automated Retail Pricing in Zimbabwe",
                   fg=TEXT2, bg=BG).pack(anchor="w")

        # Contact card
        card = tk.Frame(p, bg=SURFACE, padx=28, pady=24)
        card.pack(fill="x", padx=28, pady=24)

        make_label(card, "CONTACT", fg=TEXT3,
                   font=("Segoe UI", 8, "bold"), bg=SURFACE).pack(anchor="w", pady=(0, 14))

        name_row = tk.Frame(card, bg=SURFACE)
        name_row.pack(anchor="w", pady=(0, 8))
        make_label(name_row, "👤", fg=ACCENT, bg=SURFACE,
                   font=("Segoe UI", 14)).pack(side="left", padx=(0, 10))
        make_label(name_row, "Tinotenda V Nzvenge", fg=TEXT, bg=SURFACE,
                   font=("Segoe UI", 13, "bold")).pack(side="left")

        phone_row = tk.Frame(card, bg=SURFACE)
        phone_row.pack(anchor="w", pady=(0, 8))
        make_label(phone_row, "📞", fg=ACCENT, bg=SURFACE,
                   font=("Segoe UI", 14)).pack(side="left", padx=(0, 10))
        make_label(phone_row, "+263 784746656", fg=ACCENT, bg=SURFACE,
                   font=("Consolas", 12, "bold")).pack(side="left")

        tk.Frame(card, bg=BORDER, height=1).pack(fill="x", pady=16)

        make_label(card, "SYSTEM", fg=TEXT3,
                   font=("Segoe UI", 8, "bold"), bg=SURFACE).pack(anchor="w", pady=(0, 10))
        sys_txt = ("Rate-Price Sync v2.0 — Automated Retail Pricing in Zimbabwe\n"
                   "Multi-source exchange rate system with automated pricing engine.\n"
                   "Rate sources: ZimRate → RBZ GitHub API → RBZ Website → ZimPriceCheck → Fallback")
        make_label(card, sys_txt, fg=TEXT2, bg=SURFACE,
                   font=FONT_SMALL, justify="left").pack(anchor="w")

    def _apply_pricing_settings(self):
        if not self._require_admin("Changing pricing settings"):
            return
        try:
            self.pricing.global_margin  = float(self.s_default_margin.get() or 10)
        except ValueError:
            pass
        self.pricing.rounding_mode = self.s_rounding.get()
        self._refresh_products()

    def _refresh_settings(self):
        prods = self.db.get_products()
        hist  = self.db.get_rate_history()
        self.s_prod_count.configure(text=f"Products: {len(prods)}")
        self.s_hist_count.configure(text=f"Rate records: {len(hist)}")

    def _clear_products(self):
        if not self._require_admin("Clearing products"):
            return
        if messagebox.askyesno("Confirm", "Delete ALL products? Cannot be undone."):
            self.db.clear_products()
            self._refresh_settings()
            messagebox.showinfo("Done", "All products cleared.")

    def _clear_history(self):
        if not self._require_admin("Clearing rate history"):
            return
        if messagebox.askyesno("Confirm", "Clear all rate history?"):
            self.db.clear_history()
            self._refresh_settings()
            messagebox.showinfo("Done", "Rate history cleared.")

    # ────── RATE FETCHING ──────────────────────────────────
    def _auto_fetch_rate(self):
        self.rate_service.fetch(self._on_rate_success, self._on_rate_error)

    def _fetch_rate_manual(self):
        if hasattr(self, "rate_big"):
            self.rate_big.configure(text="…")
        self.status_lbl.configure(text="Fetching latest RBZ rate…")
        self.rate_service.fetch(self._on_rate_success, self._on_rate_error)

    def _on_rate_success(self, result):
        self.after(0, lambda: self._apply_rate(result, success=True))

    def _on_rate_error(self, result):
        self.after(0, lambda: self._apply_rate(result, success=False))

    def _apply_rate(self, result: RateResult, success: bool = True):
        self.metrics.record_fetch(result.source, result.latency_ms, success)
        self.current_rate.set(result.mid)
        self.current_result = result
        self.rate_source.set(result.source)
        self.rate_time = result.fetched_at
        self.db.save_rate(result.mid, result.source, result.fetched_at)

        self.sb_rate_label.configure(text=f"{result.mid:.4f} {result.currency}")
        self.sb_source_label.configure(text=result.source[:30])
        self.sb_time_label.configure(text=self.rate_time.strftime("%H:%M:%S"))

        self._refresh_dashboard()
        self._refresh_rates_page()
        self._refresh_products()
        self._refresh_converter()

    def _on_close(self):
        self.db.close()
        self.destroy()


if __name__ == "__main__":
    app = LoginApp()
    app.mainloop()
