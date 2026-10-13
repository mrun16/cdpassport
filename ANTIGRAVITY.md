# Building this in Google Antigravity

1. Open Antigravity, choose **Open Folder**, and select this `cd-passport` folder. The agent reads `AGENTS.md` automatically.
2. In the terminal run the commands from README.md, then open the browser agent on http://127.0.0.1:8000.
3. Paste the prompts below into the Agent Manager one at a time. Review the plan and artifacts before accepting each.

## Prompt 1: verify and polish the UI
Open the running app in the browser, walk through audit, passport, trip, facility receipt and dashboard, and take screenshots. Compare the look against a government procurement portal such as GeM: restrained, dense, tabular, trustworthy. Fix any alignment, spacing, contrast or mobile layout problems you find. Do not change the colour palette or fonts.

## Prompt 2: login and roles
Add role-based login (officer, driver, facility, municipal). Use signed session cookies and a users table seeded with one demo user per role. Officers can create audits and passports, drivers can only dispatch and deliver their own loads, facility users can only record receipts at their own facility, municipal users get read-only access to everything. Enforce this in the API.

## Prompt 3: final reuse proof
Add a reuse step after certification: buyer name, project location, quantity used, application (paver blocks, road sub-base, backfill, non-structural concrete), geo-tagged delivery, and a final reuse certificate. Add "Reuse verified" to the passport timeline and a "Reused (t)" column to the dashboard.

## Prompt 4: offline-first passports
Make passport creation and trip events work offline using a service worker and IndexedDB, and sync with the API when the network returns. Show a clear "Saved on this device, not yet synced" state.

## Prompt 5: map and route deviation
Add a Leaflet map (OpenStreetMap tiles) on the passport page showing origin, facility geofence and the trip path. Record GPS points during transit and raise a flag when a vehicle leaves a 500 m corridor around the planned route.

## Prompt 6: reports and tests
Add PDF export for the certificate and a CSV export of all passports. Write pytest tests for the API covering: hazardous routing rejection, geofence flagging, weight variance flagging, and dashboard maths.
