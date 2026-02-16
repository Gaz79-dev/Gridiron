import os
import requests

CRCON_BASE = os.getenv("CRCON_BASE_URL", "https://rcon.rdg-clan.co.uk")
MAP_SCOREBOARD = f"{CRCON_BASE}/api/get_map_scoreboard"

CRCON_COOKIE = os.getenv("CRCON_COOKIE")


class CRCONClient:
    def __init__(self):
        if not CRCON_COOKIE:
            raise RuntimeError("CRCON_COOKIE environment variable is missing")

        self.session = requests.Session()

        cookie_dict = {}
        for part in CRCON_COOKIE.split(";"):
            k, v = part.strip().split("=", 1)
            cookie_dict[k] = v

        self.session.cookies.update(cookie_dict)

    def fetch_map_scoreboard(self, map_id: int):
        url = f"{MAP_SCOREBOARD}?map_id={map_id}"
        resp = self.session.get(url, timeout=20)
        resp.raise_for_status()
        return resp.json()
