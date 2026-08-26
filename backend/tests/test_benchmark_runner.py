"""Tests verifying that the evaluation scenario framework is correct."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.scenarios import generate_scenarios, ScenarioCategory


def test_generator_yields_exactly_106_scenarios():
    scenarios = generate_scenarios()
    assert len(scenarios) == 106, f"Expected 106 scenarios, got {len(scenarios)}"


def test_all_categories_represented():
    scenarios = generate_scenarios()
    categories_present = {s.category for s in scenarios}
    for cat in ScenarioCategory:
        assert cat in categories_present, f"Missing category: {cat.value}"