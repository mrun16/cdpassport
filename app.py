
"""
C&D Passport - cradle-to-grave C&D waste traceability (prototype).
FastAPI + SQLite (JSON documents).
Run: uvicorn app.main:app --reload
"""

import sqlite3
import json
import hashlib
import uuid
import math
import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


DB = os.environ.get("CDP_DB", "cdpassport.db")
GEOFENCE_M = 300


# ---------------------------------------------------------
# MATERIAL RULES
# CO2 factors are placeholders. Replace with sourced values
# before publishing environmental figures.
# ---------------------------------------------------------

CATS = {
    "concrete": dict(
        label="Concrete / RCC",
        out="Recycled coarse aggregate",
        ftype="recycler",
        yld=0.85,
        co2=0.012,
        mineral=True,
        tests="Sieve analysis, water absorption, impact value",
    ),
    "brick": dict(
        label="Brick / masonry",
        out="Recycled fine aggregate / blocks",
        ftype="recycler",
        yld=0.80,
        co2=0.010,
        mineral=True,
        tests="Sieve analysis, fines content",
    ),
    "tiles": dict(
        label="Tiles / ceramics",
        out="Aggregate substitute",
        ftype="recycler",
        yld=0.70,
        co2=0.010,
        mineral=True,
        tests="Sieve analysis, water absorption",
    ),
    "steel": dict(
        label="Steel / metal",
        out="Scrap for remelting",
        ftype="metal",
        yld=0.95,
        co2=1.5,
        mineral=False,
        tests="Weighbridge and grade check",
    ),
    "wood": dict(
        label="Wood / timber",
        out="Reuse / biomass / board feedstock",
        ftype="recycler",
        yld=0.70,
        co2=0.20,
        mineral=False,
        tests="Moisture, treatment check",
    ),
    "gypsum": dict(
        label="Gypsum / plasterboard",
        out="Gypsum recycling",
        ftype="recycler",
        yld=0.60,
        co2=0.05,
        mineral=False,
        tests="Purity check",
    ),
    "plastic": dict(
        label="Plastics",
        out="Authorised plastic recycler",
        ftype="plastic_ewaste",
        yld=0.70,
        co2=1.0,
        mineral=False,
        tests="Polymer sort",
    ),
    "ewaste": dict(
        label="E-waste",
        out="Authorised e-waste recycler",
        ftype="plastic_ewaste",
        yld=0.80,
        co2=0.50,
        mineral=False,
        tests="Item inventory",
    ),
    "hazardous": dict(
        label="Hazardous (asbestos, lead paint, chemicals)",
        out="Approved hazardous disposal - no recycling",
        ftype="hazardous",
        yld=0,
        co2=0,
        mineral=False,
        tests="Hazard classification",
    ),
}


# ---------------------------------------------------------
# DEFAULT DEMO FACILITIES
# ---------------------------------------------------------

FACILITIES = [
    dict(
        id="F-01",
        name="Kalyan C&D Recycling Hub (demo)",
        ftype="recycler",
        lat=19.2403,
        lng=73.1305,
        accepts=["concrete", "brick", "tiles", "wood", "gypsum"],
    ),
    dict(
        id="F-02",
        name="Metal Scrap Recovery Unit (demo)",
        ftype="metal",
        lat=19.0330,
        lng=73.0297,
        accepts=["steel"],
    ),
    dict(
        id="F-03",
        name="Plastic & E-waste Recycler (demo)",
        ftype="plastic_ewaste",
        lat=19.1197,
        lng=72.8464,
        accepts=["plastic", "ewaste"],
    ),
    dict(
        id="F-04",
        name="Hazardous Waste TSDF (demo)",
        ftype="hazardous",
        lat=19.0176,
        lng=72.9781,
        accepts=["hazardous"],
    ),
]

FAC = {f["id"]: f for f in FACILITIES}

app = FastAPI(title="C&D Passport")


# ---------------------------------------------------------
# DATABASE HELPERS
# ---------------------------------------------------------

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row

    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS docs(
            kind TEXT,
            id TEXT,
            body TEXT,
            PRIMARY KEY(kind, id)
        );

        CREATE TABLE IF NOT EXISTS events(
            n INTEGER PRIMARY KEY AUTOINCREMENT,
            pid TEXT,
            type TEXT,
            payload TEXT,
            ts TEXT,
            prev TEXT,
            hash TEXT
        );
        """
    )

    return c


def put(kind, id, body):
    with db() as c:
        c.execute(
            "INSERT OR REPLACE INTO docs VALUES(?,?,?)",
            (kind, id, json.dumps(body)),
        )


def get(kind, id):
    with db() as c:
        r = c.execute(
            "SELECT body FROM docs WHERE kind=? AND id=?",
            (kind, id),
        ).fetchone()

    if not r:
        raise HTTPException(404, f"{kind} {id} not found")

    return json.loads(r["body"])


def allof(kind):
    with db() as c:
        rows = c.execute(
            "SELECT body FROM docs WHERE kind=?",
            (kind,),
        ).fetchall()

    return sorted(
        (json.loads(r["body"]) for r in rows),
        key=lambda d: d["created"],
        reverse=True,
    )


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(pid, event_type, payload):
    """Append to a hash-chained, tamper-evident event log."""

    with db() as c:
        r = c.execute(
            "SELECT hash FROM events WHERE pid=? ORDER BY n DESC LIMIT 1",
            (pid,),
        ).fetchone()

        prev = r["hash"] if r else "GENESIS"
        ts = now()
        body = json.dumps(payload, sort_keys=True)

        h = hashlib.sha256(
            f"{prev}|{pid}|{event_type}|{body}|{ts}".encode()
        ).hexdigest()

        c.execute(
            """
            INSERT INTO events(pid,type,payload,ts,prev,hash)
            VALUES(?,?,?,?,?,?)
            """,
            (pid, event_type, body, ts, prev, h),
        )


def events(pid):
    with db() as c:
        rows = c.execute(
            "SELECT * FROM events WHERE pid=? ORDER BY n",
            (pid,),
        ).fetchall()

    return [
        dict(
            type=r["type"],
            payload=json.loads(r["payload"]),
            ts=r["ts"],
            hash=r["hash"][:16],
        )
        for r in rows
    ]


def hav(a, b, c, d):
    """Calculate distance in metres between two GPS coordinates."""

    p = math.pi / 180

    x = (
        math.sin((c - a) * p / 2) ** 2
        + math.cos(a * p)
        * math.cos(c * p)
        * math.sin((d - b) * p / 2) ** 2
    )

    return 12742000 * math.asin(math.sqrt(x))


# ---------------------------------------------------------
# REQUEST MODELS
# ---------------------------------------------------------

class Item(BaseModel):
    category: str
    est_tonnes: float
    note: str = ""


class Hazard(BaseModel):
    kind: str
    note: str = ""


class AuditIn(BaseModel):
    project: str
    address: str
    officer: str
    building_age: int | None = None
    structure: str = ""
    area_sqm: float | None = None
    items: list[Item]
    hazards: list[Hazard] = []
    salvage: str = ""
    plan: str = ""


# UPDATED: facility_id is optional, and facility name/coordinates
# can be supplied when issuing a passport.
class PassIn(BaseModel):
    audit_id: str
    category: str
    declared_kg: float
    vehicle: str
    driver: str

    facility_id: str | None = None
    facility_name: str | None = None
    facility_lat: float | None = None
    facility_lng: float | None = None

    lat: float | None = None
    lng: float | None = None


class Geo(BaseModel):
    lat: float | None = None
    lng: float | None = None


class Receipt(BaseModel):
    actual_kg: float
    contamination_pct: float = 0
    output_kg: float | None = None
    tests: str = ""
    decision: str = "accept"
    inspector: str
    notes: str = ""


class FacIn(BaseModel):
    name: str
    accepts: list[str]
    lat: float
    lng: float


class BatchIn(BaseModel):
    passport_ids: list[str]
    grade: str
    tests: list[dict]
    approved_use: str
    price_per_t: float
    location: str = ""


class OrderIn(BaseModel):
    buyer: str
    project_location: str
    application: str
    qty_t: float
    ward: str = ""
    lat: float | None = None
    lng: float | None = None


class ReportIn(BaseModel):
    ward: str
    location: str
    description: str
    mobile: str = ""
    lat: float | None = None
    lng: float | None = None
    photo: str = ""


class StatusIn(BaseModel):
    status: str
    note: str = ""


# ---------------------------------------------------------
# FACILITY REGISTRATION
# ---------------------------------------------------------

# Load previously registered facilities from SQLite at startup.
for _d in allof("facility"):
    if _d["id"] not in FAC:
        FACILITIES.append(_d)
        FAC[_d["id"]] = _d


@app.post("/api/facilities")
def new_facility(f: FacIn):
    name = f.name.strip()

    if not name:
        raise HTTPException(400, "Enter the facility name.")

    if not f.accepts or any(c not in CATS for c in f.accepts):
        raise HTTPException(
            400,
            "Choose at least one material the facility is authorised to accept.",
        )

    if "hazardous" in f.accepts and len(f.accepts) > 1:
        raise HTTPException(
            400,
            "A hazardous-waste facility cannot also accept recyclable material. "
            "Register them as separate facilities.",
        )

    if not (-90 <= f.lat <= 90 and -180 <= f.lng <= 180):
        raise HTTPException(400, "Latitude or longitude is out of range.")

    # Avoid registering the same facility name twice.
    existing = next(
        (
            facility
            for facility in FACILITIES
            if facility["name"].strip().casefold() == name.casefold()
        ),
        None,
    )

    if existing:
        raise HTTPException(
            400,
            f"A facility named '{existing['name']}' is already registered.",
        )

    n = len(FACILITIES) + 1

    while f"F-{n:02d}" in FAC:
        n += 1

    d = dict(
        id=f"F-{n:02d}",
        name=name,
        ftype="hazardous" if f.accepts == ["hazardous"] else "recycler",
        lat=f.lat,
        lng=f.lng,
        accepts=f.accepts,
        created=now(),
    )

    put("facility", d["id"], d)
    FACILITIES.append(d)
    FAC[d["id"]] = d

    return d


# ---------------------------------------------------------
# METADATA
# ---------------------------------------------------------

@app.get("/api/meta")
def meta():
    return dict(
        categories={
            k: {
                x: v[x]
                for x in ("label", "out", "ftype", "tests")
            }
            for k, v in CATS.items()
        },
        facilities=FACILITIES,
    )


# ---------------------------------------------------------
# AUDITS
# ---------------------------------------------------------

@app.post("/api/audits")
def new_audit(a: AuditIn):
    if not a.items:
        raise HTTPException(400, "Add at least one material line.")

    plan = []

    for i in a.items:
        if i.category not in CATS:
            raise HTTPException(400, f"Unknown category {i.category}")

        m = CATS[i.category]

        plan.append(
            dict(
                category=i.category,
                label=m["label"],
                est_tonnes=i.est_tonnes,
                route=m["out"],
                tests=m["tests"],
                expected_recovered_t=round(i.est_tonnes * m["yld"], 2),
                facilities=[
                    f["id"]
                    for f in FACILITIES
                    if i.category in f["accepts"]
                ],
            )
        )

    d = a.model_dump() | dict(
        id="AUD-" + uuid.uuid4().hex[:6].upper(),
        created=now(),
        plan=plan,
        hazard_flag=bool(a.hazards)
        or any(i.category == "hazardous" for i in a.items),
    )

    put("audit", d["id"], d)
    return d


@app.get("/api/audits")
def audits():
    return allof("audit")


@app.get("/api/audits/{id}")
def audit(id: str):
    return get("audit", id)


# ---------------------------------------------------------
# PASSPORT CREATION - UPDATED
# ---------------------------------------------------------

@app.post("/api/passports")
def new_passport(p: PassIn):
    # Check that the audit exists.
    get("audit", p.audit_id)

    if p.category not in CATS:
        raise HTTPException(400, "Unknown category")

    # First, use a valid facility ID if the frontend supplied one.
    f = FAC.get(p.facility_id) if p.facility_id else None

    # If there is no ID, find a facility by its name.
    name = (p.facility_name or "").strip()

    if f is None and name:
        f = next(
            (
                facility
                for facility in FACILITIES
                if facility["name"].strip().casefold() == name.casefold()
            ),
            None,
        )

    # If the facility name is new, register the facility.
    if f is None:
        if not name:
            raise HTTPException(
                400,
                "Enter a destination facility name.",
            )

        if p.facility_lat is None or p.facility_lng is None:
            raise HTTPException(
                400,
                "This is a new facility. Enter its latitude and longitude "
                "to register it.",
            )

        # A newly typed facility is initially authorised only for
        # the material selected in this passport form.
        f = new_facility(
            FacIn(
                name=name,
                accepts=[p.category],
                lat=p.facility_lat,
                lng=p.facility_lng,
            )
        )

    # Validate that this facility accepts the selected material.
    if p.category not in f["accepts"]:
        raise HTTPException(
            400,
            f"{f['name']} is not authorised for "
            f"{CATS[p.category]['label']}. "
            "Choose an authorised facility for this material.",
        )

    # Store the facility ID so delivery, receipt, and tracking continue
    # to work with existing features.
    d = dict(
        audit_id=p.audit_id,
        category=p.category,
        declared_kg=p.declared_kg,
        vehicle=p.vehicle,
        driver=p.driver,
        facility_id=f["id"],
        lat=p.lat,
        lng=p.lng,
        id=(
            "CDP-"
            + datetime.now().strftime("%y%m%d")
            + "-"
            + uuid.uuid4().hex[:5].upper()
        ),
        created=now(),
        status="CREATED",
        cert=None,
        light="green",
        flags=[],
    )

    put("passport", d["id"], d)

    log(
        d["id"],
        "PASSPORT_CREATED",
        dict(
            audit=p.audit_id,
            cat=p.category,
            declared_kg=p.declared_kg,
            facility_id=f["id"],
            gps=[p.lat, p.lng],
        ),
    )

    return d


@app.get("/api/passports")
def passports(audit_id: str | None = None):
    return [
        p
        for p in allof("passport")
        if not audit_id or p["audit_id"] == audit_id
    ]


@app.get("/api/passports/{id}")
def passport(id: str):
    p = get("passport", id)

    return p | dict(
        events=events(id),
        facility=FAC[p["facility_id"]],
        audit=get("audit", p["audit_id"]),
    )


# ---------------------------------------------------------
# DISPATCH AND DELIVERY
# ---------------------------------------------------------

@app.post("/api/passports/{id}/dispatch")
def dispatch(id: str, g: Geo):
    p = get("passport", id)

    if p["status"] != "CREATED":
        raise HTTPException(
            400,
            f"Cannot dispatch a load that is {p['status']}.",
        )

    p["status"] = "IN_TRANSIT"

    put("passport", id, p)
    log(id, "DISPATCHED", g.model_dump())

    return p


@app.post("/api/passports/{id}/deliver")
def deliver(id: str, g: Geo):
    p = get("passport", id)
    f = FAC[p["facility_id"]]

    if p["status"] != "IN_TRANSIT":
        raise HTTPException(
            400,
            f"Cannot deliver a load that is {p['status']}.",
        )

    dist = (
        round(hav(g.lat, g.lng, f["lat"], f["lng"]))
        if g.lat is not None and g.lng is not None
        else None
    )

    inside = dist is not None and dist <= GEOFENCE_M

    if not inside:
        if dist is not None:
            p["flags"].append(
                f"Delivery outside {GEOFENCE_M} m geofence"
            )
        else:
            p["flags"].append("Delivery location not captured")

    p["status"] = "DELIVERED"
    p["light"] = "green" if inside else "red"

    put("passport", id, p)

    log(
        id,
        "DELIVERED",
        dict(
            lat=g.lat,
            lng=g.lng,
            distance_m=dist,
            inside_geofence=inside,
        ),
    )

    return p


# ---------------------------------------------------------
# RECEIPT AND CERTIFICATION
# ---------------------------------------------------------

@app.post("/api/passports/{id}/receipt")
def receipt(id: str, r: Receipt):
    p = get("passport", id)
    m = CATS[p["category"]]

    if p["status"] != "DELIVERED":
        raise HTTPException(
            400,
            "Receipt can only be recorded after delivery.",
        )

    ok = r.decision == "accept"

    out = (
        0
        if not ok or m["yld"] == 0
        else (
            r.output_kg
            if r.output_kg is not None
            else r.actual_kg
            * (1 - r.contamination_pct / 100)
            * m["yld"]
        )
    )

    var = (
        (r.actual_kg - p["declared_kg"])
        / p["declared_kg"]
        * 100
        if p["declared_kg"] != 0
        else 0
    )

    if abs(var) > 10:
        p["flags"].append(f"Weight variance {var:+.1f}% vs declared")

    if r.contamination_pct > 15:
        p["flags"].append(
            f"Contamination {r.contamination_pct:.0f}%"
        )

    p["light"] = (
        "red"
        if not ok or p["light"] == "red"
        else "amber"
        if p["flags"]
        else "green"
    )

    p["status"] = "CERTIFIED" if ok else "REJECTED"

    p["cert"] = dict(
        id="CERT-" + uuid.uuid4().hex[:6].upper(),
        issued=now(),
        facility=FAC[p["facility_id"]]["name"],
        inspector=r.inspector,
        received_kg=r.actual_kg,
        contamination_pct=r.contamination_pct,
        output_kg=round(out, 1),
        product=m["out"],
        tests=r.tests or m["tests"],
        result="Accepted" if ok else "Rejected",
        notes=r.notes,
        variance_pct=round(var, 1),
    )

    put("passport", id, p)

    log(
        id,
        "RECEIPT_" + p["cert"]["result"].upper(),
        p["cert"],
    )

    return p


# ---------------------------------------------------------
# DASHBOARD METRICS
# ---------------------------------------------------------

def metrics(passes):
    done = [p for p in passes if p["cert"]]
    by = {}

    for p in done:
        c = p["cert"]

        k = by.setdefault(
            p["category"],
            dict(
                label=CATS[p["category"]]["label"],
                received_t=0,
                recovered_t=0,
            ),
        )

        k["received_t"] += c["received_kg"] / 1000
        k["recovered_t"] += c["output_kg"] / 1000

    recv = sum(k["received_t"] for k in by.values())
    rec = sum(k["recovered_t"] for k in by.values())

    virgin = sum(
        k["recovered_t"]
        for category, k in by.items()
        if CATS[category]["mineral"]
    )

    co2 = sum(
        k["recovered_t"] * CATS[category]["co2"]
        for category, k in by.items()
    )

    for k in by.values():
        k.update(
            received_t=round(k["received_t"], 2),
            recovered_t=round(k["recovered_t"], 2),
        )

    return dict(
        loads=len(passes),
        in_transit=sum(
            p["status"] == "IN_TRANSIT" for p in passes
        ),
        certified=sum(
            p["status"] == "CERTIFIED" for p in passes
        ),
        rejected=sum(
            p["status"] == "REJECTED" for p in passes
        ),
        red=sum(p["light"] == "red" for p in passes),
        amber=sum(p["light"] == "amber" for p in passes),
        received_t=round(recv, 2),
        diverted_t=round(rec, 2),
        diversion_rate=round(rec / recv * 100, 1) if recv else 0,
        co2_avoided_t=round(co2, 2),
        virgin_saved_t=round(virgin, 2),
        landfill_avoided_t=round(rec, 2),
        landfill_avoided_m3=round(rec / 1.6, 1),
        landfilled_t=round(recv - rec, 2),
        by_category=by,
    )


def dashboard(audit_id: str | None = None):
    return metrics(passports(audit_id))


# ---------------------------------------------------------
# DEMO DATA
# ---------------------------------------------------------

@app.post("/api/demo")
def demo():
    a = new_audit(
        AuditIn(
            project="Sector 7 Tower Demolition (demo)",
            address="Plot 14, Sector 7, Navi Mumbai",
            officer="Site Officer (demo)",
            building_age=38,
            structure="RCC frame, brick infill",
            area_sqm=2400,
            hazards=[
                Hazard(
                    kind="Asbestos sheets",
                    note="Roof of annex block",
                )
            ],
            items=[
                Item(category=c, est_tonnes=t)
                for c, t in [
                    ("concrete", 120),
                    ("brick", 60),
                    ("steel", 14),
                    ("wood", 6),
                    ("tiles", 9),
                    ("hazardous", 2),
                ]
            ],
        )
    )

    demo_loads = [
        ("concrete", "F-01", 24000, 6, "accept"),
        ("concrete", "F-01", 22000, 11, "accept"),
        ("brick", "F-01", 18000, 19, "accept"),
        ("steel", "F-02", 7800, 2, "accept"),
        ("tiles", "F-01", 5200, 40, "reject"),
        ("hazardous", "F-04", 1500, 0, "accept"),
    ]

    for cat, fac, kg, con, decision in demo_loads:
        f = FAC[fac]

        p = new_passport(
            PassIn(
                audit_id=a["id"],
                category=cat,
                declared_kg=kg,
                vehicle="MH43-DEMO-" + str(kg)[:2],
                driver="Driver (demo)",
                facility_id=fac,
                lat=19.07,
                lng=72.99,
            )
        )

        dispatch(p["id"], Geo(lat=19.07, lng=72.99))

        deliver(
            p["id"],
            Geo(lat=f["lat"] + 0.0004, lng=f["lng"]),
        )

        receipt(
            p["id"],
            Receipt(
                actual_kg=kg * 1.02,
                contamination_pct=con,
                decision=decision,
                inspector="Facility operator (demo)",
            ),
        )

    p = new_passport(
        PassIn(
            audit_id=a["id"],
            category="brick",
            declared_kg=16000,
            vehicle="MH43-DEMO-01",
            driver="Driver (demo)",
            facility_id="F-01",
            lat=19.07,
            lng=72.99,
        )
    )

    dispatch(p["id"], Geo(lat=19.07, lng=72.99))

    pc = [
        q["id"]
        for q in passports(a["id"])
        if q["category"] == "concrete"
        and q["status"] == "CERTIFIED"
    ]

    b = new_batch(
        BatchIn(
            passport_ids=pc,
            grade="10-20 mm recycled coarse aggregate",
            approved_use=(
                "Paver blocks, road sub-base, non-structural concrete"
            ),
            price_per_t=850,
            tests=[
                dict(
                    name="Particle-size distribution",
                    value="Within grading limits",
                    result="Pass",
                ),
                dict(
                    name="Water absorption (%)",
                    value="4.2",
                    result="Pass",
                ),
                dict(
                    name="Aggregate impact value (%)",
                    value="28",
                    result="Pass",
                ),
            ],
        )
    )

    order(
        b["id"],
        OrderIn(
            buyer="Municipal Works Department (demo)",
            project_location="Ward 12 footpath",
            ward="Ward 12",
            application="Road sub-base",
            qty_t=11,
            lat=19.10,
            lng=72.90,
        ),
    )

    new_report(
        ReportIn(
            ward="Ward 12",
            location="Near the nala behind the market",
            description=(
                "Brick and concrete debris dumped on the roadside"
            ),
            lat=19.12,
            lng=72.95,
        )
    )

    new_report(
        ReportIn(
            ward="Ward 7",
            location="Plot opposite the bus depot",
            description="Mixed rubble with plastic pipes",
            lat=19.05,
            lng=73.02,
        )
    )

    return a


# ---------------------------------------------------------
# V2: BATCHES, MARKETPLACE, REUSE, CITIZEN REPORTS
# ---------------------------------------------------------

MINERAL = ("concrete", "brick", "tiles")


@app.post("/api/batches")
def new_batch(b: BatchIn):
    ids = list(dict.fromkeys(b.passport_ids))

    if not ids:
        raise HTTPException(
            400,
            "Select at least one certified load.",
        )

    ps = [get("passport", i) for i in ids]

    for p in ps:
        if p["category"] not in MINERAL:
            raise HTTPException(
                400,
                f"{p['id']} is {CATS[p['category']]['label']}. "
                "Only concrete, brick and tiles can be made into "
                "recycled aggregate.",
            )

        if p["status"] != "CERTIFIED":
            raise HTTPException(
                400,
                f"{p['id']} is not certified, so it cannot be batched.",
            )

        if p.get("batch_id"):
            raise HTTPException(
                400,
                f"{p['id']} is already in batch {p['batch_id']}.",
            )

    if not b.tests or any(
        t.get("result") != "Pass" for t in b.tests
    ):
        raise HTTPException(
            400,
            "Every test must be recorded and passed before "
            "a batch certificate is issued.",
        )

    out = sum(p["cert"]["output_kg"] for p in ps)

    bid = (
        f"RCA-BATCH-{datetime.now().year}-"
        f"{len(allof('batch')) + 1:03d}"
    )

    d = dict(
        id=bid,
        created=now(),
        grade=b.grade,
        tests=b.tests,
        approved_use=b.approved_use,
        price_per_t=b.price_per_t,
        location=(
            b.location
            or FAC[ps[0]["facility_id"]]["name"]
        ),
        passport_ids=ids,
        audit_ids=sorted({p["audit_id"] for p in ps}),
        output_kg=round(out, 1),
        available_kg=round(out, 1),
        cert_no="MMC-" + uuid.uuid4().hex[:6].upper(),
    )

    put("batch", bid, d)

    for p in ps:
        p["batch_id"] = bid
        put("passport", p["id"], p)
        log(p["id"], "BATCHED", dict(batch=bid, grade=b.grade))

    return d


@app.get("/api/batches")
def batches():
    return allof("batch")


@app.get("/api/batches/{id}")
def batch(id: str):
    b = get("batch", id)

    return b | dict(
        passports=[get("passport", i) for i in b["passport_ids"]]
    )


@app.post("/api/batches/{id}/order")
def order(id: str, o: OrderIn):
    b = get("batch", id)
    kg = o.qty_t * 1000

    if kg <= 0:
        raise HTTPException(
            400,
            "Enter a quantity greater than zero.",
        )

    if kg > b["available_kg"] + 1e-6:
        raise HTTPException(
            400,
            f"Only {b['available_kg'] / 1000:.2f} t is available "
            "in this batch.",
        )

    b["available_kg"] = round(b["available_kg"] - kg, 1)
    put("batch", id, b)

    rid = (
        f"REUSE-{datetime.now().year}-"
        f"{len(allof('reuse')) + 1:04d}"
    )

    r = dict(
        id=rid,
        created=now(),
        batch_id=id,
        qty_kg=kg,
        buyer=o.buyer,
        project_location=o.project_location,
        ward=o.ward,
        application=o.application,
        lat=o.lat,
        lng=o.lng,
        audit_ids=b["audit_ids"],
        cert_no="FRC-" + uuid.uuid4().hex[:6].upper(),
        grade=b["grade"],
        batch_cert=b["cert_no"],
    )

    put("reuse", rid, r)

    for pid in b["passport_ids"]:
        log(
            pid,
            "REUSE_CONFIRMED",
            dict(reuse=rid, batch=id, application=o.application, ward=o.ward),
        )

    return r


@app.get("/api/reuses")
def reuses():
    return allof("reuse")


@app.get("/api/reuses/{id}")
def reuse(id: str):
    return get("reuse", id)


# ---------------------------------------------------------
# CITIZEN REPORTS
# ---------------------------------------------------------

RSTAT = ("OPEN", "VERIFIED", "ASSIGNED", "CLOSED")


@app.post("/api/reports")
def new_report(r: ReportIn):
    d = r.model_dump() | dict(
        id="RPT-" + uuid.uuid4().hex[:6].upper(),
        created=now(),
        status="OPEN",
        history=[
            dict(
                status="OPEN",
                note="Report received",
                ts=now(),
            )
        ],
    )

    put("report", d["id"], d)

    return d | dict(photo="")


@app.get("/api/reports")
def reports():
    return allof("report")


@app.get("/api/reports/{id}")
def report(id: str):
    return get("report", id.upper()) | dict(photo="")


@app.post("/api/reports/{id}/status")
def report_status(id: str, s: StatusIn):
    if s.status not in RSTAT:
        raise HTTPException(400, "Unknown status.")

    d = get("report", id)
    d["status"] = s.status

    d["history"].append(
        dict(
            status=s.status,
            note=s.note,
            ts=now(),
        )
    )

    put("report", id, d)

    return d


# ---------------------------------------------------------
# DASHBOARD API
# ---------------------------------------------------------

@app.get("/api/dashboard")
def dashboard2(audit_id: str | None = None):
    d = metrics(passports(audit_id))

    rs = [
        r
        for r in allof("reuse")
        if not audit_id or audit_id in r["audit_ids"]
    ]

    today = now()[:10]

    return d | dict(
        reused_t=round(
            sum(r["qty_kg"] for r in rs) / 1000,
            2,
        ),
        reuse_orders=len(rs),
        audits=len(allof("audit")),
        reports_open=sum(
            r["status"] != "CLOSED"
            for r in allof("report")
        ),
        passports_today=sum(
            p["created"][:10] == today
            for p in passports(audit_id)
        ),
    )


# ---------------------------------------------------------
# FRONTEND
# ---------------------------------------------------------

app.mount(
    "/static",
    StaticFiles(
        directory=os.path.join(
            os.path.dirname(__file__),
            "static",
        )
    ),
    name="static",
)


@app.get("/")
def index():
    return FileResponse(
        os.path.join(
            os.path.dirname(__file__),
            "static",
            "index.html",
        )
    )

