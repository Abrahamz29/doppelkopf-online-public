import re
from dataclasses import dataclass
from enum import StrEnum


class DeclaringParty(StrEnum):
    RE = "Re"
    KONTRA = "Kontra"
    NONE = "Keine"


class ScoreEntryError(ValueError):
    """Raised when a compact score entry cannot describe a valid round."""


@dataclass(frozen=True, slots=True)
class ParsedScoreEntry:
    points: tuple[int, int, int, int]
    declaring_party: DeclaringParty
    scheduled_bocks: int
    team_signs: tuple[str, str, str, str] | None = None

    def __post_init__(self) -> None:
        _validate_point_bounds(self.points)

    @property
    def is_solo(self) -> bool:
        if not any(self.points) and self.team_signs is not None:
            return self.team_signs.count("+") in {1, 3}
        positives = sum(point > 0 for point in self.points)
        negatives = sum(point < 0 for point in self.points)
        return {positives, negatives} == {1, 3}


def parse_score_entry(entry: str) -> ParsedScoreEntry:
    """Parse the workbook's compact value/sign/party notation into four exact scores."""
    if len(entry.strip()) > 80:
        raise ScoreEntryError("Die Ergebniseingabe darf höchstens 80 Zeichen enthalten.")
    normalized = "".join(entry.split())
    if not normalized:
        raise ScoreEntryError("Die Ergebniseingabe darf nicht leer sein.")

    score_notation = "".join(
        character for character in normalized if character.isdigit() or character in "+-"
    )
    notation_match = re.fullmatch(r"(\d+)([+-]{4})", score_notation)
    digits = notation_match.group(1) if notation_match else ""
    signs = tuple(character for character in normalized if character in "+-")
    party_markers = {character.upper() for character in normalized if character.upper() in "RKC"}
    scheduled_bocks = sum(character in "Bb*" for character in normalized)
    allowed = set("0123456789+-RrKkCcBb*")

    if any(character not in allowed for character in normalized):
        raise ScoreEntryError("Die Ergebniseingabe enthält ein unbekanntes Zeichen.")
    if score_notation == "0":
        if party_markers:
            raise ScoreEntryError("Ein Nullspiel hat keine Partei Re oder Kontra.")
        return ParsedScoreEntry((0, 0, 0, 0), DeclaringParty.NONE, scheduled_bocks)
    if notation_match is not None and int(digits) == 0:
        if party_markers:
            raise ScoreEntryError("Ein Nullspiel hat keine Partei Re oder Kontra.")
        if signs.count("+") not in {1, 2, 3}:
            raise ScoreEntryError("Ein Nullspiel benötigt Plus- und Minuszeichen.")
        return ParsedScoreEntry(
            (0, 0, 0, 0),
            DeclaringParty.NONE,
            scheduled_bocks,
            (signs[0], signs[1], signs[2], signs[3]),
        )
    if notation_match is None:
        raise ScoreEntryError("Erwartet werden ein Punktewert und genau vier Vorzeichen.")
    if int(digits) <= 0:
        raise ScoreEntryError("Der Punktewert muss eine positive ganze Zahl sein.")
    if "R" in party_markers and party_markers & {"K", "C"}:
        raise ScoreEntryError("Eine Eingabe darf nicht gleichzeitig Re und Kontra sein.")
    if not party_markers:
        raise ScoreEntryError("Die Partei Re oder Kontra muss angegeben werden.")

    declaring_party = (
        DeclaringParty.RE if "R" in party_markers else DeclaringParty.KONTRA
    )
    points = calculate_round_points(int(digits), signs)
    positive_count = signs.count("+")
    if positive_count == 1 and declaring_party is not DeclaringParty.RE:
        raise ScoreEntryError("Bei einem gewonnenen Solo muss Re angegeben werden.")
    if positive_count == 3 and declaring_party is not DeclaringParty.KONTRA:
        raise ScoreEntryError("Bei einem verlorenen Solo muss Kontra angegeben werden.")
    return ParsedScoreEntry(
        points,
        declaring_party,
        scheduled_bocks,
        (signs[0], signs[1], signs[2], signs[3]),
    )


def calculate_round_points(base_points: int, signs: tuple[str, ...]) -> tuple[int, int, int, int]:
    """Calculate partnership or solo scores while preserving an exact zero sum."""
    if base_points <= 0:
        raise ScoreEntryError("Der Punktewert muss positiv sein.")
    if len(signs) != 4 or any(sign not in {"+", "-"} for sign in signs):
        raise ScoreEntryError("Es werden genau vier gültige Vorzeichen benötigt.")

    positive_count = signs.count("+")
    negative_count = signs.count("-")
    if positive_count == negative_count == 2:
        unit_points = base_points
    elif {positive_count, negative_count} == {1, 3}:
        if base_points % 3:
            raise ScoreEntryError("Solopunkte müssen ohne Rest durch drei teilbar sein.")
        unit_points = base_points // 3
    else:
        raise ScoreEntryError("Das Ergebnis muss ein Partnerspiel oder ein Solo beschreiben.")

    minority_sign = "+" if positive_count == 1 else "-" if negative_count == 1 else None
    points = [
        _score_for_sign(sign, minority_sign, base_points, unit_points) for sign in signs
    ]
    if sum(points) != 0:
        raise ScoreEntryError("Die vier Spielergebnisse müssen zusammen null ergeben.")
    result = points[0], points[1], points[2], points[3]
    _validate_point_bounds(result)
    return result


def _validate_point_bounds(points: tuple[int, int, int, int]) -> None:
    if any(point < -999 or point > 999 for point in points):
        raise ScoreEntryError(
            "Pro Spieler sind einschließlich Bockfaktor nur -999 bis 999 Punkte zulässig."
        )


def _score_for_sign(sign: str, minority_sign: str | None, base: int, unit: int) -> int:
    magnitude = base if sign == minority_sign else unit
    return magnitude if sign == "+" else -magnitude
