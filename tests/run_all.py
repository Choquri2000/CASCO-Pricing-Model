"""Run every test module in this package (standalone, without pytest).

Usage:  ``python -m tests.run_all``

It imports each ``test_*.py`` and runs its ``test_*`` functions through the shared
harness, then prints a summary and exits non-zero if anything failed.
Under pytest you do not need this file (``pytest tests/`` finds the same tests).

Why a runner?  It gives a one-shot "does my whole pipeline still
pass?" check that works in any environment with only Python + the project
dependencies.
"""

import sys

import tests.test_load_data as t_load
import tests.test_segments as t_seg
import tests.test_metrics as t_met
import tests.test_recommend as t_rec
import tests.test_features as t_feat
import tests.test_frequency as t_freq
import tests.test_severity as t_sev
import tests.test_pure_premium as t_pp
import tests.test_credibility as t_cred
import tests.test_pricing as t_price
import tests.test_validation as t_val

from tests import _harness


MODULES = [
    t_load, t_seg, t_met, t_rec,
    t_feat, t_freq, t_sev, t_pp, t_cred, t_price, t_val,
]


def main() -> int:
    total_fail = 0
    for mod in MODULES:
        total_fail += _harness.run_module(mod)
    print(f"\n==== TOTAL: {total_fail} failure(s) across {len(MODULES)} modules ====")
    return total_fail


if __name__ == "__main__":
    sys.exit(main())
