"""Regression checks for the 2025 consumption VAT rules."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

# Load the pure calculation without importing the Home Assistant integration.
path = Path(__file__).parents[1] / "custom_components/erse/sensor.py"
tree = ast.parse(path.read_text())
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "energy_cost")
namespace = {}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
vat = SimpleNamespace(energy_cost=namespace["energy_cost"])


class VatTests(unittest.TestCase):
    def test_allowance_and_power_boundary(self):
        for kwh in (0, 100, 200, 250):
            reduced = min(kwh, 200)
            expected = round(reduced * .2 * 1.06, 2) + round((kwh - reduced) * .2 * 1.23, 2) + kwh * .001 * 1.23
            self.assertAlmostEqual(vat.energy_cost(.2, kwh, kwh, 6.9), expected)
        self.assertAlmostEqual(vat.energy_cost(.2, 200, 200, 10.35), 49.446)

    def test_erse_multitariff_example(self):
        # 350 kWh: 72% outside off-peak and 28% off-peak.
        self.assertAlmostEqual(vat.energy_cost(.2, 252, 350, 6.9), 30.53 + 26.57 + .30996)
        self.assertAlmostEqual(vat.energy_cost(.1, 98, 350, 6.9), 5.94 + 5.17 + .12054)

    def test_allowance_scales_with_billing_days(self):
        self.assertAlmostEqual(vat.energy_cost(.2, 280, 280, 6.9, 42), 59.36 + .3444)
        self.assertAlmostEqual(vat.energy_cost(.2, 150, 150, 6.9, 15), 21.2 + 12.3 + .1845)

    def test_meters_share_one_allowance(self):
        self.assertAlmostEqual(
            2 * vat.energy_cost(.2, 200, 400, 6.9),
            vat.energy_cost(.2, 400, 400, 6.9),
        )
