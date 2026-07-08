"""Shape test for the relationship-graph service (runs on mock data).

    cd backend && .venv/Scripts/python -m pytest tests/test_graph.py -q
"""
import os

os.environ["DATA_MODE"] = "mock"
os.environ["ADVISOR_ENABLED"] = "0"

from app.services import graph  # noqa: E402


def test_build_graph_shape():
    g = graph.build_graph()
    for key in ("nodes", "edges", "avg_corr", "pairs", "source"):
        assert key in g
    assert isinstance(g["nodes"], list) and isinstance(g["edges"], list)
    for n in g["nodes"]:
        assert {"symbol", "theme", "weight"} <= set(n)
        assert 0 <= n["weight"] <= 1.0001
    for e in g["edges"]:
        assert {"a", "b", "corr"} <= set(e)
        assert -1.0001 <= e["corr"] <= 1.0001


def test_cash_excluded_from_graph():
    # SGOV / cash-like instruments must not be nodes (they break correlation)
    g = graph.build_graph()
    assert all(n["symbol"] != "SGOV" for n in g["nodes"])
