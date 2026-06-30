"""Global seed control (CLAUDE.md Phase 0 hygiene)."""

import random

import numpy as np


def set_seed(seed: int) -> None:
    """Seed every RNG source the platform uses, for reproducible runs."""
    random.seed(seed)
    np.random.seed(seed)
