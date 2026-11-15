import tempfile
import unittest
from unittest.mock import patch
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

    def test_frequency_config_accepts_hz_through_ghz_range(self):
        low = rs.validate_config({"frequency_khz": 0.001})
        high = rs.validate_config({"frequency_khz": 300000000})
        self.assertEqual(low["frequency_khz"], 0.001)
        self.assertEqual(high["frequency_khz"], 300000000)
        with self.assertRaises(ValueError):
            rs.validate_config({"frequency_khz": 0.0009})
        with self.assertRaises(ValueError):
            rs.validate_config({"frequency_khz": 300000001})

    def test_overlay_message_defaults_match_current_artwork(self):
        self.assertIn("Every ${M} minutes", rs.DEFAULT_CONFIG["overlay_reload_notice"])
        self.assertIn("the waterfall", rs.DEFAULT_CONFIG["overlay_reload_notice"])
        self.assertIn("something crashed", rs.DEFAULT_CONFIG["overlay_black_notice"])
        self.assertIn("the next reload", rs.DEFAULT_CONFIG["overlay_black_notice"])

    def test_config_validation_preserves_rotation_placeholder(self):
        text = "Every ${M} minutes, reload receiver"
        validated = rs.validate_config({"overlay_reload_notice": text})
        self.assertEqual(validated["overlay_reload_notice"], text)
        self.assertEqual(validated["rotation_minutes"], rs.DEFAULT_CONFIG["rotation_minutes"])

    def test_config_validation_preserves_custom_multiline_overlay_text(self):
        reload_text = "Line one\nLine two"
        black_text = "Warning\nNext line"
        validated = rs.validate_config({
            "overlay_reload_notice": reload_text,
            "overlay_black_notice": black_text,
        })
        self.assertEqual(validated["overlay_reload_notice"], reload_text)
        self.assertEqual(validated["overlay_black_notice"], black_text)

    def test_config_validation_rejects_invalid_overlay_text(self):
        with self.assertRaises(ValueError):
            rs.validate_config({"overlay_reload_notice": 123})
        with self.assertRaises(ValueError):
            rs.validate_config({"overlay_black_notice": "x" * 801})
        with self.assertRaises(ValueError):
            rs.validate_config({"overlay_black_notice": "\n".join(["line"] * 9)})

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

    def test_parses_receiverbook_openwebrx_map_data(self):
        body = """
            <script>
                $(function() {
                    var receivers = [
                        {
                            "label": "Station group",
                            "location": {"type": "Point", "coordinates": [20.1, 10.1]},
                            "receivers": [
                                {
                                    "label": "OpenWebRX receiver",
                                    "version": "1.2.130",
                                    "url": "https://sdr.example.test/",
                                    "type": "openwebrx"
                                },
                                {
                                    "label": "Kiwi receiver",
                                    "url": "https://kiwi.example.test/",
                                    "type": "kiwisdr"
                                }
                            ]
                        }
                    ];
                    $('.map-container').addReceivers(receivers);
                });
            </script>
        """
        receivers = rs.parse_receiverbook_map(body)
        self.assertEqual(len(receivers), 1)
        self.assertEqual(receivers[0]["name"], "OpenWebRX receiver")
        self.assertEqual(receivers[0]["station"], "Station group")
        self.assertEqual(receivers[0]["lat"], 10.1)
        self.assertEqual(receivers[0]["lon"], 20.1)
        self.assertEqual(receivers[0]["type"], "openwebrx")

    def test_parses_openwebrx_plus_profile_frequency_ranges(self):
        payload = {
            "sdrs": [{
                "profiles": [
                    {"center_freq": 100000000, "sample_rate": 2000000},
                    {"center_freq": 462500000, "sample_rate": 8000000},
                ]
            }]
        }
        ranges = rs.parse_openwebrx_plus_frequency_ranges(payload)
        self.assertEqual(ranges, [
            {"low_hz": 99000000.0, "high_hz": 101000000.0},
            {"low_hz": 458500000.0, "high_hz": 466500000.0},
        ])

    def test_parses_classic_openwebrx_bands(self):
        ranges = rs.parse_openwebrx_classic_frequency_ranges(
            "name=Example\nversion=0.19.1\nbands=3000000-30000000\n"
        )
        self.assertEqual(ranges, [{"low_hz": 3000000.0, "high_hz": 30000000.0}])
        self.assertEqual(rs.parse_openwebrx_classic_frequency_ranges("name=Example\n"), [])

    def test_receiverbook_rejects_local_urls(self):
        self.assertIsNone(rs.normalize_receiverbook_url("http://127.0.0.1:8073/"))
        self.assertIsNone(rs.normalize_receiverbook_url("http://localhost:8073/"))
        self.assertIsNone(rs.normalize_receiverbook_url("ftp://sdr.example.test/"))
        self.assertEqual(
            rs.normalize_receiverbook_url("https://sdr.example.test/radio/"),
            "https://sdr.example.test/radio/",
        )

    def test_openwebrx_tuning_url_uses_hz_and_supported_mode_names(self):
        receiver = {"url": "https://sdr.example.test/radio/"}
        url = rs.make_openwebrx_url(receiver, self.cfg)
        parsed = urlsplit(url)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "sdr.example.test")
        self.assertEqual(parsed.path, "/radio/")
        self.assertEqual(parsed.fragment, "freq=4625000,mod=usb")

        fm_cfg = dict(self.cfg, mode="nbfm")
        fm_url = rs.make_openwebrx_url(receiver, fm_cfg)
        self.assertEqual(urlsplit(fm_url).fragment, "freq=4625000,mod=nfm")

    def test_discover_openwebrx_uses_saved_search_radius(self):
        previous = (
            rs.receiverbook_data,
            rs.receiverbook_fetched_monotonic,
            rs.receiverbook_fetched_at,
            rs.receiverbook_error,
            rs.config,
        )
        self.addCleanup(
            lambda: (
                setattr(rs, "receiverbook_data", previous[0]),
                setattr(rs, "receiverbook_fetched_monotonic", previous[1]),
                setattr(rs, "receiverbook_fetched_at", previous[2]),
                setattr(rs, "receiverbook_error", previous[3]),
                setattr(rs, "config", previous[4]),
            )
        )
        rs.config = dict(self.cfg)
        checked_at = rs.time.time()
        rs.receiverbook_data = [
            {
                "id": "receiverbook:https://sdr.example.test/",
                "name": "Nearby OpenWebRX",
                "station": "Test station",
                "version": "1.2.130",
                "type": "openwebrx",
                "url": "https://sdr.example.test/",
                "lat": 10.1,
                "lon": 20.1,
                "frequency_ranges": [{"low_hz": 4000000, "high_hz": 5000000}],
                "frequency_checked_at": checked_at,
            },
            {
                "id": "receiverbook:https://other-sdr.example.test/",
                "name": "Out-of-band OpenWebRX",
                "station": "Other station",
                "version": "1.2.130",
                "type": "openwebrx",
                "url": "https://other-sdr.example.test/",
                "lat": 10.2,
                "lon": 20.2,
                "frequency_ranges": [{"low_hz": 100000000, "high_hz": 110000000}],
                "frequency_checked_at": checked_at,
            },
        ]
        rs.receiverbook_fetched_monotonic = rs.time.monotonic()
        rs.receiverbook_fetched_at = "2026-11-14T00:00:00Z"
        rs.receiverbook_error = None
        with patch.object(rs, "save_receiverbook_cache"):
            found, meta = rs.discover_openwebrx()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["name"], "Nearby OpenWebRX")
        self.assertEqual(found[0]["source"], "Receiverbook")
        self.assertTrue(found[0]["listed_online"])
        self.assertEqual(urlsplit(found[0]["tune_url"]).fragment, "freq=4625000,mod=usb")
        self.assertEqual(meta["nearby_count"], 2)
        self.assertEqual(meta["found_count"], 1)

    def test_custom_openwebrx_instance_validation(self):
        instance = rs.normalize_custom_openwebrx_instance({
            "url": "https://sdr.example.test/radio/",
            "name": "My receiver",
            "lat": 10.1,
            "lon": 20.1,
        })
        self.assertEqual(instance["id"], "custom:https://sdr.example.test/radio/")
        self.assertEqual(instance["name"], "My receiver")
        self.assertEqual(instance["lat"], 10.1)
        with self.assertRaises(ValueError):
            rs.normalize_custom_openwebrx_instance({
                "url": "http://127.0.0.1:8073/",
                "lat": 10,
                "lon": 20,
            })
        with self.assertRaises(ValueError):
            rs.normalize_custom_openwebrx_instance({
                "url": "https://sdr.example.test/",
                "lat": 95,
                "lon": 20,
            })

    def test_custom_openwebrx_instances_persist_and_can_be_removed(self):
        previous_path = rs.OPENWEBRX_CUSTOM_PATH
        previous_data = rs.openwebrx_custom_data
        self.addCleanup(lambda: (
            setattr(rs, "OPENWEBRX_CUSTOM_PATH", previous_path),
            setattr(rs, "openwebrx_custom_data", previous_data),
        ))
        with tempfile.TemporaryDirectory() as directory:
            rs.OPENWEBRX_CUSTOM_PATH = rs.Path(directory) / "openwebrx_custom.json"
            rs.openwebrx_custom_data = []
            instance = {
                "url": "https://sdr.example.test/",
                "name": "Favorite receiver",
                "lat": 10.1,
                "lon": 20.1,
            }
            added = rs.add_custom_openwebrx_instance(instance)
            self.assertEqual(len(added), 1)
            rs.openwebrx_custom_data = []
            rs.load_custom_openwebrx_instances()
            self.assertEqual(rs.openwebrx_custom_data[0]["name"], "Favorite receiver")
            removed = rs.remove_custom_openwebrx_instance(added[0]["id"])
            self.assertEqual(removed, [])

    def test_custom_openwebrx_discovery_works_without_receiverbook(self):
        previous_config = rs.config
        self.addCleanup(lambda: setattr(rs, "config", previous_config))
        rs.config = dict(self.cfg)
        rs.config["openwebrx_receiverbook_enabled"] = False
        instance = {
            "id": "custom:https://sdr.example.test/",
            "name": "My receiver",
            "station": "",
            "version": "1.2.130",
            "type": "openwebrx",
            "url": "https://sdr.example.test/",
            "lat": 10.1,
            "lon": 20.1,
            "frequency_ranges": [{"low_hz": 4000000, "high_hz": 5000000}],
            "frequency_checked_at": rs.time.time(),
        }
        with (
            patch.object(rs, "fetch_receiverbook_directory") as fetch_receiverbook,
            patch.object(rs, "get_custom_openwebrx_instances", return_value=[instance]),
            patch.object(rs, "save_custom_openwebrx_frequency_cache"),
        ):
            found, meta = rs.discover_openwebrx()
        fetch_receiverbook.assert_not_called()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["source"], "Custom")
        self.assertFalse(found[0]["listed_online"])
        self.assertFalse(meta["receiverbook_enabled"])
        self.assertEqual(meta["custom_count"], 1)

    def test_receiverbook_source_setting_requires_boolean(self):
        with self.assertRaises(ValueError):
            rs.validate_config({"openwebrx_receiverbook_enabled": "false"})

    def test_directory_schema_validation(self):
        good = {"schema": 1, "receivers": [self.sample()]}
        self.assertEqual(len(rs.validate_directory(good)), 1)
        with self.assertRaises(ValueError):
            rs.validate_directory({"schema": 2, "receivers": []})
        with self.assertRaises(ValueError):
            rs.validate_directory({"schema": 1, "receivers": "not a list"})


if __name__ == "__main__":
    unittest.main()
