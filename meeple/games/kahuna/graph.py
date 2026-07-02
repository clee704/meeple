"""Kahuna's board: 12 islands connected by 27 bridge lines, matching the
graph and bridge_pos numbering documented in RULES.md."""

BRIDGES: tuple[tuple[str, str], ...] = (
    ("ALOA", "BARI"),
    ("ALOA", "DUDA"),
    ("ALOA", "HUNA"),
    ("BARI", "COCO"),
    ("BARI", "DUDA"),
    ("BARI", "ELAI"),
    ("BARI", "FAAA"),
    ("COCO", "FAAA"),
    ("COCO", "GOLA"),
    ("COCO", "KAHU"),
    ("DUDA", "ELAI"),
    ("DUDA", "HUNA"),
    ("ELAI", "FAAA"),
    ("ELAI", "HUNA"),
    ("ELAI", "IFFI"),
    ("ELAI", "JOJO"),
    ("FAAA", "GOLA"),
    ("FAAA", "JOJO"),
    ("GOLA", "JOJO"),
    ("GOLA", "KAHU"),
    ("HUNA", "IFFI"),
    ("HUNA", "LALE"),
    ("IFFI", "JOJO"),
    ("IFFI", "KAHU"),
    ("IFFI", "LALE"),
    ("JOJO", "KAHU"),
    ("KAHU", "LALE"),
)
NUM_BRIDGES = len(BRIDGES)

ISLANDS: tuple[str, ...] = tuple(sorted({island for pair in BRIDGES for island in pair}))

# Bridge positions touching each island, e.g. ISLAND_BRIDGES["ALOA"] == (0, 1, 2).
ISLAND_BRIDGES: dict[str, tuple[int, ...]] = {
    island: tuple(pos for pos, pair in enumerate(BRIDGES) if island in pair) for island in ISLANDS
}

DEGREE: dict[str, int] = {island: len(positions) for island, positions in ISLAND_BRIDGES.items()}

# Strict majority: more than half of an island's lines (ties don't count).
MAJORITY: dict[str, int] = {island: degree // 2 + 1 for island, degree in DEGREE.items()}
