# Project rules

- Stack: FastAPI + SQLite backend (`app/main.py`), single-file vanilla JS frontend (`app/static/index.html`). Do not add a frontend build step unless asked.
- Look and feel: Indian government portal. Light background, deep green navigation, navy headings, saffron primary buttons, Public Sans. No gradients, emoji, illustrations, or playful copy. Sentence case. Tables over cards for data.
- Never use the national emblem or Ashoka Chakra. Use the generic "C&D" mark.
- Accessibility: visible focus, labels on every input, colour is never the only status signal (chips carry text).
- Hazardous waste must never be routable to a recycling facility. Keep that check in the API, not only the UI.
- Every state change on a passport must append to the hash-chained event log via `log()`.
- Emission factors are placeholders. Never present them as verified.
- After any change run `python -m pytest` if tests exist, and start the server to confirm it boots.
