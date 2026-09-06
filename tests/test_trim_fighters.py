from ufc_mentions import build_dashboard_data as bdd


def test_only_fighters_on_a_recorded_night_survive():
    fighters = {"a one": {"name": "A One"}, "b two": {"name": "B Two"}, "c three": {"name": "C Three"}}
    tapes = [{"markets": [{"fighter_1": "A One", "fighter_2": ""}]}]
    trades = [{"fighter_1": "", "fighter_2": "B Two"}]
    out = bdd.trim_fighters(fighters, tapes, trades)
    assert sorted(out) == ["a one", "b two"]


def test_nothing_recorded_keeps_everything():
    fighters = {"a one": {}, "b two": {}}
    assert bdd.trim_fighters(fighters, [], []) == fighters
