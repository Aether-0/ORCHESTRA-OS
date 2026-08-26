"""Display-only instrumentation for the original H3 script.

This module changes pandas console display options only. It does not alter data,
statistics, estimators, hypotheses, or source files in the pinned upstream checkout.
"""
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 2000)
pd.set_option("display.max_colwidth", None)
pd.set_option("display.expand_frame_repr", False)
