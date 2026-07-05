import unittest

from core.layout import LayoutPlanner


class LayoutRealismTests(unittest.TestCase):
    def test_realistic_layout_places_stages_with_spacing_and_camping_away_from_core(self):
        planner = LayoutPlanner()
        flat_zones = [
            (80, 80, 200, 200),
            (30, 30, 80, 90),
            (320, 60, 90, 80),
            (330, 300, 100, 90),
            (20, 280, 120, 110),
        ]

        plan = planner.plan(flat_zones, terrain_type="flat", map_size=(512, 512), style="electronic festival")

        self.assertGreater(plan.main_stage.x, 100)
        self.assertLess(plan.main_stage.x, 400)
        self.assertGreater(plan.main_stage.z, 100)
        self.assertLess(plan.main_stage.z, 400)

        for stage in plan.secondary_stages:
            dx = abs(stage.x - plan.main_stage.x)
            dz = abs(stage.z - plan.main_stage.z)
            min_distance = plan.main_stage.radius + 60
            self.assertGreaterEqual(dx * dx + dz * dz, min_distance * min_distance)

        for camping_zone in plan.camping:
            dx = abs(camping_zone.x - plan.main_stage.x)
            dz = abs(camping_zone.z - plan.main_stage.z)
            self.assertGreaterEqual(dx * dx + dz * dz, (plan.main_stage.radius + 100) ** 2)

        self.assertGreaterEqual(len(plan.paths), 4)

    def test_reference_context_adjusts_layout_for_crowd_facing_stage(self):
        planner = LayoutPlanner()
        plan = planner.plan(
            flat_zones=[(120, 120, 180, 180)],
            terrain_type="flat",
            map_size=(512, 512),
            style="electronic festival",
        )

        adjusted = planner.apply_reference_context(
            plan,
            {"orientation_hint": "crowd-facing", "scene_hint": "crowd scene"},
            (512, 512),
        )

        self.assertNotEqual(adjusted.main_stage.x, plan.main_stage.x)
        self.assertNotEqual(adjusted.entrance, plan.entrance)
        self.assertNotEqual(adjusted.spawn, plan.spawn)


if __name__ == "__main__":
    unittest.main()
