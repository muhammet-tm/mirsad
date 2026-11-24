"""Mirsad: finds fraudulent links and websites in search results, map listings, and new certificates.

Each link is scored by a four-ensemble URL classifier after the DaE2 design (see
docs/TECHNICAL_REPORT.md), then by evidence rules that can only raise the risk.
"""

__version__ = "0.1.0"
