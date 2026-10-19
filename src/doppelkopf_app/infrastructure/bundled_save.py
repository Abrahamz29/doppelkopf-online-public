"""Versioned PostgreSQL persistence routine; v1 is immutable after migration 12."""

SAVE_ROUND_SQL = r"""
CREATE FUNCTION save_round_v1(p jsonb) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
SET search_path FROM CURRENT
AS $$
DECLARE
    g game_sessions%ROWTYPE;
    sid integer := (p->>'session_id')::integer;
    expected integer := (p->>'revision')::integer;
    player_ids integer[];
    sequence_no integer;
    seating_id integer;
    dealer_id integer;
    dealer_index integer;
    round_id integer;
    header_rows jsonb;
    round_rows jsonb;
BEGIN
    UPDATE game_sessions SET revision = revision + 1
    WHERE id = sid AND (expected IS NULL OR revision = expected)
    RETURNING * INTO g;
    IF NOT FOUND THEN
        IF NOT EXISTS (SELECT 1 FROM game_sessions WHERE id = sid) THEN
            RAISE EXCEPTION USING ERRCODE = 'DK001', MESSAGE = 'session missing';
        END IF;
        RAISE EXCEPTION USING ERRCODE = 'DK003', MESSAGE = 'stale state';
    END IF;
    IF g.ended_at IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'DK002', MESSAGE = 'session ended';
    END IF;
    SELECT array_agg(player_id ORDER BY seat) INTO player_ids
    FROM game_session_players WHERE game_session_id = sid;
    IF cardinality(player_ids) IS DISTINCT FROM 4 THEN
        RAISE EXCEPTION USING ERRCODE = 'DK003', MESSAGE = 'incomplete seating';
    END IF;
    SELECT COALESCE(MAX(sequence), 0) + 1 INTO sequence_no
    FROM rounds WHERE game_session_id = sid;
    SELECT id INTO seating_id FROM seating_revisions WHERE game_session_id = sid
    ORDER BY revision DESC LIMIT 1;
    dealer_id := g.next_dealer_player_id;
    IF dealer_id IS NULL OR NOT (dealer_id = ANY(player_ids)) THEN
        dealer_id := player_ids[(p->>'dealer_position')::integer + 1];
    END IF;
    dealer_index := array_position(player_ids, dealer_id);
    IF dealer_index IS NULL OR
       (p->>'sequence' IS NOT NULL AND sequence_no <> (p->>'sequence')::integer) OR
       (jsonb_typeof(p->'player_ids') = 'array' AND
        to_jsonb(player_ids) <> p->'player_ids') OR
       (p->>'dealer_id' IS NOT NULL AND dealer_id <> (p->>'dealer_id')::integer) THEN
        RAISE EXCEPTION USING ERRCODE = 'DK003', MESSAGE = 'stale state';
    END IF;
    IF jsonb_array_length(p->'points') IS DISTINCT FROM 4 THEN
        RAISE EXCEPTION USING ERRCODE = 'DK003', MESSAGE = 'invalid points';
    END IF;
    INSERT INTO rounds(game_session_id, sequence, dealer_position, dealer_player_id,
                       seating_revision_id, completed_at, entry, declaring_party,
                       active_bocks, scheduled_bocks, team_signs)
    VALUES(sid, sequence_no, dealer_index - 1, dealer_id, seating_id,
           (p->>'completed_at')::timestamp, p->>'entry', p->>'declaring_party',
           (p->>'active_bocks')::integer, (p->>'scheduled_bocks')::integer,
           p->>'team_signs') RETURNING id INTO round_id;
    INSERT INTO scores(round_id, player_id, points)
    SELECT round_id, player_ids[i], (p->'points'->>(i-1))::integer
    FROM generate_series(1, 4) AS i;
    UPDATE game_sessions SET next_dealer_player_id = player_ids[dealer_index % 4 + 1]
    WHERE id = sid;
    SELECT jsonb_agg(to_jsonb(v) ORDER BY v.seat) INTO header_rows
    FROM session_state_v1 v WHERE v.session_id = sid;
    SELECT COALESCE(jsonb_agg(to_jsonb(v) ORDER BY v.sequence, v.seat), '[]'::jsonb)
    INTO round_rows FROM round_state_v1 v WHERE v.session_id = sid;
    RETURN jsonb_build_object('headers', header_rows, 'rounds', round_rows);
END
$$
"""
