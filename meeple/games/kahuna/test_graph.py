from meeple.games.kahuna.graph import (
    BRIDGES,
    DEGREE,
    ISLANDS,
    MAJORITY,
    NUM_BRIDGES,
    other_endpoint,
)


def test_bridge_and_island_counts_match_rules_md():
    assert NUM_BRIDGES == 27
    assert len(ISLANDS) == 12
    assert sum(DEGREE.values()) == 2 * NUM_BRIDGES


def test_degree_and_majority_match_rules_md_table():
    expected = {
        "ALOA": (3, 2),
        "BARI": (5, 3),
        "COCO": (4, 3),
        "DUDA": (4, 3),
        "ELAI": (6, 4),
        "FAAA": (5, 3),
        "GOLA": (4, 3),
        "HUNA": (5, 3),
        "IFFI": (5, 3),
        "JOJO": (5, 3),
        "KAHU": (5, 3),
        "LALE": (3, 2),
    }
    for island, (degree, majority) in expected.items():
        assert DEGREE[island] == degree
        assert MAJORITY[island] == majority


def test_even_degree_island_majority_is_strictly_more_than_half():
    # RULES.md: a 4-line island needs 3, not 2 -- a tie isn't a majority.
    assert DEGREE["COCO"] == 4
    assert MAJORITY["COCO"] == 3


def test_other_endpoint():
    pos = BRIDGES.index(("ELAI", "HUNA"))
    assert other_endpoint(pos, "ELAI") == "HUNA"
    assert other_endpoint(pos, "HUNA") == "ELAI"


def test_bridges_are_alphabetically_ordered_pairs():
    for a, b in BRIDGES:
        assert a < b
