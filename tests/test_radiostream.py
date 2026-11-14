import unittest
from urllib.parse import parse_qs, urlsplit

import radiostream_core as rs


class RadioStreamTests(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(rs.DEFAULT_CONFIG)
        self.cfg.update({
            "center_lat": 10.0,
            "center_lon": 20.0,
            "radius_km": 100,
            "frequency_khz": 4625.0,
            "mode": "usb",
            "zoom": 9,
        })

    def sample(self, **overrides):
        item = {
            "id": "test-1",
            "url": "http://kiwi.example.test:8073",
            "name": "Test receiver",
            "loc": "Test location",
            "gps": [10.1, 20.1],
            "bands": [100000, 30000000],
            "users": 1,
            "users_max": 8,
            "snr": [25, 30],
            "offline": False,
            "flagged": False,
        }
        item.update(overrides)
        return item

    def test_haversine_zero_and_known_distance(self):
        self.assertAlmostEqual(rs.haversine_km(10, 20, 10, 20), 0, places=6)
        self.assertGreater(rs.haversine_km(10, 20, 10.1, 20.1), 10)
        self.assertLess(rs.haversine_km(10, 20, 10.1, 20.1), 20)

    def test_parses_receiver_inside_range(self):
        found = rs.parse_receiver(self.sample(), self.cfg)
        self.assertIsNotNone(found)
        self.assertTrue(found["available"])
        self.assertEqual(found["id"], "test-1")
        self.assertEqual(found["snr_hf"], 30.0)

    def test_excludes_receiver_outside_radius(self):
        found = rs.parse_receiver(self.sample(gps=[15, 25]), self.cfg)
        self.assertIsNone(found)

    def test_excludes_missing_gps_and_null_island(self):
        self.assertIsNone(rs.parse_receiver(self.sample(gps=None), self.cfg))
        self.assertIsNone(rs.parse_receiver(self.sample(gps=[0, 0]), self.cfg))

    def test_marks_offline_flagged_and_full_receivers_unavailable(self):
        self.assertFalse(rs.parse_receiver(self.sample(offline=True), self.cfg)["available"])
        self.assertFalse(rs.parse_receiver(self.sample(flagged=True), self.cfg)["available"])
        self.assertFalse(rs.parse_receiver(self.sample(users=8), self.cfg)["available"])

    def test_frequency_band_filter(self):
        self.assertFalse(rs.parse_receiver(self.sample(bands=[100000, 4000000]), self.cfg)["band_ok"])
        self.assertTrue(rs.parse_receiver(self.sample(bands=[100000, 30000000]), self.cfg)["band_ok"])

    def test_tune_url_applies_global_frequency_mode_zoom_and_controls(self):
        parsed = urlsplit(rs.make_tune_url({"url": "http://kiwi.example.test:8073"}, self.cfg))
        params = parse_qs(parsed.query, keep_blank_values=True)
        self.assertEqual(params["f"], ["4625usbz9"])
        self.assertEqual(params["pb"], ["50,4000"])
        self.assertEqual(params["vol"], ["180"])
        self.assertEqual(params["ext"], [""])
        self.assertNotIn("user", params)

    def test_config_validation_rejects_bad_zoom_and_mode(self):
        with self.assertRaises(ValueError):
            rs.validate_config({"zoom": 99})
        with self.assertRaises(ValueError):
            rs.validate_config({"mode": "unsupported"})

    def test_detects_kiwisdr_proxy_offline_page(self):
        page = """
            <html><body>
            The Kiwi 22048.proxy.kiwisdr.com is not online.
            to check again.
            </body></html>
        """
        self.assertTrue(rs.is_offline_receiver_page(page))

    def test_detects_required_visitor_name_page(self):
        page = """
            <html><body>
            Enter your name or callsign <br> to start KiwiSDR
            </body></html>
        """
        self.assertTrue(rs.is_offline_receiver_page(page))

    def test_does_not_mark_normal_kiwisdr_page_offline(self):
        page = "<html><title>KiwiSDR</title><body>Welcome to the receiver</body></html>"
        self.assertFalse(rs.is_offline_receiver_page(page))

    def test_detects_visible_enter_password_prompt(self):
        page = """
            <html><body>
              <div>Enter <strong>Password</strong>:</div>
            </body></html>
        """
        self.assertTrue(rs.is_password_prompt_page(page))

    def test_password_prompt_detection_is_case_insensitive(self):
        self.assertTrue(rs.is_password_prompt_page("<p>ENTER PASSWORD:</p>"))

    def test_ignores_password_text_inside_scripts_and_comments(self):
        page = """
            <!-- Enter Password: is only an example -->
            <script>const label = "Enter Password:";</script>
            <html><body>Welcome to the receiver</body></html>
        """
        self.assertFalse(rs.is_password_prompt_page(page))

    def test_does_not_reject_openwebrx_page_without_password_prompt(self):
        page = """
            <!DOCTYPE HTML>
            <!-- OpenWebRX (c) Copyright 2013-2014 Andras Retzler -->
            <!-- This file is part of OpenWebRX. -->
            <html><head><script src="kiwisdr.min.js"></script></head>
            <body>Welcome to the receiver</body></html>
        """
        self.assertFalse(rs.is_password_prompt_page(page))

    def test_directory_schema_validation(self):
        good = {"schema": 1, "receivers": [self.sample()]}
        self.assertEqual(len(rs.validate_directory(good)), 1)
        with self.assertRaises(ValueError):
            rs.validate_directory({"schema": 2, "receivers": []})
        with self.assertRaises(ValueError):
            rs.validate_directory({"schema": 1, "receivers": "not a list"})


if __name__ == "__main__":
    unittest.main()
