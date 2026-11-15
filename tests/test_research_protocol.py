"""Research evaluation must not select models on the held-out test pool."""
import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dlgn.data import validation_indices


def test_validation_partition_is_disjoint_complete_and_reproducible():
    labels = np.repeat(np.arange(10), 20)
    train, val = validation_indices(200, labels, seed=7)
    train2, val2 = validation_indices(200, labels, seed=7)
    assert not set(train) & set(val)
    assert set(train) | set(val) == set(range(200))
    assert np.array_equal(train, train2) and np.array_equal(val, val2)
    assert len(val) == 40
    assert np.array_equal(np.bincount(labels[val]), np.full(10, 4))


@pytest.mark.parametrize("fraction", [0, 1, -0.1])
def test_invalid_validation_fraction(fraction):
    with pytest.raises(ValueError):
        validation_indices(20, np.repeat([0,1],10), fraction=fraction)
