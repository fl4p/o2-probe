from __future__ import annotations

from pathlib import Path

import pytest

from o2_lumped.config import load_config


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def example_config():
    return load_config(ROOT / "config" / "uncalibrated_example.json")
