# C&D Passport

Cradle-to-grave traceability for construction and demolition (C&D) waste.
A site officer audits a building, the system produces a recovery and routing plan, every truckload gets a QR-coded passport, the receiving facility issues a quality certificate, and a dashboard reports diversion, emissions avoided, virgin material saved and landfill avoided.

## Run it

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 and press **Load demonstration data** on the dashboard.

## Workflow in the app

| Step | Screen | What happens |
|---|---|---|
| 1 | Site audit | Officer records building details, hazards, salvage and estimated tonnes per material (concrete, brick, steel, wood, gypsum, tiles, plastic, e-waste, hazardous). A recovery and routing plan is generated. |
| 2 | Load passports | A passport and QR code is issued per truckload with declared weight, vehicle, driver, destination and GPS of origin. Hazardous waste can only be routed to a hazardous facility. |
| 3 | Passport page | Driver starts the trip (GPS captured) and confirms arrival. Arrival is checked against a 300 m geofence around the facility. |
| 4 | Facility desk | Operator records weighbridge weight, contamination and tests, then accepts or rejects. A recycled-material certificate is issued. |
| 5 | Dashboard | Diversion rate, CO2e avoided, virgin material saved, landfill avoided, recovery by material, load status. |

Public verification: the QR on each passport opens `/#/verify/<passport id>`.

## What v2 adds

| Screen | Route | Notes |
|---|---|---|
| Sign in | `#/login` | Mobile number, role, one-time password. **Demo OTP is always 123456.** Role menus are UI-only; the API does not enforce roles yet. |
| Dashboard | `#/` | Five-figure status strip, quick actions, Leaflet map (needs internet for tiles) |
| Batches | `#/batches` | Combine certified concrete/brick/tile loads into batch `RCA-BATCH-YYYY-NNN` with test results. Hazardous, rejected or failed-test material is refused. |
| Batch certificate | `#/batch/<id>` | Public, with QR |
| Marketplace | `#/market` | Orders cannot exceed available quantity; each order creates a reuse record |
| Reuse certificate | `#/reuse/<id>` | Verified reuse, geo-tagged |
| Report dumping | `#/report` | Public, photo and GPS, status lookup by reference number |
| Citizen reports | `#/reports` | Officer verifies, assigns and closes |

## Structure

```
app/main.py            FastAPI API, material rules, hash-chained event log, metrics
app/static/index.html  Single-page officer console (no build step)
cdpassport.db          SQLite file, created on first run
ANTIGRAVITY.md         Prompts to continue the build in Google Antigravity
AGENTS.md              Project rules for the AI agent
```

## Rules and assumptions (edit in `CATS` at the top of `app/main.py`)

- `yld` is the assumed recovery yield per material.
- `co2` is tonnes CO2e avoided per tonne recovered. **These are placeholders.** Replace them with sourced factors before showing any emissions number to a jury or authority.
- Landfill volume uses 1.6 t/m3.
- Virgin material saved counts only mineral streams (concrete, brick, tiles).
- Facilities are demo records with approximate coordinates.

## Known gaps (the prototype does not yet have)

- Login and roles (officer, driver, facility, municipal)
- Offline mode for sites with poor network
- Final reuse proof (buyer, application, geo-tagged delivery)
- Live GPS route tracking and route-deviation alerts
- PDF export of certificates and reports
