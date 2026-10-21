from unittest.mock import patch

import altair as alt
import pytest

from doppelkopf_app.domain.scoring import DeclaringParty
from doppelkopf_app.domain.statistics import StatisticalRound, calculate_statistics
from doppelkopf_app.ui.statistics_charts import (
    render_point_distribution,
    render_statistics_bars,
)


def test_peak_normalization_uses_selected_filter_peak_and_current_app_counts():
    names = ("A", "B", "C", "D")
    # Peaks differ: overall/Bock = 3 games, without Bock = 2 games.
    statistics = calculate_statistics(names, tuple(
        StatisticalRound(i, DeclaringParty.RE,
                         tuple(zip(names, (points, points, -points, -points), strict=True)),
                         active_bocks=int(i < 3))
        for i, points in enumerate([2, 2, 2, 4, 4, 6, 8, 8, 10, 10])
    ))
    with patch("doppelkopf_app.ui.statistics_charts.st.vega_lite_chart") as chart:
        render_point_distribution(statistics)
    rows, spec = chart.call_args.args
    assert max(row["Gesamt"] for row in rows) == 3
    assert max(row["Gesamt · Ohne Bock"] for row in rows) == 2
    assert max(row["Gesamt · Nur Bock"] for row in rows) == 3
    assert spec["transform"][2]["joinaggregate"][-1] == {
        "op": "max", "field": "Häufigkeit", "as": "Peak im Filter",
    }
    assert spec["transform"][4] == {
        "calculate": "datum['Peak im Filter'] > 0 "
                     "? datum['Häufigkeit'] / datum['Peak im Filter'] : 0",
        "as": "Peakhöhe",
    }
    assert spec["transform"][5] == {
        "calculate": "normalize_distribution ? datum['Peakhöhe'] : datum['Häufigkeit']",
        "as": "Darstellung",
    }
    assert spec["layer"][0]["encoding"]["y"]["scale"]["domainMax"] == {
        "expr": "normalize_distribution ? 1 : 3",
    }
    assert spec["layer"][0]["encoding"]["y"]["axis"]["tickMinStep"] == {
        "expr": "normalize_distribution ? 0.2 : 1",
    }


@pytest.mark.parametrize("selection,expected", [
    ("Gesamt", [1, 1, 1]),
    ("Re (Normalspiel)", [1, 0, 0]),
    ("Kontra (Normalspiel)", [0, 1, 0]),
    ("Solo Re", [0, 0, 1]),
])
def test_distribution_keeps_overall_x_scale_and_ticks(selection, expected):
    names = ("A", "B", "C", "D")
    statistics = calculate_statistics(names, (
        StatisticalRound(1, DeclaringParty.RE, tuple(zip(names, (2, 2, -2, -2), strict=True))),
        StatisticalRound(2, DeclaringParty.KONTRA, tuple(zip(names, (4, -4, 4, -4), strict=True))),
        StatisticalRound(3, DeclaringParty.RE, tuple(zip(names, (18, -6, -6, -6), strict=True))),
    ))
    with patch("doppelkopf_app.ui.statistics_charts.st.vega_lite_chart") as chart:
        render_point_distribution(statistics)
    rows, spec = chart.call_args.args
    assert [row["Punktewert"] for row in rows] == [2, 4, 18]
    assert [row[selection] for row in rows] == expected
    assert spec["layer"][0]["encoding"]["x"]["scale"]["domain"] == [2, 4, 18]
    assert spec["layer"][0]["encoding"]["x"]["axis"]["values"] == [2, 4, 18]
    assert spec["params"][0]["bind"]["options"] == [
        "Gesamt", "Re (Normalspiel)", "Kontra (Normalspiel)", "Solo Re",
    ]
    assert spec["params"][0]["value"] == "Gesamt"
    assert spec["transform"][:2] == [
        {"calculate": "datum[point_distribution + (bock_distribution === 'Mit Bock' "
                      "? '' : ' · ' + bock_distribution)]", "as": "Häufigkeit"},
        {"calculate": "point_distribution", "as": "Auswahl"},
    ]
    assert spec["params"][1] == {
        "name": "normalize_distribution", "value": False,
        "bind": {"input": "checkbox", "name": "Normalisieren"},
    }
    assert spec["params"][2] == {
        "name": "bock_distribution", "value": "Mit Bock",
        "bind": {"input": "select", "name": "Bockfilter",
                 "options": ["Mit Bock", "Ohne Bock", "Nur Bock"]},
    }
    assert [row[f"{selection} · Ohne Bock"] for row in rows] == expected
    assert [row[f"{selection} · Nur Bock"] for row in rows] == [0, 0, 0]
    y_axis = spec["layer"][0]["encoding"]["y"]
    assert y_axis["scale"]["domainMin"] == 0
    assert y_axis["scale"]["domainMax"] == {"expr": "normalize_distribution ? 1 : 1"}
    assert y_axis["scale"]["nice"] is False
    assert spec["transform"][2]["joinaggregate"][0]["field"] == "Häufigkeit"
    assert spec["transform"][3]["calculate"].endswith(": 0")
    assert chart.call_args.kwargs["on_select"] == "ignore"
    alt.Chart.from_dict({**spec, "data": {"values": rows}})


def test_empty_distribution_keeps_overall_x_axis():
    names = ("A", "B", "C", "D")
    statistics = calculate_statistics(names, (
        StatisticalRound(1, DeclaringParty.RE, tuple(zip(names, (4, 4, -4, -4), strict=True))),
    ))
    with patch("doppelkopf_app.ui.statistics_charts.st.vega_lite_chart") as chart:
        render_point_distribution(statistics)
    rows, spec = chart.call_args.args
    assert rows[0]["Solo Re"] == 0
    assert spec["transform"][4]["calculate"].endswith(": 0")
    assert spec["layer"][0]["encoding"]["x"]["scale"]["domain"] == [4]
    assert spec["layer"][1]["transform"][-1] == {"filter": "datum.Anzahl === 0"}
    assert "keine Spiele" in spec["layer"][1]["encoding"]["text"]["value"]


@pytest.mark.parametrize("selection,without,only", [
    ("Gesamt", [2, 0, 1, 0], [0, 2, 0, 1]),
    ("Re (Normalspiel)", [1, 0, 0, 0], [0, 1, 0, 0]),
    ("Kontra (Normalspiel)", [1, 0, 0, 0], [0, 1, 0, 0]),
    ("Solo Re", [0, 0, 1, 0], [0, 0, 0, 1]),
])
def test_distribution_combines_bock_and_party_filters(selection, without, only):
    names = ("A", "B", "C", "D")
    statistics = calculate_statistics(names, tuple(
        StatisticalRound(i, party, tuple(zip(names, points, strict=True)), active_bocks=bocks)
        for i, (party, points, bocks) in enumerate([
            (DeclaringParty.RE, (4, 4, -4, -4), 0),
            (DeclaringParty.KONTRA, (4, -4, 4, -4), 0),
            (DeclaringParty.RE, (12, -4, -4, -4), 0),
            (DeclaringParty.RE, (8, 8, -8, -8), 1),
            (DeclaringParty.KONTRA, (8, -8, 8, -8), 2),
            (DeclaringParty.RE, (24, -8, -8, -8), 3),
        ])
    ))
    with patch("doppelkopf_app.ui.statistics_charts.st.vega_lite_chart") as chart:
        render_point_distribution(statistics)
    rows, spec = chart.call_args.args
    assert [row["Punktewert"] for row in rows] == [4, 8, 12, 24]
    assert [row[f"{selection} · Ohne Bock"] for row in rows] == without
    assert [row[f"{selection} · Nur Bock"] for row in rows] == only
    assert [row[selection] for row in rows] == [a + b for a, b in zip(without, only, strict=True)]
    # Neither filter can shrink the common absolute Y scale.
    assert spec["layer"][0]["encoding"]["y"]["scale"]["domainMax"] == {
        "expr": "normalize_distribution ? 1 : 2",
    }


@pytest.mark.parametrize("count", [1, 1000])
def test_distribution_sends_aggregates_without_server_filter(count):
    names = ("A", "B", "C", "D")
    statistics = calculate_statistics(names, tuple(
        StatisticalRound(i, DeclaringParty.RE,
                         tuple(zip(names, (4, 4, -4, -4), strict=True)))
        for i in range(count)
    ))
    with (
        patch("doppelkopf_app.ui.statistics_charts.st.selectbox") as server_filter,
        patch("doppelkopf_app.ui.statistics_charts.st.vega_lite_chart") as chart,
    ):
        render_point_distribution(statistics)
    server_filter.assert_not_called()
    rows, spec = chart.call_args.args
    categories = {"Gesamt": count, "Re (Normalspiel)": count,
                  "Kontra (Normalspiel)": 0, "Solo Re": 0}
    assert rows == [{"Punktewert": 4, **categories,
                     **{f"{name} · Ohne Bock": value for name, value in categories.items()},
                     **{f"{name} · Nur Bock": 0 for name in categories}}]
    assert spec["layer"][0]["encoding"]["y"]["scale"]["domainMax"] == {
        "expr": f"normalize_distribution ? 1 : {count}",
    }


@pytest.mark.parametrize("count", [1, 1000])
@pytest.mark.parametrize("pairs", [False, True])
def test_kpi_charts_send_only_aggregates_and_use_browser_binding(count, pairs):
    names = ("Anna", "Berta", "Clara", "Dora")
    statistics = calculate_statistics(names, tuple(
        StatisticalRound(i, DeclaringParty.RE,
                         tuple(zip(names, (3, 3, -3, -3), strict=True)),
                         team_signs=("+", "+", "-", "-"))
        for i in range(1, count + 1)
    ))
    with patch("doppelkopf_app.ui.statistics_charts.st.vega_lite_chart") as chart:
        render_statistics_bars(statistics, pairs=pairs)
    rows, spec = chart.call_args.args
    # Payload cardinality is independent of the number of games.
    assert len(rows) == (len(statistics.pairs) if pairs else 4)
    assert all("Spiel" not in row for row in rows)
    assert chart.call_args.kwargs["on_select"] == "ignore"
    assert spec["params"][0]["bind"]["input"] == "select"
    assert spec["transform"][0] == {"calculate": "datum[selected_kpi]", "as": "Wert"}
    metrics = spec["params"][0]["bind"]["options"]
    assert len(metrics) == (6 if pairs else 28)
    assert all(all(metric in row for metric in metrics) for row in rows)
    if pairs:
        winners = next(row for row in rows if row["Paar"] == "Anna & Berta")
        assert winners["Bilanz"] == count
        assert winners["Punkte pro Spiel"] == 3
    else:
        assert rows[0]["Punkte insgesamt"] == 3 * count
        assert rows[0]["Spiele gewonnen"] == count
        assert rows[0]["Re gewonnen %"] == 100
        assert rows[2]["Punkte insgesamt"] == -3 * count
        assert rows[2]["Spiele gewonnen"] == 0
    # Validate the actual spec, including bound variables and dynamic values.
    alt.Chart.from_dict({**spec, "data": {"values": rows}})
