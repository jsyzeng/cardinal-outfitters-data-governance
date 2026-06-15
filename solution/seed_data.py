"""
seed_data.py — Cardinal Outfitters federated retail platform (synthetic seed).

PROVIDED FILE. Students do not edit this. It authors a small, deterministic,
*deliberately imperfect* dataset across the four domains and a Glue-style metadata
catalog with governance-tag gaps and cross-domain semantic conflicts.

Everything is local: tables land in a SQLite database (the "data lake"), and the
metadata catalog is an in-memory structure (the "Glue Data Catalog" analog). Nothing
here calls AWS. The governance_toolkit reads what this module builds.

Determinism: a fixed RNG seed means every student sees identical data, so graders see
identical outputs. Re-running rebuilds the same lake from scratch.
"""
from __future__ import annotations

import os
import random
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

SEED = 42
EPOCH = datetime(2025, 1, 1, 0, 0, 0)  # fixed "now-ish" anchor; no wall-clock reads

# ----------------------------------------------------------------------------- #
# Metadata catalog (Glue Data Catalog analog)
# ----------------------------------------------------------------------------- #

@dataclass
class ColumnMeta:
    name: str
    type: str
    classification: Optional[str] = None   # PII | SENSITIVE | PUBLIC | None(=gap)
    description: str = ""


@dataclass
class TableMeta:
    name: str
    domain: str
    columns: list[ColumnMeta]
    owner: Optional[str] = None            # None == governance gap to be found
    classification: Optional[str] = None   # table-level data class; None == gap
    retention: Optional[str] = None        # e.g. "P7Y"; None == gap
    description: str = ""
    lf_tags: dict[str, str] = field(default_factory=dict)  # student-assigned at runtime

    def column(self, name: str) -> Optional[ColumnMeta]:
        return next((c for c in self.columns if c.name == name), None)


@dataclass
class Catalog:
    """The Glue-style metadata catalog: tables, their columns, governance params."""
    database: str
    tables: dict[str, TableMeta]
    # Known cross-domain semantic conflicts seeded into the platform. Each entry is a
    # human-readable description of two domains disagreeing about the same concept.
    semantic_conflicts: list[dict] = field(default_factory=list)

    def table(self, name: str) -> TableMeta:
        return self.tables[name]


# ----------------------------------------------------------------------------- #
# Synthetic value pools (no Faker dependency)
# ----------------------------------------------------------------------------- #

_FIRST = ["Ava", "Liam", "Noah", "Emma", "Oliver", "Sophia", "Mateo", "Mia", "Lucas",
          "Amara", "Yuki", "Priya", "Omar", "Freya", "Diego", "Nina", "Kofi", "Lena",
          "Arjun", "Chloe", "Hassan", "Ingrid", "Tariq", "Wei", "Rosa"]
_LAST = ["Patel", "Nguyen", "Garcia", "Smith", "Okafor", "Kim", "Rossi", "Haddad",
         "Andersson", "Silva", "Khan", "Olsen", "Mendez", "Cohen", "Tanaka", "Murphy",
         " Feldt".strip(), "Ahmed", "Costa", "Berg"]
_REGIONS = ["EU", "NA", "APAC", "LATAM"]
_REGION_COUNTRY = {"EU": ["DE", "FR", "SE", "ES"], "NA": ["US", "CA"],
                   "APAC": ["JP", "AU", "IN"], "LATAM": ["BR", "MX"]}
_TIERS = ["bronze", "silver", "gold", "platinum"]
_CATEGORIES = ["tents", "footwear", "apparel", "packs", "climbing", "nutrition"]
_CARRIERS = ["DHL", "FedEx", "UPS", "GLS", "PostNord"]
_CHANNELS = ["email", "sms", "push", "social"]
_SEGMENTS = ["lapsed", "vip", "new", "seasonal", "high_value"]
_RETURN_REASONS = ["size", "defective", "changed_mind", "late_delivery", "wrong_item"]


def _email(first: str, last: str, rng: random.Random, dirty: bool = False) -> str:
    sep = rng.choice([".", "_", ""])
    dom = rng.choice(["gmail.com", "outlook.com", "proton.me", "cardinalmail.co"])
    addr = f"{first}{sep}{last}@{dom}".lower()
    if dirty:
        # invalid-by-construction addresses (validity failures the quality suite finds)
        addr = rng.choice([addr.replace("@", "_at_"), addr.replace(".", ""),
                           first.lower() + "@", "n/a"])
    return addr


def _phone(rng: random.Random, region: str, dirty: bool = False) -> str:
    cc = {"EU": "+49", "NA": "+1", "APAC": "+81", "LATAM": "+55"}[region]
    num = "".join(str(rng.randint(0, 9)) for _ in range(9))
    if dirty:
        return rng.choice(["", "555", num])  # missing/short → validity failure
    return f"{cc}{num}"


# ----------------------------------------------------------------------------- #
# Build
# ----------------------------------------------------------------------------- #

def _connect(db_path: str) -> sqlite3.Connection:
    if db_path != ":memory:" and os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    return conn


def build(db_path: str = "cardinal.db") -> tuple[sqlite3.Connection, Catalog]:
    """Build the Cardinal Outfitters lake + catalog. Returns (sqlite_conn, Catalog).

    The data is deterministic and deliberately imperfect: governance-tag gaps,
    cross-domain semantic conflicts, and quality defects are seeded on purpose so the
    audit (Step 2), quality (Step 4), MDM (Step 5), and access (Step 7) exercises have
    something real to find.
    """
    rng = random.Random(SEED)
    conn = _connect(db_path)
    cur = conn.cursor()

    # --- Customer Identity & Loyalty ------------------------------------------ #
    cur.execute("""
        CREATE TABLE customer (
            customer_id      INTEGER PRIMARY KEY,
            full_name        TEXT,
            email            TEXT,
            phone            TEXT,
            region           TEXT,
            country          TEXT,
            loyalty_tier     TEXT,
            marketing_consent INTEGER,   -- 0/1; loyalty domain's view of consent
            created_ts       TEXT
        )""")
    n_customers = 300
    # Unique identities by construction: draw distinct (first, last) combos so the only
    # near-duplicates in the data are the ones we seed deliberately below. Email local
    # part is "first.last", unique because the name is unique — so coincidental
    # same-name / same-email collisions don't exist.
    combos = [(f, l) for f in _FIRST for l in _LAST]
    rng.shuffle(combos)
    base = combos[:n_customers]
    customers = []
    clean_email_ids = []
    for cid in range(1, n_customers + 1):
        first, last = base[cid - 1]
        region = rng.choice(_REGIONS)
        country = rng.choice(_REGION_COUNTRY[region])
        dom = rng.choice(["gmail.com", "outlook.com", "proton.me", "cardinalmail.co"])
        dirty_email = rng.random() < 0.06
        # ~6% dirty email, ~5% dirty phone → validity failures for the quality suite
        email = ("n/a" if dirty_email else f"{first}.{last}@{dom}").lower()
        phone = _phone(rng, region, dirty=(rng.random() < 0.05))
        tier = rng.choice(_TIERS)
        consent = 1 if rng.random() < 0.6 else 0
        # timeliness defect: a few records back-dated far in the past (stale)
        days_ago = rng.randint(0, 540) if rng.random() > 0.04 else rng.randint(2000, 4000)
        created = EPOCH - timedelta(days=days_ago, hours=rng.randint(0, 23))
        customers.append((cid, f"{first} {last}", email, phone, region, country,
                          tier, consent, created.isoformat()))
        if not dirty_email:
            clean_email_ids.append(cid)

    # Seed exactly 8 deliberate duplicate persons (the MDM exercise):
    #   - 2 clear duplicates: identical email + identical name  -> auto-merge band
    #   - 6 ambiguous near-duplicates: same person, email VARIANT (domain swap or an
    #     inserted digit) and/or a whitespace name variant -> steward-review band
    dup_sources = rng.sample(clean_email_ids, 8)
    for k, cid in enumerate(dup_sources):
        src = customers[cid - 1]
        new_id = n_customers + k + 1
        name, email = src[1], src[2]
        if k < 2:
            pass  # exact duplicate (same name + same email) -> high-confidence auto-merge
        else:
            lp, dom = email.split("@", 1)
            if k % 2 == 0:                       # domain-swap variant
                newdom = "outlook.com" if dom != "outlook.com" else "gmail.com"
                email = f"{lp}@{newdom}"
            else:                                # inserted-digit variant
                email = f"{lp}{rng.randint(1, 9)}@{dom}"
            if rng.random() < 0.5:
                name = name.replace(" ", "  ")   # whitespace name variant
        customers.append((new_id, name, email, src[3], src[4], src[5],
                          rng.choice(_TIERS), src[7], src[8]))
    cur.executemany("INSERT INTO customer VALUES (?,?,?,?,?,?,?,?,?)", customers)
    n_total_customers = len(customers)

    # --- E-commerce Orders ---------------------------------------------------- #
    cur.execute("""
        CREATE TABLE orders (
            order_id     INTEGER PRIMARY KEY,
            customer_id  INTEGER,
            order_ts     TEXT,
            status       TEXT,
            amount       REAL,
            currency     TEXT
        )""")
    cur.execute("""
        CREATE TABLE order_returns (
            return_id INTEGER PRIMARY KEY,
            order_id  INTEGER,
            reason    TEXT,
            qty       INTEGER
        )""")
    n_orders = 1200
    orders, returns = [], []
    rid = 1
    for oid in range(1, n_orders + 1):
        cid = rng.randint(1, n_customers)
        days_ago = rng.randint(0, 420)
        ots = EPOCH - timedelta(days=days_ago, hours=rng.randint(0, 23))
        status = rng.choices(["delivered", "shipped", "processing", "cancelled", "returned"],
                             weights=[55, 15, 12, 8, 10])[0]
        amount = round(rng.uniform(12, 680), 2)
        # accuracy defect: ~1.5% negative amounts
        if rng.random() < 0.015:
            amount = -amount
        orders.append((oid, cid, ots.isoformat(), status, amount, "USD"))
        if status == "returned":
            returns.append((rid, oid, rng.choice(_RETURN_REASONS), rng.randint(1, 3)))
            rid += 1
    cur.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?)", orders)
    cur.executemany("INSERT INTO order_returns VALUES (?,?,?,?)", returns)

    # --- Inventory & Fulfillment ---------------------------------------------- #
    cur.execute("""
        CREATE TABLE supplier (
            supplier_id   INTEGER PRIMARY KEY,
            name          TEXT,
            country       TEXT,
            esg_rating    TEXT
        )""")
    cur.execute("""
        CREATE TABLE product (
            product_id        INTEGER PRIMARY KEY,
            name              TEXT,
            category          TEXT,          -- completeness defect: some NULL
            supplier_id       INTEGER,
            unit_cost         REAL,
            sustainability_class TEXT         -- mandatory-attr gap: often NULL
        )""")
    cur.execute("""
        CREATE TABLE shipment (
            shipment_id  INTEGER PRIMARY KEY,
            order_id     INTEGER,
            carrier      TEXT,
            ship_ts      TEXT,
            carbon_kg    REAL                 -- CSRD: per-shipment carbon estimate
        )""")
    n_suppliers = 40
    for sid in range(1, n_suppliers + 1):
        cur.execute("INSERT INTO supplier VALUES (?,?,?,?)",
                    (sid, f"Supplier-{sid:02d}", rng.choice(sum(_REGION_COUNTRY.values(), [])),
                     rng.choice(["A", "B", "C", None])))
    n_products = 200
    for pid in range(1, n_products + 1):
        cat = rng.choice(_CATEGORIES)
        if rng.random() < 0.08:        # completeness defect: missing category
            cat = None
        sustainability = rng.choice(["recycled", "organic", "standard"])
        if rng.random() < 0.45:        # mandatory-attr gap: often missing
            sustainability = None
        cur.execute("INSERT INTO product VALUES (?,?,?,?,?,?)",
                    (pid, f"{rng.choice(_CATEGORIES).title()} Model {pid}", cat,
                     rng.randint(1, n_suppliers), round(rng.uniform(5, 240), 2),
                     sustainability))
    # shipments: one per non-cancelled order (mostly)
    sid = 1
    for (oid, cid, ots, status, amount, cur_code) in orders:
        if status == "cancelled":
            continue
        # carbon: most in kg; a 3% slice mistakenly stored in grams (unit conflict →
        # the Step 8 traceability/reconciliation defect and the Step 6 "breach")
        carbon = round(rng.uniform(0.4, 9.5), 3)
        if rng.random() < 0.03:
            carbon = carbon * 1000  # grams-not-kg unit error
        ship_ts = (datetime.fromisoformat(ots) + timedelta(days=rng.randint(1, 5))).isoformat()
        cur.execute("INSERT INTO shipment VALUES (?,?,?,?,?)",
                    (sid, oid, rng.choice(_CARRIERS), ship_ts, carbon))
        sid += 1

    # --- Marketing & Campaigns ------------------------------------------------ #
    cur.execute("""
        CREATE TABLE campaign (
            campaign_id INTEGER PRIMARY KEY,
            name        TEXT,
            channel     TEXT,
            start_date  TEXT,
            end_date    TEXT
        )""")
    cur.execute("""
        CREATE TABLE campaign_membership (
            membership_id INTEGER PRIMARY KEY,
            campaign_id   INTEGER,
            cust_ref      TEXT,        -- SEMANTIC CONFLICT: marketing keys on email, not customer_id
            segment       TEXT,
            mkt_consent   INTEGER      -- SEMANTIC CONFLICT: marketing's own consent flag
        )""")
    n_campaigns = 20
    for cpid in range(1, n_campaigns + 1):
        start = EPOCH - timedelta(days=rng.randint(30, 400))
        end = start + timedelta(days=rng.randint(7, 60))
        cur.execute("INSERT INTO campaign VALUES (?,?,?,?,?)",
                    (cpid, f"Campaign {cpid}", rng.choice(_CHANNELS),
                     start.date().isoformat(), end.date().isoformat()))
    mid = 1
    for _ in range(800):
        cpid = rng.randint(1, n_campaigns)
        cust = customers[rng.randint(0, n_customers - 1)]
        # marketing references customers by EMAIL, not customer_id (the federation conflict)
        cust_ref = cust[2]
        # marketing's consent disagrees with loyalty's ~20% of the time (consistency defect)
        loyalty_consent = cust[7]
        mkt_consent = loyalty_consent if rng.random() > 0.20 else (1 - loyalty_consent)
        cur.execute("INSERT INTO campaign_membership VALUES (?,?,?,?,?)",
                    (mid, cpid, cust_ref, rng.choice(_SEGMENTS), mkt_consent))
        mid += 1

    conn.commit()

    catalog = _build_catalog()
    return conn, catalog


def _build_catalog() -> Catalog:
    """The Glue-style metadata catalog, with deliberate governance gaps.

    Gaps seeded (these are what Step 2's audit must surface):
      - orders:           no owner, no retention
      - order_returns:    no owner, no classification, no retention
      - product:          no classification, no retention
      - shipment:         no owner
      - campaign_membership: no owner, no classification, no retention
      - customer.phone:   classification left NULL (a PII column not tagged PII)
    """
    C = ColumnMeta
    tables = {
        "customer": TableMeta(
            "customer", "Customer Identity & Loyalty",
            [C("customer_id", "INTEGER", "PUBLIC", "surrogate key"),
             C("full_name", "TEXT", "PII", "customer name"),
             C("email", "TEXT", "PII", "primary contact email"),
             C("phone", "TEXT", None, "contact phone"),            # GAP: PII not tagged
             C("region", "TEXT", "PUBLIC", "service region; drives row policy"),
             C("country", "TEXT", "PUBLIC"),
             C("loyalty_tier", "TEXT", "PUBLIC"),
             C("marketing_consent", "INTEGER", "SENSITIVE", "GDPR consent (loyalty view)"),
             C("created_ts", "TEXT", "PUBLIC")],
            owner="customer-identity@cardinal.example",
            classification="PII", retention="P7Y",
            description="Master customer profile, loyalty domain of record."),
        "orders": TableMeta(
            "orders", "E-commerce Orders",
            [C("order_id", "INTEGER", "PUBLIC"),
             C("customer_id", "INTEGER", "PUBLIC", "FK to customer (loyalty key)"),
             C("order_ts", "TEXT", "PUBLIC"),
             C("status", "TEXT", "PUBLIC"),
             C("amount", "REAL", "SENSITIVE"),
             C("currency", "TEXT", "PUBLIC")],
            owner=None,                                            # GAP
            classification="SENSITIVE", retention=None,            # GAP
            description="Purchase events."),
        "order_returns": TableMeta(
            "order_returns", "E-commerce Orders",
            [C("return_id", "INTEGER", "PUBLIC"),
             C("order_id", "INTEGER", "PUBLIC"),
             C("reason", "TEXT", None),
             C("qty", "INTEGER", "PUBLIC")],
            owner=None, classification=None, retention=None,       # GAP x3
            description="Order returns."),
        "supplier": TableMeta(
            "supplier", "Inventory & Fulfillment",
            [C("supplier_id", "INTEGER", "PUBLIC"),
             C("name", "TEXT", "PUBLIC"),
             C("country", "TEXT", "PUBLIC"),
             C("esg_rating", "TEXT", "PUBLIC", "ESG supplier rating; CSRD input")],
            owner="inventory-fulfillment@cardinal.example",
            classification="PUBLIC", retention="P5Y"),
        "product": TableMeta(
            "product", "Inventory & Fulfillment",
            [C("product_id", "INTEGER", "PUBLIC"),
             C("name", "TEXT", "PUBLIC"),
             C("category", "TEXT", "PUBLIC", "mandatory per inventory standard"),
             C("supplier_id", "INTEGER", "PUBLIC"),
             C("unit_cost", "REAL", "SENSITIVE"),
             C("sustainability_class", "TEXT", None, "CSRD attribute; often missing")],
            owner="inventory-fulfillment@cardinal.example",
            classification=None, retention=None),                  # GAP x2
        "shipment": TableMeta(
            "shipment", "Inventory & Fulfillment",
            [C("shipment_id", "INTEGER", "PUBLIC"),
             C("order_id", "INTEGER", "PUBLIC"),
             C("carrier", "TEXT", "PUBLIC"),
             C("ship_ts", "TEXT", "PUBLIC"),
             C("carbon_kg", "REAL", "PUBLIC", "per-shipment carbon (kg); CSRD source")],
            owner=None,                                            # GAP
            classification="PUBLIC", retention="P10Y"),
        "campaign": TableMeta(
            "campaign", "Marketing & Campaigns",
            [C("campaign_id", "INTEGER", "PUBLIC"),
             C("name", "TEXT", "PUBLIC"),
             C("channel", "TEXT", "PUBLIC"),
             C("start_date", "TEXT", "PUBLIC"),
             C("end_date", "TEXT", "PUBLIC")],
            owner="marketing@cardinal.example",
            classification="PUBLIC", retention="P3Y"),
        "campaign_membership": TableMeta(
            "campaign_membership", "Marketing & Campaigns",
            [C("membership_id", "INTEGER", "PUBLIC"),
             C("campaign_id", "INTEGER", "PUBLIC"),
             C("cust_ref", "TEXT", "PII", "customer EMAIL (marketing's key)"),
             C("segment", "TEXT", "PUBLIC"),
             C("mkt_consent", "INTEGER", "SENSITIVE", "marketing consent (marketing view)")],
            owner=None, classification=None, retention=None,       # GAP x3
            description="Campaign membership; keys customers by email."),
    }
    conflicts = [
        {"concept": "customer identity key",
         "domain_a": "Customer Identity & Loyalty", "field_a": "customer.customer_id (INTEGER surrogate)",
         "domain_b": "Marketing & Campaigns", "field_b": "campaign_membership.cust_ref (email string)",
         "impact": "No shared join key; cross-domain customer resolution requires matching on email."},
        {"concept": "marketing consent",
         "domain_a": "Customer Identity & Loyalty", "field_a": "customer.marketing_consent",
         "domain_b": "Marketing & Campaigns", "field_b": "campaign_membership.mkt_consent",
         "impact": "Two systems of record for consent disagree ~20% of the time; GDPR risk if marketing acts on stale consent."},
        {"concept": "carbon unit of measure",
         "domain_a": "Inventory & Fulfillment", "field_a": "shipment.carbon_kg (kg)",
         "domain_b": "Reporting (derived)", "field_b": "a slice stored in grams",
         "impact": "Mixed units inflate the CSRD disclosure unless normalized; traceability breaks at the unit boundary."},
    ]
    return Catalog(database="cardinal", tables=tables, semantic_conflicts=conflicts)


if __name__ == "__main__":
    conn, cat = build(":memory:")
    cur = conn.cursor()
    print("Tables and row counts:")
    for t in cat.tables:
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        gaps = [g for g in ("owner", "classification", "retention")
                if getattr(cat.table(t), g) is None]
        print(f"  {t:22} rows={n:5d}  gaps={gaps}")
    print(f"\nSeeded semantic conflicts: {len(cat.semantic_conflicts)}")
