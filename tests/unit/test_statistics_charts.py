from unittest.mock import patch

import altair as alt
import pytest

from doppelkopf_app.domain.scoring import DeclaringParty
from doppelkopf_app.domain.statistics import StatisticalRound, calculate_statistics
from doppelkopf_app.ui.statistics_charts import render_point_distribution, render_statistics_bars


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
    assert spec["transform"] == [
        {"calculate": "datum[point_distribution]", "as": "Häufigkeit"},
        {"calculate": "point_distribution", "as": "Auswahl"},
    ]
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
    assert spec["layer"][0]["encoding"]["x"]["scale"]["domain"] == [4]
    assert spec["layer"][1]["transform"][-1] == {"filter": "datum.Anzahl === 0"}
    assert "keine Spiele" in spec["layer"][1]["encoding"]["text"]["value"]


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
    rows, _spec = chart.call_args.args
    assert rows == [{"Punktewert": 4, "Gesamt": count, "Re (Normalspiel)": count,
                     "Kontra (Normalspiel)": 0, "Solo Re": 0}]


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
