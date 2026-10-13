#!/usr/bin/env python3
"""/privacy: політика конфіденційності українською й англійською (13.10). Без мережі і бази."""
import os, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "NO_THREADS": "1", "TEST_MODE": "1"})
os.environ.pop("DATABASE_URL", None)

import bot

r = bot.app.test_client().get("/privacy")
html = r.get_data(as_text=True)
assert r.status_code == 200, r.status_code
assert r.headers["Content-Type"].startswith("text/html"), r.headers["Content-Type"]
for must in ("Політика конфіденційності", "Privacy Policy", "@iryna_rul_bot", "@iryna_rul_photographer",
             "essentialism.core@gmail.com", "Видалення даних", "Data deletion", "30 днів", "30 days",
             "iryna-reklama", "Франкфурт", "Frankfurt", 'id="en"'):
    assert must in html, must
assert "Руль" not in html, "прізвище не пишемо (VIDMOVY В21)"
print("OK /privacy:", len(html.encode()), "байт")
