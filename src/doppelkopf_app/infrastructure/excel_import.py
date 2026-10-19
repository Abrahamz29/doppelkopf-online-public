from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from doppelkopf_app.domain.entities import BockCounting
from doppelkopf_app.domain.scoring import DeclaringParty, parse_score_entry
from doppelkopf_app.infrastructure.database import transaction
from doppelkopf_app.infrastructure.models import (
    GameSessionPlayerRecord,
    GameSessionRecord,
    PlayerRecord,
    RoundRecord,
    ScoreRecord,
    SeatingRevisionPlayerRecord,
    SeatingRevisionRecord,
)

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
EXPECTED_SHA256 = "bcbae7d249f0f30d8230f4da0d022ffe7670d37efddf8dfcd2f58cd1b2840e01"
SOURCE_SNAPSHOT_DATE = date(2022, 11, 21)
SOURCE_SNAPSHOT_TIME = datetime(2022, 11, 21, 19, 33, 12)


class ExcelImportError(ValueError):
    """Raised when the historical workbook cannot be imported without guessing."""


@dataclass(frozen=True, slots=True)
class ExcelRound:
    source_row: int
    dealer_position: int
    entry: str
    declaring_party: DeclaringParty
    active_bocks: int
    scheduled_bocks: int
    points: tuple[int, int, int, int]
    seat_order: tuple[str, str, str, str]


@dataclass(frozen=True, slots=True)
class ExcelSession:
    source_reference: str
    title: str
    players: tuple[str, str, str, str]
    start_dealer_position: int
    rounds: tuple[ExcelRound, ...]


@dataclass(frozen=True, slots=True)
class ExcelImportReport:
    sessions_found: int
    sessions_imported: int
    sessions_skipped: int
    rounds_imported: int
    players_created: int


def read_excel_sessions(source: Path) -> tuple[ExcelSession, ...]:
    """Read completed sessions from the immutable workbook's ``Daten`` sheet."""
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ExcelImportError(
            f"Die Excel-Datei hat nicht den dokumentierten SHA-256-Wert: {digest}"
        )
    cells = _read_daten_cells(source)
    fixed_players = tuple(_require_text(cells, 2, column) for column in range(10, 14))
    if len(set(fixed_players)) != 4:
        raise ExcelImportError("Daten!J2:M2 enthält nicht vier verschiedene Spielernamen.")

    blocks: list[tuple[int, int]] = []
    start_row = 4
    last_source_row = max(row for row, _column in cells)
    for row in range(start_row, last_source_row + 1):
        if cells.get((row, 29)) == 35:
            blocks.append((start_row, row))
            start_row = row + 1

    sessions: list[ExcelSession] = []
    for index, (first_row, last_row) in enumerate(blocks, start=1):
        sessions.append(
            _build_session(cells, fixed_players, index, first_row, last_row)
        )
    return tuple(sessions)


def import_excel_test_data(
    factory: sessionmaker[Session], source: Path
) -> ExcelImportReport:
    """Idempotently import completed Excel sessions into the relational model."""
    sessions = read_excel_sessions(source)
    imported = 0
    skipped = 0
    rounds_imported = 0
    players_created = 0
    with transaction(factory) as db:
        players_by_name = {
            player.name: player for player in db.scalars(select(PlayerRecord)).all()
        }
        for name in sorted({name for item in sessions for name in item.players}):
            if name not in players_by_name:
                player = PlayerRecord(name=name)
                db.add(player)
                db.flush()
                players_by_name[name] = player
                players_created += 1

        for item in sessions:
            exists = db.scalar(
                select(GameSessionRecord.id).where(
                    GameSessionRecord.source_reference == item.source_reference
                )
            )
            if exists is not None:
                skipped += 1
                continue
            session = GameSessionRecord(
                played_on=SOURCE_SNAPSHOT_DATE,
                title=item.title,
                ended_at=SOURCE_SNAPSHOT_TIME,
                start_dealer_position=item.start_dealer_position,
                source_reference=item.source_reference,
                bock_counting=BockCounting.MULTIPLICATIVE.value,
            )
            db.add(session)
            db.flush()
            player_ids = tuple(players_by_name[name].id for name in item.players)
            db.add_all(
                GameSessionPlayerRecord(
                    game_session_id=session.id, player_id=player_id, seat=seat
                )
                for seat, player_id in enumerate(player_ids)
            )
            revision = SeatingRevisionRecord(
                game_session_id=session.id,
                revision=1,
                effective_from_sequence=1,
                changed_at=SOURCE_SNAPSHOT_TIME,
            )
            db.add(revision)
            db.flush()
            db.add_all(
                SeatingRevisionPlayerRecord(
                    revision_id=revision.id, player_id=player_id, seat=seat
                )
                for seat, player_id in enumerate(player_ids)
            )
            session.next_dealer_player_id = player_ids[
                (item.start_dealer_position + len(item.rounds)) % 4
            ]
            for sequence, item_round in enumerate(item.rounds, start=1):
                round_record = RoundRecord(
                    game_session_id=session.id,
                    sequence=sequence,
                    dealer_position=item_round.dealer_position,
                    dealer_player_id=player_ids[item_round.dealer_position],
                    seating_revision_id=revision.id,
                    entry=item_round.entry,
                    declaring_party=item_round.declaring_party.value,
                    active_bocks=item_round.active_bocks,
                    scheduled_bocks=item_round.scheduled_bocks,
                    source_row=item_round.source_row,
                    source_seat_order=" ".join(item_round.seat_order),
                )
                db.add(round_record)
                db.flush()
                db.add_all(
                    ScoreRecord(round_id=round_record.id, player_id=player_id, points=points)
                    for player_id, points in zip(player_ids, item_round.points, strict=True)
                )
                rounds_imported += 1
            imported += 1
    return ExcelImportReport(len(sessions), imported, skipped, rounds_imported, players_created)


def _build_session(
    cells: dict[tuple[int, int], object],
    fixed_players: tuple[str, ...],
    index: int,
    first_row: int,
    last_row: int,
) -> ExcelSession:
    order = tuple(_require_text(cells, first_row, 33).split())
    if len(order) != 4 or set(order) != set(fixed_players):
        raise ExcelImportError(f"Daten!AG{first_row} enthält keine gültige Sitzreihenfolge.")
    active_bocks = [len(str(cells.get((row, 14)) or "")) for row in range(first_row, last_row + 1)]
    scheduled_bocks = _derive_scheduled_bocks(active_bocks)
    rounds: list[ExcelRound] = []
    fixed_index = {name: position for position, name in enumerate(fixed_players)}
    for offset, row in enumerate(range(first_row, last_row + 1)):
        fixed_points = tuple(_require_int(cells, row, column) for column in range(10, 14))
        row_order = tuple(_require_text(cells, row, 33).split())
        if len(row_order) != 4 or set(row_order) != set(fixed_players):
            raise ExcelImportError(f"Daten!AG{row} enthält keine gültige Sitzreihenfolge.")
        points = tuple(fixed_points[fixed_index[name]] for name in order)
        row_points = tuple(fixed_points[fixed_index[name]] for name in row_order)
        party_text = _require_text(cells, row, 32)
        try:
            party = DeclaringParty(party_text)
        except ValueError as error:
            raise ExcelImportError(f"Unbekannte Partei in Daten!AF{row}: {party_text}") from error
        dealer_text = _require_text(cells, row, 34)
        dealer_name = dealer_text.removesuffix(" gibt!")
        if dealer_name not in row_order:
            raise ExcelImportError(f"Unbekannter Geber in Daten!AH{row}: {dealer_text}")
        level = active_bocks[offset]
        scheduled = scheduled_bocks[offset]
        entry = _reconstruct_entry(row_points, party, level, scheduled, row)
        rounds.append(
            ExcelRound(
                row,
                order.index(dealer_name),
                entry,
                party,
                level,
                scheduled,
                (points[0], points[1], points[2], points[3]),
                (row_order[0], row_order[1], row_order[2], row_order[3]),
            )
        )
    return ExcelSession(
        source_reference=f"excel:Daten:{first_row}-{last_row}",
        title=f"Excel-Spieltag {index} (Datum unbekannt)",
        players=(order[0], order[1], order[2], order[3]),
        start_dealer_position=rounds[0].dealer_position,
        rounds=tuple(rounds),
    )


def _derive_scheduled_bocks(active: list[int]) -> list[int]:
    scheduled = [0] * len(active)
    for index in range(len(active) - 1):
        carried = sum(scheduled[max(0, index - 3) : index])
        scheduled[index] = active[index + 1] - carried
        if scheduled[index] < 0:
            raise ExcelImportError("Die Bockwarteschlange in Daten!N ist nicht rekonstruierbar.")
    return scheduled


def _reconstruct_entry(
    points: tuple[int, ...],
    party: DeclaringParty,
    active_bocks: int,
    scheduled_bocks: int,
    source_row: int,
) -> str:
    marker = "R" if party is DeclaringParty.RE else "K"
    if all(point == 0 for point in points):
        return f"{'B' * scheduled_bocks}0 (Excel-Nullspiel) {marker}"
    factor = 2**active_bocks
    if any(point % factor for point in points):
        raise ExcelImportError(f"Daten!J{source_row}:M{source_row} passt nicht zum Bockfaktor.")
    raw = tuple(point // factor for point in points)
    positive_count = sum(point > 0 for point in raw)
    negative_count = sum(point < 0 for point in raw)
    if positive_count == negative_count == 2:
        base = abs(raw[0])
    elif {positive_count, negative_count} == {1, 3}:
        minority_positive = positive_count == 1
        base = abs(next(point for point in raw if (point > 0) == minority_positive))
    else:
        raise ExcelImportError(f"Daten!J{source_row}:M{source_row} ist kein gültiges Ergebnis.")
    signs = "".join("+" if point > 0 else "-" for point in raw)
    entry = f"{'B' * scheduled_bocks}{base}{signs}{marker}"
    parsed = parse_score_entry(entry)
    expected = tuple(point * factor for point in parsed.points)
    if expected != points:
        raise ExcelImportError(f"Rekonstruktion von Datenzeile {source_row} ist nicht verlustfrei.")
    return entry


def _read_daten_cells(source: Path) -> dict[tuple[int, int], object]:
    with zipfile.ZipFile(source) as archive:
        shared = _shared_strings(archive)
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    cells: dict[tuple[int, int], object] = {}
    for node in root.findall(f".//{{{MAIN_NS}}}c"):
        reference = node.attrib["r"]
        match = re.fullmatch(r"([A-Z]+)(\d+)", reference)
        if match is None:
            continue
        column = _column_number(match.group(1))
        row = int(match.group(2))
        value_node = node.find(f"{{{MAIN_NS}}}v")
        if value_node is None or value_node.text is None:
            continue
        raw = value_node.text
        cell_type = node.attrib.get("t")
        if cell_type == "s":
            value: object = shared[int(raw)]
        elif cell_type == "b":
            value = raw == "1"
        elif cell_type in {"str", "inlineStr"}:
            value = raw
        else:
            number = float(raw)
            value = int(number) if number.is_integer() else number
        cells[(row, column)] = value
    return cells


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t")) for item in root]


def _column_number(letters: str) -> int:
    result = 0
    for character in letters:
        result = result * 26 + ord(character) - ord("A") + 1
    return result


def _require_text(cells: dict[tuple[int, int], object], row: int, column: int) -> str:
    value = cells.get((row, column))
    if not isinstance(value, str) or not value.strip():
        raise ExcelImportError(f"Erwarteter Text fehlt in Zeile {row}, Spalte {column}.")
    return value.strip()


def _require_int(cells: dict[tuple[int, int], object], row: int, column: int) -> int:
    value = cells.get((row, column))
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExcelImportError(f"Erwartete Ganzzahl fehlt in Zeile {row}, Spalte {column}.")
    return value
