from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class BockCounting(StrEnum):
    """Determine how simultaneous Bock announcements change a score."""

    ADDITIVE = "additive"
    MULTIPLICATIVE = "multiplicative"
    APPEND = "append"

    def factor(self, active_bocks: int) -> int:
        if active_bocks < 0:
            raise ValueError("Die Anzahl aktiver Bocks darf nicht negativ sein.")
        if self is BockCounting.APPEND:
            return 2 if active_bocks else 1
        if self is BockCounting.ADDITIVE:
            return active_bocks + 1
        return int(2**active_bocks)


@dataclass(frozen=True, slots=True)
class Player:
    name: str

    def __post_init__(self) -> None:
        normalized = self.name.strip()
        if not normalized:
            raise ValueError("Der Spielername darf nicht leer sein.")
        if len(normalized) > 120:
            raise ValueError("Der Spielername darf höchstens 120 Zeichen enthalten.")
        object.__setattr__(self, "name", normalized)


@dataclass(frozen=True, slots=True)
class GameSession:
    played_on: date
    title: str
    bock_counting: BockCounting = BockCounting.ADDITIVE

    def __post_init__(self) -> None:
        normalized = self.title.strip()
        if not normalized:
            raise ValueError("Die Bezeichnung des Spielabends darf nicht leer sein.")
        if len(normalized) > 200:
            raise ValueError(
                "Die Bezeichnung des Spielabends darf höchstens 200 Zeichen enthalten."
            )
        object.__setattr__(self, "title", normalized)

