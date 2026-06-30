import random

import numpy as np

from meeple.config import set_seed


def test_set_seed_makes_random_and_numpy_reproducible():
    set_seed(7)
    a = (random.random(), np.random.rand())
    set_seed(7)
    b = (random.random(), np.random.rand())
    assert a == b
