"""Backward-compatibility shim for lake_literature.

Allows existing scripts and imports targeting `lake_literature` to continue functioning
seamlessly by delegating to `lake_research_map`.
"""

import sys

import lake_research_map

# Map module into sys.modules
sys.modules["lake_literature"] = lake_research_map


def main() -> None:
    from lake_research_map.pipeline import main as pipeline_main

    pipeline_main()
