from collections.abc import Sequence

from doppelkopf_app.domain.entities import BockCounting


def _advance_appended_bocks(pending: int, announcements: int) -> int:
    if announcements < 0:
        raise ValueError("Bockvormerkungen dürfen nicht negativ sein.")
    return max(0, pending - 1) + 4 * announcements


def remaining_appended_bocks(announcements: Sequence[int]) -> int:
    """Count all unplayed appended Bock games after the recorded games."""
    pending = 0
    for count in announcements:
        pending = _advance_appended_bocks(pending, count)
    return pending


def bock_levels(announcements: Sequence[int], mode: BockCounting) -> tuple[int, ...]:
    """Return active Bocks for recorded games and the next four games."""
    if any(count < 0 for count in announcements):
        raise ValueError("Bockvormerkungen dürfen nicht negativ sein.")
    levels: list[int] = []
    pending = 0
    for index in range(len(announcements) + 4):
        if mode is BockCounting.APPEND:
            levels.append(int(pending > 0))
            pending = _advance_appended_bocks(
                pending, announcements[index] if index < len(announcements) else 0
            )
        else:
            levels.append(sum(announcements[max(0, index - 4) : index]))
    return tuple(levels)
