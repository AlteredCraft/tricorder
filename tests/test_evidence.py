import unittest

from tools.evidence import assess, parse_event


class EvidenceTests(unittest.TestCase):
    def event(self, seq, name, **fields):
        return {"boot_id": "boot-a", "seq": seq, "device_us": seq * 100,
                "event": name, **fields}

    def test_missing_checks_are_inconclusive(self):
        result = assess([self.event(0, "boot")], ["rtc_advance"])
        self.assertEqual(result["checks"]["rtc_advance"], "inconclusive")
        self.assertEqual(result["status"], "inconclusive")

    def test_success_requires_explicit_measured_check(self):
        events = [self.event(0, "boot"), self.event(1, "check", check="rtc_advance", result="pass")]
        self.assertEqual(assess(events, ["rtc_advance"])["status"], "pass")

    def test_gap_and_duplicate_sequences_fail_evidence_integrity(self):
        for sequence in (2, 0):
            events = [self.event(0, "boot"), self.event(sequence, "check", check="rtc_advance", result="pass")]
            self.assertEqual(assess(events, ["rtc_advance"])["status"], "fail")

    def test_reboot_cannot_borrow_previous_boots_pass(self):
        events = [self.event(0, "boot"), self.event(1, "check", check="rtc_advance", result="pass"),
                  {**self.event(0, "boot"), "boot_id": "boot-b"}]
        self.assertEqual(assess(events, ["rtc_advance"])["status"], "inconclusive")

    def test_later_success_does_not_erase_failure(self):
        events = [self.event(0, "boot"), self.event(1, "check", check="sd_roundtrip", result="fail"),
                  self.event(2, "check", check="sd_roundtrip", result="pass")]
        self.assertEqual(assess(events, ["sd_roundtrip"])["status"], "fail")

    def test_reversed_device_clock_is_failure(self):
        events = [self.event(0, "boot", device_us=1000), self.event(1, "ready", device_us=1)]
        self.assertEqual(assess(events, ["rtc_advance"])["status"], "fail")

    def test_malformed_instrumentation_is_not_silently_ignored(self):
        for line in ('TRICORDER {bad', 'TRICORDER {}', 'TRICORDER {"seq": false}'):
            with self.assertRaises(ValueError):
                parse_event(line)
        self.assertIsNone(parse_event("I (25) boot: ordinary IDF log"))

    def test_failure_in_either_boot_survives_aggregation(self):
        events = [self.event(0, "boot"), self.event(1, "check", check="rtc_advance", result="fail"),
                  {**self.event(0, "boot"), "boot_id": "boot-b"},
                  {**self.event(1, "check", check="rtc_advance", result="pass"), "boot_id": "boot-b"}]
        self.assertEqual(assess(events, ["rtc_advance"])["status"], "fail")


if __name__ == "__main__":
    unittest.main()
