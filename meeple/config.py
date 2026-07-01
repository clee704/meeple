"""Global seed control, so runs are reproducible from a single seed."""

import random

import numpy as np


def set_seed(seed: int) -> None:
    """Seed every RNG source the platform uses, for reproducible runs."""
    random.seed(seed)
    np.random.seed(seed)
