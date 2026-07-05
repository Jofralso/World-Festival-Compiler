import unittest

from core.ai_stages import build_image_search_queries, search_image_references


class FestivalImageSearchTests(unittest.TestCase):
    def test_build_image_search_queries_uses_festival_name(self):
        queries = build_image_search_queries("Tomorrowland")
        self.assertTrue(any("Tomorrowland" in q for q in queries))
        self.assertGreaterEqual(len(queries), 3)

    def test_search_image_references_extracts_metadata_for_orientation(self):
        html = """
        <html><body>
          <a class="result__a" href="https://example.com/festival-stage">Tomorrowland main stage</a>
          <a class="result__snippet">A large stage with crowds facing the central platform at sunset.</a>
          <img src="https://cdn.example.com/festival-stage.jpg" alt="festival stage" />
        </body></html>
        """

        refs = search_image_references("Tomorrowland", html=html, limit=3)

        self.assertGreaterEqual(len(refs), 1)
        self.assertEqual(refs[0]["title"], "Tomorrowland main stage")
        self.assertEqual(refs[0]["image_url"], "https://cdn.example.com/festival-stage.jpg")
        self.assertIn(refs[0]["orientation_hint"], {"front-facing", "crowd-facing"})
        self.assertIn("stage", refs[0]["scene_hint"])


if __name__ == "__main__":
    unittest.main()
