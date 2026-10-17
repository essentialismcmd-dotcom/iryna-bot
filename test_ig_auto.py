#!/usr/bin/env python3
"""/ig-webhook і /data-deletion (18.10): автовідповідь у Direct без мережі і бази."""
import os, sys, json, hmac, hashlib

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "NO_THREADS": "1", "TEST_MODE": "1", "IG_VERIFY_TOKEN": "vt",
                   "META_APP_SECRET": "appsek", "IG_PAGE_TOKEN": "pt"})
os.environ.pop("DATABASE_URL", None)

import bot

c = bot.app.test_client()

# сторінка видалення
r = c.get("/data-deletion")
h = r.get_data(as_text=True)
assert r.status_code == 200 and "Data deletion" in h and "Видалення даних" in h and "30" in h

# перевірка підписки
assert c.get("/ig-webhook?hub.mode=subscribe&hub.verify_token=vt&hub.challenge=42").get_data(as_text=True) == "42"
assert c.get("/ig-webhook?hub.mode=subscribe&hub.verify_token=ne&hub.challenge=42").status_code == 403

# вибір відповіді
assert bot.ig_which("Хочу 3 схеми", None) == "A"
assert bot.ig_which("хочу три схеми", None) == "A"
assert bot.ig_which("Можна схеми світла?", None) == "A"
assert bot.ig_which("Хочу гайд", None) == "B"
assert bot.ig_which("Можна дізнатися більше про цю пропозицію?", "52535495609037") == "B"
assert bot.ig_which("Привіт, скільки коштує зйомка?", None) is None
assert bot.ig_which("Привіт", "999") is None


class FakeStore:
    def __init__(self):
        self.claimed, self.ev = set(), []
    def session_begin(self): pass
    def session_end(self): pass
    def dm_contact(self, ig_id, **k): return 1
    def dm_event(self, *a, **k): self.ev.append(a)
    def log_event(self, *a, **k): pass
    def kv_claim(self, k):
        if k in self.claimed: return False
        self.claimed.add(k); return True


fs = FakeStore()
bot.store = fs
sent = []
bot.ig_send = lambda ig, t: sent.append((ig, t)) or True


def post(body, sig=True):
    raw = json.dumps(body).encode()
    hd = {"Content-Type": "application/json"}
    if sig:
        hd["X-Hub-Signature-256"] = "sha256=" + hmac.new(b"appsek", raw, hashlib.sha256).hexdigest()
    return c.post("/ig-webhook", data=raw, headers=hd)


def msg(sender, text=None, echo=False, ad=None):
    m = {"sender": {"id": sender}, "recipient": {"id": "IRA"},
         "message": {"mid": "m" + sender + str(text), "text": text, "is_echo": echo}}
    if ad:
        m["message"]["referral"] = {"ad_id": ad, "source": "ADS"}
    return {"object": "instagram", "entry": [{"messaging": [m]}]}


assert post(msg("u1", "Хочу 3 схеми"), sig=False).status_code == 403 and not sent
assert post(msg("u1", "Хочу 3 схеми")).get_json()["sent"] == 1
assert sent[-1] == ("u1", bot.IG_REPLY_A)
post(msg("u1", "Хочу гайд"))                      # друга відповідь тій самій людині не йде
assert len(sent) == 1
post(msg("u2", "Можна більше?", ad="52535495609037"))
assert sent[-1] == ("u2", bot.IG_REPLY_B)
post(msg("u3", "Хочу 3 схеми", echo=True))        # ехо від Іри
post(msg("u4", "Коли вільна дата на зйомку?"))    # клієнтка зйомки
assert len(sent) == 2, sent
assert "t.me/iryna_rul_bot?start=svitlo" in bot.IG_REPLY_A and "start=hajd299" in bot.IG_REPLY_B

# без env вимкнено
bot.IG_PAGE_TOKEN = ""
assert post(msg("u5", "Хочу 3 схеми")).get_json()["ok"] is False and len(sent) == 2
print("OK ig auto")
