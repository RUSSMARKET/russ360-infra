import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("rusaifin_iphone_capture.py")
SPEC = importlib.util.spec_from_file_location("rusaifin_iphone_capture", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class CaptureFilterTest(unittest.TestCase):
    def test_accepts_only_rusaifin_iphone_html_navigation(self):
        record = {
            "server_name": "fintech.rusaifin.ru",
            "method": "GET",
            "status": 200,
            "content_type": "text/html; charset=utf-8",
            "user_agent": "Mozilla/5.0 (iPhone) AppleWebKit/605.1.15",
            "remote_addr": "192.0.2.10",
        }
        self.assertTrue(MODULE.eligible_navigation(record))
        record["server_name"] = "another-site.example"
        self.assertFalse(MODULE.eligible_navigation(record))

    def test_rejects_non_html_and_non_apple_clients(self):
        record = {
            "server_name": "fintech.rusaifin.ru",
            "method": "GET",
            "status": 200,
            "content_type": "application/javascript",
            "user_agent": "Mozilla/5.0 (iPhone) AppleWebKit/605.1.15",
            "remote_addr": "192.0.2.10",
        }
        self.assertFalse(MODULE.eligible_navigation(record))
        record["content_type"] = "text/html"
        record["user_agent"] = "curl/8.0"
        self.assertFalse(MODULE.eligible_navigation(record))


if __name__ == "__main__":
    unittest.main()
