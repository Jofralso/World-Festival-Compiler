import unittest
from pathlib import Path

from core.terrain_intelligence import TerrainIntelligence


class TerrainIntelligenceTests(unittest.TestCase):
    def test_build_context_profile_uses_local_and_online_resources(self):
        intel = TerrainIntelligence(cache_dir=Path('/tmp/fw_intel_test'))
        sample = Path('/tmp/fw_intel_sample.png')
        sample.write_bytes(b'\x89PNG\r\n\x1a\n')
        profile = intel.build_context_profile('Tomorrowland', local_inputs=[sample])
        self.assertIn('query', profile)
        self.assertIn('terrain_summary', profile)
        self.assertTrue(isinstance(profile['online_resources'], list))


if __name__ == '__main__':
    unittest.main()
