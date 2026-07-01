"""Tiny persistent tracker for daily break statistics.

Stores a JSON map of ``{"YYYY-MM-DD": {"taken": n, "skipped": n}}`` in the
config directory and exposes a compact summary for the settings page.  All I/O
is defensive so a corrupt or unwritable file never crashes the app.
"""

import json
import datetime
from pathlib import Path


class BreakStats:
    def __init__(self, path):
        self.path = Path(path)

    # ---- persistence ----
    def _load(self) -> dict:
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text())
                if isinstance(data, dict):
                    return data
        except Exception as e:
            print(f"[stats] Could not read stats: {e}")
        return {}

    def _save(self, data: dict):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            print(f"[stats] Could not write stats: {e}")

    @staticmethod
    def _today() -> str:
        return datetime.date.today().isoformat()

    # ---- recording ----
    def record(self, taken: bool):
        data = self._load()
        day = data.setdefault(self._today(), {"taken": 0, "skipped": 0})
        day["taken" if taken else "skipped"] = day.get("taken" if taken else "skipped", 0) + 1
        self._save(data)

    def record_taken(self):
        self.record(True)

    def record_skipped(self):
        self.record(False)

    # ---- reporting ----
    def summary(self) -> dict:
        data = self._load()
        today = data.get(self._today(), {"taken": 0, "skipped": 0})
        week_taken = week_skipped = 0
        today_date = datetime.date.today()
        for i in range(7):
            key = (today_date - datetime.timedelta(days=i)).isoformat()
            day = data.get(key)
            if day:
                week_taken += int(day.get("taken", 0))
                week_skipped += int(day.get("skipped", 0))
        return {
            "today": {
                "taken": int(today.get("taken", 0)),
                "skipped": int(today.get("skipped", 0)),
            },
            "last7": {"taken": week_taken, "skipped": week_skipped},
        }
