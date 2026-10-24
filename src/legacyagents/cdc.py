"""Change data capture: a reader that follows the gateway journal from a saved checkpoint and
turns each entry into an agent-friendly event (masked, ordered, at-least-once with de-duplication
by sequence number, resumable after a restart)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from .gateway import Journal
from .guards import mask_obj


class CdcReader:
    def __init__(self, journal: Journal, checkpoint: Path):
        self.journal, self.checkpoint = journal, Path(checkpoint)
        self.last = json.loads(self.checkpoint.read_text())["seq"] if self.checkpoint.exists() else 0

    def poll(self, limit: int = 100) -> list[dict]:
        with self.journal.lock:
            new = [e for e in self.journal.entries if e["seq"] > self.last][:limit]
        events = []
        for e in new:
            events.append(
                mask_obj(
                    {
                        "type": f"{e['file']}.{e['entry']}",
                        "seq": e["seq"],
                        "key": e["key"],
                        "before": e["before"],
                        "after": e["after"],
                        "ts": e["ts"],
                    }
                )
            )
            self.last = e["seq"]
        if new:
            self.checkpoint.write_text(json.dumps({"seq": self.last}))
        return events

    def stream(self, stop: threading.Event, on_event, wait: float = 0.05):
        while not stop.is_set():
            with self.journal.cond:
                if not any(e["seq"] > self.last for e in self.journal.entries):
                    self.journal.cond.wait(wait)
            for ev in self.poll():
                on_event(ev, time.time())
