#!/usr/bin/env python3
"""
Сухий прогін заливки чинних PDF у бота (гайд v13, магніт v3d). НІЧОГО НЕ
НАДСИЛАЄ: перевіряє, що файли на місці і їх назви пройдуть перевірку ролі
в /zalyvka, і друкує команди з заглушками $BOT_URL і $WEBHOOK_SECRET.
Виконувати команди тільки після «так» Yaro (це відправка файлу через бота).
"""
import hashlib, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAGNIT = os.path.normpath(os.path.join(HERE, "..", "..", "magnit"))
PLAN = [
    ("guide", "Iryna-Rul-SVITLO-guide-2026-09-23-v13.pdf", "SVITLO-guide-2026-09-23-v13"),
    ("magnet", "Iryna-Rul-3-skhemy-svitla-2026-09-23-v3d.pdf", "3-skhemy-svitla-2026-09-23-v3d"),
]
bad = 0
for rol, name, expect in PLAN:
    path = os.path.join(MAGNIT, name)
    if not os.path.exists(path):
        print(rol + ": НЕМА " + path)
        bad += 1
        continue
    blob = open(path, "rb").read()
    mb = len(blob) / 1048576
    print(rol + ": " + name + ", " + ("%.1f" % mb) + " МБ, md5 " + hashlib.md5(blob).hexdigest()[:8]
          + (", назва проходить" if expect in name else ", НАЗВА НЕ ПРОЙДЕ"))
    if mb > 50:
        print("  УВАГА: понад 50 МБ, Bot API не прийме")
        bad += 1
    print('  curl -sS -F "file=@' + path + '" "$BOT_URL/zalyvka/$WEBHOOK_SECRET?rol=' + rol + '"')
sys.exit(1 if bad else 0)
