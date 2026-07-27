

def test_cards_missing_from_walkforward(tmp_path, monkeypatch):
    import json as _json
    from scripts.live import refresh_dashboard as rd

    root = tmp_path
    (root / "data" / "processed").mkdir(parents=True)
    (root / "model_outputs").mkdir(parents=True)
    (root / "data" / "processed" / "kalshi_results_labels.csv").write_text(
        "event_date,ticker,outcome\n2026-07-18,A,yes\n2026-07-25,B,no\n", encoding="utf-8"
    )
    (root / "model_outputs" / "walkforward_report.json").write_text(
        _json.dumps({"cards": ["2026-07-18"]}), encoding="utf-8"
    )
    monkeypatch.setattr(rd, "ROOT", root)
    assert rd.cards_missing_from_walkforward() == ["2026-07-25"]


def test_walkforward_up_to_date_does_not_retrain(tmp_path, monkeypatch):
    import json as _json
    from scripts.live import refresh_dashboard as rd

    root = tmp_path
    (root / "data" / "processed").mkdir(parents=True)
    (root / "model_outputs").mkdir(parents=True)
    (root / "data" / "processed" / "kalshi_results_labels.csv").write_text(
        "event_date,ticker,outcome\n2026-07-25,B,no\n", encoding="utf-8"
    )
    (root / "model_outputs" / "walkforward_report.json").write_text(
        _json.dumps({"cards": ["2026-07-25"]}), encoding="utf-8"
    )
    monkeypatch.setattr(rd, "ROOT", root)
    monkeypatch.setattr(rd, "WALKFORWARD_MARKER", root / "model_outputs" / ".wf")
    assert rd.maybe_retrain_walkforward() == "walk-forward up to date"
