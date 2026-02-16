import os
import requests

CRCON_BASE = os.getenv("CRCON_BASE_URL", "https://rcon.rdg-clan.co.uk").rstrip("/")
MAP_SCOREBOARD = f"{CRCON_BASE}/api/get_map_scoreboard"

CRCON_API_KEY = os.getenv("CRCON_API_KEY")


class CRCONClient:
    def __init__(self):
        if not CRCON_API_KEY:
            raise RuntimeError("CRCON_API_KEY environment variable is missing")

        self.session = requests.Session()

        # Use Django token authentication
        self.session.headers.update({
            "Authorization": f"Bearer {CRCON_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def fetch_map_scoreboard(self, map_id: int):
        url = MAP_SCOREBOARD

        resp = self.session.get(url, params={"map_id": map_id}, timeout=20)

        if resp.status_code == 401:
            raise RuntimeError("CRCON API key rejected (401 Unauthorized)")
        if resp.status_code == 403:
            raise RuntimeError("CRCON API key forbidden (403)")
        if resp.status_code >= 500:
            raise RuntimeError(f"CRCON server error: {resp.status_code}")

        resp.raise_for_status()

        return resp.json()
