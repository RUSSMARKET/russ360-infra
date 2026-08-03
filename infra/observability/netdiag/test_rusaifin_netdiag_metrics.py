import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("rusaifin_netdiag_metrics.py")
SPEC = importlib.util.spec_from_file_location("rusaifin_netdiag_metrics", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class MetricsTest(unittest.TestCase):
    def test_classifies_completed_and_incomplete_responses(self):
        records = [
            {
                "msec": 1_000,
                "server_name": "fintech.rusaifin.ru",
                "protocol": "HTTP/2.0",
                "request_completion": "OK",
                "status": 200,
                "uri": "/_nuxt/main.js",
                "content_type": "application/javascript",
            },
            {
                "msec": 1_001,
                "server_name": "fintech.rusaifin.ru",
                "protocol": "HTTP/2.0",
                "request_completion": "",
                "status": 200,
                "uri": "/_nuxt/main.js",
                "content_type": "application/javascript",
            },
            {
                "msec": 1_001,
                "server_name": "fintech.rusaifin.ru",
                "protocol": "HTTP/2.0",
                "request_completion": "",
                "status": 499,
                "uri": "/font.woff2",
                "content_type": "font/woff2",
            },
        ]
        output = MODULE.render_metrics(records, now=1_002, window_seconds=300, parse_errors=0)
        self.assertIn('completion="ok"} 1', output)
        self.assertIn('completion="incomplete"} 2', output)
        self.assertIn('resource_class="nuxt_js"} 1', output)
        self.assertIn('rusaifin_netdiag_client_aborts_window', output)
        self.assertIn('resource_class="other"} 1', output)

    def test_ignores_unknown_vhosts_and_old_records(self):
        records = [
            {"msec": 100, "server_name": "example.com", "request_completion": "", "status": 200},
            {
                "msec": 100,
                "server_name": "fintech.rusaifin.ru",
                "request_completion": "",
                "status": 200,
            },
        ]
        output = MODULE.render_metrics(records, now=1_000, window_seconds=300, parse_errors=0)
        self.assertNotIn("rusaifin_netdiag_requests_window{", output)

    def test_counts_only_fixed_successful_bootstrap_events(self):
        base = {
            "msec": 1_000,
            "server_name": "fintech.rusaifin.ru",
            "protocol": "HTTP/2.0",
            "request_completion": "OK",
            "method": "POST",
            "status": 204,
            "uri": "/__netdiag/bootstrap/resource-error",
            "user_agent": "Mozilla/5.0 (iPhone) AppleWebKit/605.1.15",
        }
        records = [
            base,
            {**base, "uri": "/__netdiag/bootstrap/timeout"},
            {**base, "uri": "/__netdiag/bootstrap/arbitrary"},
            {**base, "method": "GET"},
            {**base, "user_agent": "curl/8.0"},
        ]
        output = MODULE.render_metrics(records, now=1_001, window_seconds=300, parse_errors=0)
        self.assertIn('event="resource-error"} 1', output)
        self.assertIn('event="timeout"} 1', output)
        self.assertNotIn('event="arbitrary"', output)


if __name__ == "__main__":
    unittest.main()
