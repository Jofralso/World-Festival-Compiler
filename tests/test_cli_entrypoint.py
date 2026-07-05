import importlib
import unittest


class CliEntrypointTests(unittest.TestCase):
    def test_cli_module_imports(self) -> None:
        module = importlib.import_module("cli")
        self.assertTrue(hasattr(module, "main"))


if __name__ == "__main__":
    unittest.main()
