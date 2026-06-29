"""Cron expression parser — supports standard 5-field cron (minute hour dom month dow)."""

from datetime import datetime, timedelta, timezone
from typing import Optional


def _parse_field(field: str, min_val: int, max_val: int) -> set[int]:
    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if part == "*":
            values.update(range(min_val, max_val + 1))
        elif part.startswith("*/"):
            step = int(part[2:])
            values.update(range(min_val, max_val + 1, step))
        elif "-" in part:
            start, end = part.split("-", 1)
            values.update(range(int(start), int(end) + 1))
        else:
            values.add(int(part))
    return values


class CronExpression:
    def __init__(self, expr: str):
        parts = expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Expected 5-field cron expression, got: {expr}")
        self.minutes = _parse_field(parts[0], 0, 59)
        self.hours = _parse_field(parts[1], 0, 23)
        self.dom = _parse_field(parts[2], 1, 31)
        self.months = _parse_field(parts[3], 1, 12)
        self.dow = _parse_field(parts[4], 0, 6)

    def matches(self, dt: datetime) -> bool:
        return (
            dt.minute in self.minutes
            and dt.hour in self.hours
            and dt.day in self.dom
            and dt.month in self.months
            and dt.weekday() in {d % 7 for d in self.dow}
        )

    def next_run(self, after: Optional[datetime] = None) -> datetime:
        after = after or datetime.now(timezone.utc)
        if after.tzinfo is None:
            after = after.replace(tzinfo=timezone.utc)

        candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(525600):  # max 1 year lookahead
            if self.matches(candidate):
                return candidate
            candidate += timedelta(minutes=1)
        raise ValueError(f"No next run found for cron: {self}")
