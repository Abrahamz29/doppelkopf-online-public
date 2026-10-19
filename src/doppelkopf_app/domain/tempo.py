from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class RoundTempo:
    sequence: int
    completed_at: datetime
    duration_seconds: int
    smoothed_seconds: Decimal
    segment: int = 0

    @property
    def minutes_per_game(self) -> Decimal:
        return self.smoothed_seconds / Decimal(60)

    @property
    def games_per_hour(self) -> Decimal:
        if not self.smoothed_seconds:
            return Decimal(0)
        return Decimal(3600) / self.smoothed_seconds


def calculate_round_tempos(
    completed_rounds: tuple[tuple[int, datetime | None], ...], window_minutes: int = 30,
    *, reset_times: tuple[datetime, ...] = (), live_only: bool = False,
) -> tuple[RoundTempo, ...]:
    """Calculate per-round intervals and their time-based rolling average."""
    if not 5 <= window_minutes <= 180:
        raise ValueError("Das Tempofenster muss zwischen 5 und 180 Minuten liegen.")
    measured: list[tuple[int, datetime, int, int]] = []
    resets = sorted(set(reset_times))
    segment = 0
    manual_segment = 0
    window = timedelta(minutes=window_minutes)
    previous: datetime | None = None
    for sequence, completed_at in completed_rounds:
        if completed_at is None:
            previous = None
            continue
        current_segment = sum(reset <= completed_at for reset in resets)
        if current_segment != manual_segment:
            previous = None
            segment += 1
            manual_segment = current_segment
        if previous is not None and completed_at - previous > window:
            previous = None
            segment += 1
        if previous is not None:
            seconds = round((completed_at - previous).total_seconds())
            if seconds > 0:
                measured.append((sequence, completed_at, seconds, segment))
        previous = completed_at

    latest_segment = segment
    result: list[RoundTempo] = []
    for sequence, completed_at, seconds, segment in measured:
        if live_only and segment != latest_segment:
            continue
        start = completed_at - window
        values = [
            value
            for _, measured_at, value, measured_segment in measured
            if measured_segment == segment and start < measured_at <= completed_at
        ]
        average = Decimal(sum(values)) / Decimal(len(values))
        result.append(RoundTempo(sequence, completed_at, seconds, average, segment))
    return tuple(result)
