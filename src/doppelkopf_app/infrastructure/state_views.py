"""Portable, non-materialized read models; keep v1 SQL immutable for migration 11."""
from sqlalchemy import Date, DateTime, Integer, column, table

SESSION_VIEW_SQL = """
CREATE VIEW session_state_v1 AS
SELECT g.id AS session_id, g.played_on, g.title, g.ended_at, g.bock_counting,
       g.tempo_reset_at, g.start_dealer_position, g.next_dealer_player_id, g.revision,
       s.seat, p.id AS player_id, p.name AS player_name,
       COALESCE(t.points, 0) AS overall_points
FROM game_sessions g
LEFT JOIN game_session_players s ON s.game_session_id = g.id
LEFT JOIN players p ON p.id = s.player_id
LEFT JOIN (SELECT player_id, SUM(points) AS points FROM scores GROUP BY player_id) t
       ON t.player_id = p.id
"""
ROUND_VIEW_SQL = """
CREATE VIEW round_state_v1 AS
SELECT r.id AS round_id, r.game_session_id AS session_id, r.sequence,
       r.dealer_position, r.dealer_player_id, r.entry, r.declaring_party,
       r.active_bocks, r.scheduled_bocks, r.source_row, r.source_seat_order,
       r.completed_at, r.team_signs,
       COALESCE(h.seat, c.seat) AS seat,
       p.id AS player_id, p.name AS player_name, COALESCE(s.points, 0) AS points
FROM rounds r
LEFT JOIN seating_revision_players h ON h.revision_id = r.seating_revision_id
LEFT JOIN game_session_players c ON c.game_session_id = r.game_session_id
       AND h.player_id IS NULL
LEFT JOIN players p ON p.id = COALESCE(h.player_id, c.player_id)
LEFT JOIN scores s ON s.round_id = r.id AND s.player_id = p.id
"""

session_view = table(
    "session_state_v1",
    *[column(n) for n in ("session_id", "title", "bock_counting", "start_dealer_position",
                         "next_dealer_player_id", "seat", "player_id", "player_name",
                         "overall_points")],
    column("played_on", Date), column("ended_at", DateTime),
    column("tempo_reset_at", DateTime), column("revision", Integer),
)
round_view = table(
    "round_state_v1",
    *[column(n) for n in ("round_id", "session_id", "sequence", "dealer_position",
                         "dealer_player_id", "entry", "declaring_party", "active_bocks",
                         "scheduled_bocks", "source_row", "source_seat_order", "team_signs",
                         "seat", "player_id", "player_name", "points")],
    column("completed_at", DateTime),
)
