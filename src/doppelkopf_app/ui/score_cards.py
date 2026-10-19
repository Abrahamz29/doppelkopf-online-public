from html import escape

import streamlit as st

from doppelkopf_app.application.services import PlayerSummary


def format_points(points: int, zero_sign: str | None = None) -> str:
    if points == 0:
        return f"{zero_sign}0" if zero_sign in {"+", "-"} else "0"
    return f"{points:+d}"


def render_score_cards(
    players: tuple[PlayerSummary, ...],
    totals: tuple[int, int, int, int],
    last_round_points: tuple[int, int, int, int] | None,
    dealer_position: int | None,
    last_round_team_signs: tuple[str, str, str, str] | None = None,
) -> None:
    """Render four compact, non-wrapping score tiles for narrow screens."""
    cards = []
    for index, (player, total) in enumerate(zip(players, totals, strict=True)):
        name = escape(player.name)
        is_dealer = index == dealer_position
        dealer_marker = (
            '<span class="dealer-marker" title="Aktueller Geber" aria-hidden="true">G</span>'
            if is_dealer
            else ""
        )
        dealer_text = ", aktueller Geber" if is_dealer else ""
        latest = last_round_points[index] if last_round_points is not None else None
        zero_sign = last_round_team_signs[index] if last_round_team_signs is not None else None
        latest_text = (
            f", letztes Spiel {format_points(latest, zero_sign)} Punkte"
            if latest is not None
            else ""
        )
        latest_markup = (
            '<span class="score-last" '
            f'title="Letztes Spiel: {format_points(latest, zero_sign)} Punkte">'
            f'({format_points(latest, zero_sign)})</span>'
            if latest is not None
            else ""
        )
        cards.append(
            f'<div class="score-card{" dealer" if is_dealer else ""}" '
            f'aria-label="Sitz {index + 1}, {name}{dealer_text}, '
            f'{format_points(total)} Punkte{latest_text}">'
            f'<div class="score-name"><span>{index + 1}. {name}</span>{dealer_marker}</div>'
            f'<div class="score-values"><span class="score-value">{format_points(total)}</span>'
            f"{latest_markup}</div></div>"
        )
    st.html(
        """
        <style>
        .compact-score-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr));
          gap:.38rem; margin:.15rem 0 .45rem; }
        .compact-score-grid .score-card { min-width:0; padding:.48rem .52rem;
          border:1px solid color-mix(in srgb, var(--st-text-color) 24%, transparent);
          border-radius:.7rem;
          background:color-mix(in srgb, var(--st-background-color) 90%, transparent); }
        .compact-score-grid .score-card.dealer { border-color:var(--doko-dealer-border);
          background:var(--doko-dealer-background); color:var(--doko-dealer-text);
          box-shadow:inset 0 0 0 1px
            color-mix(in srgb, var(--doko-dealer-border) 22%, transparent); }
        .compact-score-grid .score-name { display:flex; align-items:center;
          justify-content:space-between;
          gap:.2rem; min-width:0; font-size:clamp(.67rem,2.6vw,.88rem); font-weight:700; }
        .compact-score-grid .score-name > span:first-child { overflow:hidden;
          text-overflow:ellipsis;
          white-space:nowrap; }
        .compact-score-grid .score-values { display:flex; align-items:baseline; gap:.28rem;
          min-width:0; margin-top:.08rem; white-space:nowrap; }
        .compact-score-grid .score-value { font-size:clamp(1.3rem,5vw,1.8rem);
          line-height:1.05; font-variant-numeric:tabular-nums; }
        .compact-score-grid .score-last { font-size:clamp(.62rem,2.1vw,.78rem);
          line-height:1; font-weight:600; opacity:.66; font-variant-numeric:tabular-nums; }
        .compact-score-grid .dealer-marker { flex:0 0 auto; display:inline-grid; place-items:center;
          width:1.12rem; height:1.12rem; border-radius:50%;
          background:var(--doko-dealer-marker); color:white;
          font-size:.62rem; font-weight:800; }
        @media (max-width:640px) {
          .compact-score-grid { gap:.22rem; margin:0 0 .3rem;
            font-size:clamp(1.2rem,calc(1.02rem + .75vw),1.22rem); }
          .compact-score-grid .score-card { padding:.38rem .32rem; border-radius:.5rem; }
          .compact-score-grid .score-name { font-size:clamp(.58em,3.24vw,.72em); }
          .compact-score-grid .score-values { gap:.16rem; margin-top:0; }
          .compact-score-grid .score-value { font-size:clamp(1.05em,6vw,1.35em); }
          .compact-score-grid .score-last { font-size:clamp(.52em,2.64vw,.65em); }
          .compact-score-grid .dealer-marker { width:.9rem; height:.9rem; font-size:.52em; }
        }
        @media (max-width:340px) {
          .compact-score-grid { font-size:1.15rem; }
          .compact-score-grid .score-name { font-size:clamp(.58em,3.1vw,.72em); }
          .compact-score-grid .score-value { font-size:clamp(1.05em,5.75vw,1.35em); }
          .compact-score-grid .score-last { font-size:clamp(.52em,2.53vw,.65em); }
        }
        </style>
        <div class="compact-score-grid">"""
        + "".join(cards)
        + "</div>"
    )


def render_dashboard_score_cards(
    players: tuple[PlayerSummary, ...],
    totals: tuple[int, int, int, int],
    last_round_points: tuple[int, int, int, int] | None,
    dealer_position: int | None,
    last_round_team_signs: tuple[str, str, str, str] | None = None,
) -> None:
    """Render prominent score cards for the wide live dashboard."""
    cards = []
    ranking = {
        player.id: position
        for position, (player, _) in enumerate(
            sorted(zip(players, totals, strict=True), key=lambda item: item[1], reverse=True),
            start=1,
        )
    }
    for index, (player, total) in enumerate(zip(players, totals, strict=True)):
        name = escape(player.name)
        is_dealer = index == dealer_position
        latest = last_round_points[index] if last_round_points is not None else None
        zero_sign = last_round_team_signs[index] if last_round_team_signs is not None else None
        latest_markup = (
            f'<span class="dashboard-score-last">({format_points(latest, zero_sign)})</span>'
            if latest is not None
            else '<span class="dashboard-score-last">(–)</span>'
        )
        dealer_markup = '<span class="dashboard-dealer">Gibt</span>' if is_dealer else ""
        cards.append(
            f'<article class="dashboard-score-card{" dealer" if is_dealer else ""}">'
            f'<div class="dashboard-score-head"><div class="dashboard-score-identity">'
            f'<span class="dashboard-score-name">{name}</span>'
            f'<span class="dashboard-score-rank"> · #{ranking[player.id]}</span></div>'
            f"{dealer_markup}</div>"
            f'<div class="dashboard-score-value">{format_points(total)}</div>'
            f"{latest_markup}</article>"
        )
    st.html(
        """
        <style>
        .dashboard-score-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr));
          gap:.6rem; margin:0 0 .15rem; }
        .dashboard-score-card { min-width:0; padding:.45rem .75rem;
          border:1px solid color-mix(in srgb,var(--st-text-color) 22%,transparent);
          border-radius:1rem;
          background:color-mix(in srgb,var(--st-background-color) 86%,transparent);
          box-shadow:0 .35rem 1.1rem color-mix(in srgb,#000 15%,transparent); }
        .dashboard-score-card.dealer { border-color:var(--doko-dealer-border);
          background:var(--doko-dealer-background); color:var(--doko-dealer-text); }
        .dashboard-score-head { display:flex; align-items:center; gap:.4rem;
          justify-content:space-between; font-size:.82rem; font-weight:750; }
        .dashboard-score-identity { display:flex; align-items:baseline; min-width:0;
          font-size:clamp(.95rem,1.3vw,1.2rem); }
        .dashboard-score-rank { flex-shrink:0; white-space:pre; opacity:.72; }
        .dashboard-dealer { flex-shrink:0; padding:.16rem .55rem; border-radius:999px;
          background:var(--doko-dealer-marker); color:#fff; opacity:1; }
        .dashboard-score-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
          min-width:0; font-weight:750; }
        .dashboard-score-value { margin:.08rem 0 0; font-size:clamp(2rem,3.15vw,3.1rem);
          line-height:1; font-variant-numeric:tabular-nums; letter-spacing:-.035em; }
        .dashboard-score-last { display:inline-block; margin-top:.03rem; font-size:1.08rem;
          line-height:1; font-weight:650; opacity:.72; font-variant-numeric:tabular-nums; }
        @media (min-width:768px) {
          .dashboard-score-identity { font-size:clamp(1.235rem,1.69vw,1.56rem); }
          .dashboard-score-last { font-size:1.404rem; }
        }
        @media (min-width:901px) {
          .dashboard-score-value { font-size:clamp(3.5rem,4.5vw,4rem); }
          .dashboard-score-last { font-size:2.275rem; opacity:1; }
        }
        @media (max-width:900px) {
          .dashboard-score-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
        }
        </style>
        <div class="dashboard-score-grid">"""
        + "".join(cards)
        + "</div>"
    )
