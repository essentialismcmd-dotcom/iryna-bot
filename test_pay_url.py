import os
os.environ.setdefault("BOT_TOKEN", "x")
os.environ["PAY_URL"] = "https://send.monobank.ua/jar/UBodjhwAt"
from urllib.parse import urlparse, parse_qs
import bot


def test_pay_url_has_amount_and_code():
    for tier, uah in (("t1", 900),):
        q = parse_qs(urlparse(bot.pay_url(1234, tier)).query)
        assert q["a"] == [str(bot.PRODUCTS[tier]["uah"])]
        assert q["t"] == [bot.order_code(1234, tier)]
        assert bot.CODE_RE.search(q["t"][0])


if __name__ == "__main__":
    test_pay_url_has_amount_and_code(); print("ok")
