"""Shared, cached test data.

Loading and joining the raw files is by far the slowest step of the test suite
(the real enrcols file is ~1 GB), so the analysis frame is built once per test
session and every test gets its own copy.

The data directory follows ``src.load_data.DATA_DIR``: the real (confidential)
files in ``data/``, or the synthetic data set when ``CASCO_DATA_DIR`` points to it
(see ``scripts/make_synthetic_data.py``).
"""

from functools import lru_cache

from src import load_data
from src import segments as sg
from src import features as ft


@lru_cache(maxsize=1)
def _cached_frame():
    return load_data.load_analysis_frame()


def analysis_frame():
    """The policy-level analysis frame (a fresh copy per call)."""
    return _cached_frame().copy()


def segmented_frame():
    """Analysis frame with the four rating dimensions and the composite segment key."""
    return sg.build_segment_key(sg.add_segments(analysis_frame()))


def time_split(segmented: bool = False):
    """(train, test) modelling frames, optionally carrying the segment columns."""
    frame = segmented_frame() if segmented else analysis_frame()
    return ft.make_time_split(ft.build_features(frame))
