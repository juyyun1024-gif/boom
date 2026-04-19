"""In-memory event store for SentinelCare."""

from __future__ import annotations

from threading import Lock
from typing import Optional

from .models import Event, Alert


class EventStore:
    """Thread-safe in-memory store for events and alerts."""

    def __init__(self, max_events: int = 200) -> None:
        self._events: list[Event] = []
        self._alerts: list[Alert] = []
        self._max = max_events
        self._lock = Lock()

    # -- Events ---------------------------------------------------------------

    def add_event(self, event: Event) -> None:
        with self._lock:
            self._events.append(event)
            if len(self._events) > self._max:
                self._events = self._events[-self._max :]

    def get_events(self, limit: int = 50) -> list[Event]:
        with self._lock:
            return list(reversed(self._events[-limit:]))

    def clear_events(self) -> None:
        with self._lock:
            self._events.clear()

    # -- Alerts ---------------------------------------------------------------

    def add_alert(self, alert: Alert) -> None:
        with self._lock:
            self._alerts.append(alert)

    def get_alerts(self, limit: int = 20) -> list[Alert]:
        with self._lock:
            return list(reversed(self._alerts[-limit:]))

    def get_latest_alert(self) -> Optional[Alert]:
        with self._lock:
            return self._alerts[-1] if self._alerts else None


# Singleton
event_store = EventStore()
