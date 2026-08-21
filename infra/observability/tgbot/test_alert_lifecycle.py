import json
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TG_CHAT_ID", "0")

import bot


def alert(fingerprint, status="firing", resource="nuxt_js"):
    return {
        "fingerprint": fingerprint,
        "status": status,
        "startsAt": "2026-08-21T10:00:00Z",
        "labels": {
            "alertname": "Rusaifin: incomplete asset",
            "severity": "warning",
            "server": "fintech.rusaifin.ru",
            "protocol": "HTTP/2.0",
            "resource_class": resource,
        },
        "annotations": {"summary": "transport signal"},
    }


class AlertLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_path = os.path.join(self.tmp.name, "state.json")
        self.path_patch = mock.patch.object(bot, "STATE_PATH", self.state_path)
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.tmp.cleanup()

    def test_grouped_instances_emit_once_and_resolve_after_all_clear(self):
        js = alert("js")
        other = alert("other", resource="nuxt_other")

        self.assertTrue(bot._begin_firing(js))
        self.assertTrue(bot._mark_alert_notified(js))
        self.assertFalse(bot._begin_firing(other))
        self.assertFalse(bot._finish_alert({**js, "status": "resolved"}))
        self.assertTrue(bot._alert_still_active(other))
        self.assertTrue(bot._finish_alert({**other, "status": "resolved"}))

    def test_alert_resolved_during_triage_is_not_posted(self):
        item = alert("short-flap")
        self.assertTrue(bot._begin_firing(item))
        self.assertFalse(bot._finish_alert({**item, "status": "resolved"}))
        self.assertFalse(bot._alert_still_active(item))
        self.assertFalse(bot._mark_alert_notified(item))

    def test_warning_repeat_is_suppressed_until_interval(self):
        item = alert("persistent")
        with mock.patch.object(bot.time, "time", return_value=1_000_000):
            self.assertTrue(bot._begin_firing(item))
        with mock.patch.object(bot.time, "time", return_value=1_000_001):
            self.assertFalse(bot._begin_firing(item))
        with mock.patch.object(
            bot.time, "time", return_value=1_000_000 + bot.ALERT_REPEAT_WARNING_SEC
        ):
            self.assertTrue(bot._begin_firing(item))

    def test_state_contains_no_alert_payload_or_secret_fields(self):
        item = alert("safe")
        item["labels"]["api_token"] = "must-not-be-persisted"
        bot._begin_firing(item)
        with open(self.state_path) as fh:
            state = json.load(fh)
        serialized = json.dumps(state)
        self.assertNotIn("must-not-be-persisted", serialized)

    def test_representative_instance_uses_largest_evaluator_value(self):
        low = alert("low")
        high = alert("high", resource="nuxt_other")
        low["valueString"] = "[ var='A' value=6 ], [ var='C' value=1 ]"
        high["valueString"] = "[ var='A' value=39 ], [ var='C' value=1 ]"
        items = sorted([low, high], key=bot._alert_numeric_value, reverse=True)
        self.assertEqual(items[0]["fingerprint"], "high")


if __name__ == "__main__":
    unittest.main()
