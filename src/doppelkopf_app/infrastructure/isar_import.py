"""Validated, atomic and repeatable import of the local friends-game export."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from doppelkopf_app.domain.isar_import import ArchivedResult, decode_isar_result
from doppelkopf_app.infrastructure.database import transaction
from doppelkopf_app.infrastructure.models import (
    GameSessionPlayerRecord,
    GameSessionRecord,
    IsarGameRecord,
    IsarPlayerRecord,
    IsarSessionRecord,
    PlayerRecord,
    RoundRecord,
    ScoreRecord,
    SeatingRevisionPlayerRecord,
    SeatingRevisionRecord,
)


class SourceNode(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow")
    tag: str
    attributes: dict[str, str]
    children: list[SourceNode] = Field(default_factory=list)


class SourceGame(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow")
    list_id: str
    game_number: int = Field(gt=0)
    raw_tree: SourceNode
    tricks: list[dict[str, Any]]


class SourceSession(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow")
    id: str
    state: str
    table_attributes: dict[str, str]
    games: list[SourceGame]
    rules: list[dict[str, str]]


@dataclass(frozen=True)
class PreparedGame:
    source: SourceGame
    dealer: int
    result: ArchivedResult | None


@dataclass(frozen=True)
class PreparedSession:
    source: SourceSession
    players: tuple[str, ...]
    created: datetime
    updated: datetime
    games: tuple[PreparedGame, ...]
    totals: tuple[int, ...]
    payload: dict[str, Any]
    digest: str


@dataclass(frozen=True)
class ImportReport:
    sessions_imported: int
    sessions_skipped: int
    rounds_imported: int
    source_games_imported: int
    players_created: int


def _timestamp(value: str) -> datetime:
    return datetime.fromtimestamp(int(value), UTC).replace(tzinfo=None)


def _uuid(value: str) -> str:
    if str(UUID(value)) != value:
        raise ValueError("Quell-ID muss eine kanonische UUID sein.")
    return value


def prepare_isar_import(source: Path, statistics: Path) -> tuple[PreparedSession, ...]:
    """Validate every game and reconcile each player's list total before any write."""
    raw = json.loads(source.read_text(encoding="utf-8"))
    sessions = TypeAdapter(list[SourceSession]).validate_python(raw["lists"])
    stats = json.loads(statistics.read_text(encoding="utf-8"))
    if stats["category"] != "friends":
        raise ValueError("Es werden ausschließlich Freundes-Spieltage importiert.")
    by_id = {item["list_id"]: item for item in stats["lists"]}
    if (
        len(by_id) != len(stats["lists"])
        or len({s.id for s in sessions}) != len(sessions)
        or set(by_id) != {s.id for s in sessions}
    ):
        raise ValueError("Doppelte oder fehlende Spieltage im Quellenabgleich.")
    prepared = []
    for source_session in sessions:
        _uuid(source_session.id)
        if source_session.state != "finished":
            raise ValueError("Nur abgeschlossene Spieltage können importiert werden.")
        attrs = source_session.table_attributes
        if attrs["UID"] != source_session.id:
            raise ValueError("Tisch-ID stimmt nicht überein.")
        players = tuple(_uuid(attrs[f"PUID{i}"]) for i in range(4))
        if len(set(players)) != 4:
            raise ValueError("Vier verschiedene Quellspieler erforderlich.")
        created, updated = _timestamp(attrs["CREATED"]), _timestamp(attrs["UPDATED"])
        if updated < created:
            raise ValueError("Ungültiger Zeitraum.")
        games = tuple(
            _prepare_game(g, source_session.id, i) for i, g in enumerate(source_session.games, 1)
        )
        stat = by_id[source_session.id]
        if len(games) != stat["completed_games_reported"] or not games:
            raise ValueError("Spieleanzahl stimmt nicht mit der Quellstatistik überein.")
        reported = {p["player_id"]: p["metrics"].get("P", 0) for p in stat["players"]}
        if set(reported) != set(players) or len(stat["players"]) != 4:
            raise ValueError("Spieler der Statistik stimmen nicht mit dem Tisch überein.")
        totals = tuple(sum(g.result.points[i] for g in games if g.result) for i in range(4))
        if any(type(reported[p]) is not int for p in players):
            raise ValueError("Ganzzahlige Statistikpunkte erforderlich.")
        if totals != tuple(reported[p] for p in players):
            raise ValueError(f"Punkteabgleich fehlgeschlagen: {source_session.id}")
        payload = source_session.model_dump(exclude_unset=True)
        payload["statistics"] = stat
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
        prepared.append(
            PreparedSession(
                source_session,
                players,
                created,
                updated,
                games,
                totals,
                payload,
                digest,
            )
        )
    return tuple(sorted(prepared, key=lambda s: (s.created, s.source.id)))


def _prepare_game(game: SourceGame, session_id: str, number: int) -> PreparedGame:
    if game.list_id != session_id or game.game_number != number or game.raw_tree.tag != "GAME":
        raise ValueError("Ungültige Spielreihenfolge oder Quellzuordnung.")
    nodes = game.raw_tree.children
    contexts = [n.attributes for n in nodes if n.tag == "CONTEXTNORMALGAME"]
    situations = [n.attributes for n in nodes if n.tag == "DOKOGAMESITUATION"]
    if len(contexts) != 1 or len(situations) != 1:
        raise ValueError("Spielkontext oder Ergebnis fehlt bzw. ist doppelt.")
    dealer = int(contexts[0]["DEALER"])
    if dealer not in range(4):
        raise ValueError("Ungültiger Geber.")
    situation = situations[0]
    if situation.get("NOGAME") == "1":
        if game.tricks or int(situation.get("P", "0")) != 0:
            raise ValueError("NOGAME enthält unerwartet gespielte Stiche oder Punkte.")
        return PreparedGame(game, dealer, None)
    if "NOGAME" in situation or not game.tricks:
        raise ValueError("Unbekannter Spielstatus oder fehlende Stichdaten.")
    result = decode_isar_result(
        dealer=dealer,
        teams=situation["TEAM"],
        winner=situation["W"],
        points=int(situation.get("P", "0")),
        bock_factor=int(situation.get("BOCKRUNDE_FACTOR", "1")),
    )
    return PreparedGame(game, dealer, result)


def import_isar_sessions(
    factory: sessionmaker[Session],
    sessions: tuple[PreparedSession, ...],
    names: dict[str, str],
) -> ImportReport:
    """Commit all verified lists together; identical imports skip, changed ones fail."""
    ids = {uid for item in sessions for uid in item.players}
    if set(names) != ids or len(set(names.values())) != len(names):
        raise ValueError("Vollständige eindeutige Namenszuordnung erforderlich.")
    if any(not n.strip() or n != n.strip() or len(n) > 120 for n in names.values()):
        raise ValueError("Ungültiger Spielername.")
    imported = skipped = rounds = records = created = 0
    with transaction(factory) as db:
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(2026102016)"))
        player_ids: dict[str, int] = {}
        for uid in sorted(ids):
            existing = db.get(IsarPlayerRecord, uid)
            if existing:
                player_ids[uid] = existing.player_id
                continue
            if db.scalar(select(PlayerRecord.id).where(PlayerRecord.name == names[uid])):
                raise ValueError(
                    "Name bereits ohne Quellzuordnung vorhanden; kein blindes Mischen."
                )
            player = PlayerRecord(name=names[uid])
            db.add(player)
            db.flush()
            db.add(IsarPlayerRecord(source_id=uid, player_id=player.id))
            player_ids[uid] = player.id
            created += 1
        for item in sessions:
            existing_session = db.get(IsarSessionRecord, item.source.id)
            if existing_session:
                if existing_session.sha256 != item.digest:
                    raise ValueError("Bereits importierter Spieltag hat veränderte Quelldaten.")
                skipped += 1
                continue
            _write_session(db, item, player_ids)
            imported += 1
            rounds += sum(g.result is not None for g in item.games)
            records += len(item.games)
    return ImportReport(imported, skipped, rounds, records, created)


def _write_session(db: Session, item: PreparedSession, players: dict[str, int]) -> None:
    ids = [players[uid] for uid in item.players]
    day = item.created.replace(tzinfo=UTC).astimezone(ZoneInfo("Europe/Berlin")).date()
    session = GameSessionRecord(
        played_on=day,
        title=f"Online {day:%d.%m.%Y} · {item.source.id[:8]}",
        created_at=item.created,
        ended_at=item.updated,
        bock_counting="multiplicative",
        start_dealer_position=item.games[0].dealer,
        source_reference=f"isar:friends:{item.source.id}",
    )
    db.add(session)
    db.flush()
    db.add_all(
        GameSessionPlayerRecord(game_session_id=session.id, player_id=pid, seat=i)
        for i, pid in enumerate(ids)
    )
    revision = SeatingRevisionRecord(
        game_session_id=session.id,
        revision=1,
        effective_from_sequence=1,
        changed_at=item.created,
    )
    db.add(revision)
    db.flush()
    db.add_all(
        SeatingRevisionPlayerRecord(revision_id=revision.id, player_id=pid, seat=i)
        for i, pid in enumerate(ids)
    )
    metadata = {k: v for k, v in item.payload.items() if k != "games"}
    db.add(
        IsarSessionRecord(
            source_id=item.source.id, session_id=session.id, sha256=item.digest, payload=metadata
        )
    )
    db.flush()
    sequence = 0
    records: dict[int, RoundRecord] = {}
    for game in item.games:
        if game.result is not None:
            sequence += 1
            result = game.result
            record = RoundRecord(
                game_session_id=session.id,
                sequence=sequence,
                dealer_position=game.dealer,
                dealer_player_id=ids[game.dealer],
                seating_revision_id=revision.id,
                entry=result.entry,
                declaring_party=result.party.value,
                team_signs=result.team_signs,
                active_bocks=result.active_bocks,
                scheduled_bocks=0,
                source_row=game.source.game_number,
                source_seat_order=" ".join(item.players),
            )
            db.add(record)
            records[game.source.game_number] = record
    db.flush()
    for game in item.games:
        record_or_none = records.get(game.source.game_number)
        round_id = record_or_none.id if record_or_none is not None else None
        if game.result is not None and record_or_none is not None:
            db.add_all(
                ScoreRecord(round_id=record_or_none.id, player_id=pid, points=points)
                for pid, points in zip(ids, game.result.points, strict=True)
            )
        db.add(
            IsarGameRecord(
                source_session_id=item.source.id,
                source_number=game.source.game_number,
                round_id=round_id,
                payload=game.source.model_dump(exclude_unset=True),
            )
        )
