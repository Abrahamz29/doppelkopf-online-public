"""Decode archived Isar results; never replay them through today's house rules."""

from dataclasses import dataclass

from doppelkopf_app.domain.scoring import DeclaringParty, parse_score_entry


@dataclass(frozen=True)
class ArchivedResult:
    points: tuple[int, int, int, int]
    entry: str
    party: DeclaringParty
    team_signs: str
    active_bocks: int


def decode_isar_result(
    *,
    dealer: int,
    teams: str,
    winner: str,
    points: int,
    bock_factor: int = 1,
) -> ArchivedResult:
    """Rotate forehand-relative teams to table seats; P already includes bocks.

    The minority player receives three times P in a solo. Missing XML P is
    decoded as zero by the adapter, subject to a mandatory per-list total check.
    """
    if dealer not in range(4) or len(teams) != 4 or set(teams) != {"1", "2"}:
        raise ValueError("Ungültige Sitz- oder Parteizuordnung im Isar-Export.")
    if winner not in {"1", "2"}:
        raise ValueError("Ungültiges Isar-Ergebnis.")
    if bock_factor not in {1, 2, 4} or points % bock_factor:
        raise ValueError("Unbekannter Bockfaktor oder nicht teilbarer Punktewert.")
    if teams.count("1") not in {1, 2}:
        raise ValueError("Unbekannte Isar-Parteiverteilung.")
    # Special-point offsets can leave the trick-winning party with negative P.
    # The application's party marker describes the positive scoring side.
    if points < 0:
        winner = "2" if winner == "1" else "1"
        points = -points
    signs = [""] * 4
    for relative_seat, team in enumerate(teams):
        signs[(relative_seat + dealer + 1) % 4] = "+" if team == winner else "-"
    value = points * (3 if teams.count("1") == 1 else 1)
    sign_text = "".join(signs)
    entry = f"{value}{sign_text}" + ("R" if winner == "1" else "K") if points else (f"0{sign_text}")
    parsed = parse_score_entry(entry)
    base_entry = entry.replace(str(value), str(value // bock_factor), 1)
    return ArchivedResult(
        parsed.points, base_entry, parsed.declaring_party, sign_text, bock_factor.bit_length() - 1
    )
