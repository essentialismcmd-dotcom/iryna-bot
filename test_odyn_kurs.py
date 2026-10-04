"""Курс один: COURSE_BUNDLE_ONLY=1 і COURSE_PRICES=...,3300 дають одну кнопку 3 300."""
import os, importlib, sys
os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1"})
os.environ["COURSE_BUNDLE_ONLY"] = "1"
os.environ["COURSE_PRICES"] = "3200,1900,3300"
sys.modules.pop("bot", None)
import bot
c = bot.COURSES["k12"]
assert c["uah"] == 3300, c
assert c["btn"] == "Курс ретуші, 3300 грн", c["btn"]
assert "Обидва" not in c["text"] and "дешевше" not in c["text"]
assert bot.PRODUCTS["k12"]["code"] == "6" and bot.PRODUCTS["k12"]["uah"] == 3300
assert "пакетом" not in bot.RETUSH_BUNDLE
print("OK test_odyn_kurs")
