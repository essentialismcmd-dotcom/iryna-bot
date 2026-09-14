#!/usr/bin/env python3
"""
Перевірка приймача діректу БЕЗ мережі, бази і Meta.

Навіщо: замір з Meta робиться один раз і на живому акаунті. Якщо приймач
складе переписку не в той тред або не відповість на перевірку підписки, ми
дізнаємось про це посеред заміру і витратимо другий вхід. Дешевше зловити
тут.

Запуск:  python test_dm.py
Виходить 0, якщо все зелене. Мережі не торкається: BOT_TOKEN підставний,
NO_THREADS=1 глушить потоки, сховище підмінене на список у памʼяті.
"""

import os, sys, json

# Консоль Windows за замовчуванням cp1251 і падає на апострофі U+02BC.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("WEBHOOK_SECRET", "sekret")
os.environ.setdefault("META_VERIFY_TOKEN", "perevirka")
os.environ["NO_THREADS"] = "1"          # не чіпати телеграм і монобанк
os.environ.pop("DATABASE_URL", None)    # сховище вимкнене

import bot

AKAUNT = "17841400000000000"   # акаунт Іри, він же отримувач і відправник ехо
LUDYNA = "12334"               # клієнтка


class FakeStore:
    """Записує виклики замість Postgres. Той самий інтерфейс, що й store."""

    def __init__(self):
        self.podii = []
        self._id = {}

    def session_begin(self):
        pass

    def session_end(self):
        pass

    def dm_contact(self, ig_id, username=None, display_name=None, lang=None, ts=None):
        return self._id.setdefault(ig_id, len(self._id) + 1)

    def dm_event(self, contact_id, direction, body=None, ts=None, kind="message",
                 payload=None, ext_id=None):
        self.podii.append({"contact": contact_id, "direction": direction,
                           "body": body, "kind": kind, "ext_id": ext_id})

    def hto(self, contact_id):
        for k, v in self._id.items():
            if v == contact_id:
                return k
        return None

    # Читалки. Потрібні лише для того, щоб сторінки стану віддавали 200.
    def dm_stats(self):
        return {}

    def dm_state(self, limit=60):
        return []

    def dm_one(self, kogo):
        return None

    def dm_thread(self, contact_id, limit=60):
        return []


def konvert(sender, recipient, text, echo=False, mid="mid.1"):
    msg = {"mid": mid, "text": text}
    if echo:
        msg["is_echo"] = True
    return {"object": "instagram",
            "entry": [{"id": AKAUNT, "time": 1569262486134,
                       "messaging": [{"sender": {"id": sender},
                                      "recipient": {"id": recipient},
                                      "timestamp": 1569262485349,
                                      "message": msg}]}]}


PROVALY = []


def perevirka(nazva, umova, sho_bulo=""):
    if umova:
        print("  ok    " + nazva)
    else:
        print("  ПРОВАЛ " + nazva + ("  " + str(sho_bulo) if sho_bulo else ""))
        PROVALY.append(nazva)


def main():
    fake = FakeStore()
    bot.store = fake
    c = bot.app.test_client()
    s = bot.SECRET

    print("\n1. Перевірка підписки, та сама, яку робить Meta")
    r = c.get("/dm-hook/" + s, query_string={
        "hub.mode": "subscribe", "hub.verify_token": bot.VERIFY_TOKEN,
        "hub.challenge": "1158201444"})
    perevirka("правильний токен повертає hub.challenge голим текстом",
              r.status_code == 200 and r.get_data(as_text=True) == "1158201444",
              r.status_code)
    r = c.get("/dm-hook/" + s, query_string={
        "hub.mode": "subscribe", "hub.verify_token": "chuzhyi",
        "hub.challenge": "1158201444"})
    perevirka("чужий токен отримує 403", r.status_code == 403, r.status_code)

    print("\n2. Вхідне від клієнтки")
    fake.podii.clear()
    r = c.post("/dm-hook/" + s, json=konvert(LUDYNA, AKAUNT, "Скільки коштує зйомка?"))
    perevirka("відповідь 200", r.status_code == 200, r.status_code)
    perevirka("рівно одна подія", len(fake.podii) == 1, len(fake.podii))
    if fake.podii:
        p = fake.podii[0]
        perevirka("напрямок in", p["direction"] == "in", p["direction"])
        perevirka("тред заведений на клієнтку, не на акаунт",
                  fake.hto(p["contact"]) == LUDYNA, fake.hto(p["contact"]))
        perevirka("текст на місці", p["body"] == "Скільки коштує зйомка?", p["body"])

    print("\n3. Ехо: Іра відповіла з телефона. Головна пастка")
    fake.podii.clear()
    r = c.post("/dm-hook/" + s,
               json=konvert(AKAUNT, LUDYNA, "350 доларів", echo=True, mid="mid.2"))
    perevirka("відповідь 200", r.status_code == 200, r.status_code)
    perevirka("рівно одна подія", len(fake.podii) == 1, len(fake.podii))
    if fake.podii:
        p = fake.podii[0]
        perevirka("напрямок out", p["direction"] == "out", p["direction"])
        perevirka("тред ТОЙ САМИЙ, що й у вхідного, а не «Іра сама з собою»",
                  fake.hto(p["contact"]) == LUDYNA, fake.hto(p["contact"]))

    print("\n4. Обидва боки лягли в один тред")
    perevirka("контактів заведено рівно один", len(fake._id) == 1, list(fake._id))

    print("\n5. Сміття не валить сервіс")
    for nazva, telo in (("порожнє", {}),
                        ("не наш обʼєкт", {"object": "page", "entry": []}),
                        ("подія без message", {"object": "instagram", "entry": [
                            {"id": AKAUNT, "messaging": [{"sender": {"id": LUDYNA},
                                                          "recipient": {"id": AKAUNT},
                                                          "read": {"mid": "m"}}]}]})):
        fake.podii.clear()
        r = c.post("/dm-hook/" + s, json=telo)
        perevirka(nazva + ": 200 і не падає", r.status_code == 200, r.status_code)

    print("\n6. Маршрути не сперечаються між собою")
    perevirka("сторінка людини /dm/<S>/<хто> жива",
              c.get("/dm/" + s + "/olena").status_code == 200)
    perevirka("сторінка стану /dm/<S> жива",
              c.get("/dm/" + s).status_code == 200)

    print("")
    if PROVALY:
        print("ПРОВАЛІВ: " + str(len(PROVALY)))
        for n in PROVALY:
            print("  " + n)
        return 1
    print("Усе зелене. Приймач готовий до заміру з Meta.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
