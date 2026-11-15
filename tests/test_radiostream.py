import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import radiostream_core as rs
import radiostream_server as rss


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
        cfg = dict(self.cfg, passband_low=50, passband_high=4000)
        parsed = urlsplit(rs.make_tune_url({"url": "http://kiwi.example.test:8073"}, cfg))
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

    def test_frequency_list_is_preserved_and_first_frequency_starts_active(self):
        validated = rs.validate_config({
            "frequencies_khz": [2500, 5000, 10000],
            "frequency_khz": 2500,
        })
        self.assertEqual(validated["frequencies_khz"], [2500, 5000, 10000])
        self.assertEqual(validated["frequency_khz"], 2500)

        url = rs.make_tune_url(
            {"url": "http://kiwi.example.test:8073"},
            validated,
        )
        self.assertEqual(parse_qs(urlsplit(url).query)["f"], ["2500usbz11"])

    def test_frequency_validation_rejects_empty_duplicate_and_oversized_lists(self):
        with self.assertRaises(ValueError):
            rs.validate_config({"frequencies_khz": []})
        with self.assertRaises(ValueError):
            rs.validate_config({"frequencies_khz": [4625, 4625]})
        with self.assertRaises(ValueError):
            rs.validate_config({"frequencies_khz": [0]})
        with self.assertRaises(ValueError):
            rs.validate_config({
                "frequencies_khz": [
                    1000 + index for index in range(rs.MAX_FREQUENCIES + 1)
                ],
            })

    def test_legacy_named_frequency_links_migrate_to_numeric_frequencies(self):
        validated = rs.validate_config({
            "frequency_khz": 10000,
            "frequency_links": [
                {"name": "WWV 2.5 MHz", "frequency_khz": 2500},
                {"name": "WWV 5 MHz", "frequency_khz": 5000},
                {"name": "WWV 10 MHz", "frequency_khz": 10000},
            ],
            "active_frequency_index": 2,
        })
        self.assertEqual(validated["frequencies_khz"], [2500, 5000, 10000])
        self.assertEqual(validated["frequency_khz"], 10000)
        self.assertNotIn("frequency_links", validated)
        self.assertNotIn("active_frequency_index", validated)

    def test_legacy_single_frequency_setting_remains_supported(self):
        validated = rs.validate_config({"frequency_khz": 15000})
        self.assertEqual(validated["frequencies_khz"], [15000])
        self.assertEqual(validated["frequency_khz"], 15000)

    def test_frequency_shuffle_visits_each_frequency_before_repeating(self):
        frequencies = [2500.0, 5000.0, 10000.0, 15000.0]
        current = frequencies[0]
        remaining = frequencies[1:]
        visited = [current]

        for _ in range(len(frequencies) - 1):
            current, remaining = rss.take_next_frequency(
                frequencies,
                current,
                remaining,
            )
            self.assertIsNotNone(current)
            visited.append(current)

        self.assertEqual(set(visited), set(frequencies))
        self.assertEqual(len(visited), len(set(visited)))

        next_frequency, remaining = rss.take_next_frequency(
            frequencies,
            current,
            remaining,
        )
        self.assertNotEqual(next_frequency, current)
        self.assertIn(next_frequency, frequencies)

    def test_frequency_shuffle_handles_single_frequency(self):
        next_frequency, remaining = rss.take_next_frequency([4625.0], 4625.0, [])
        self.assertIsNone(next_frequency)
        self.assertEqual(remaining, [])

    def test_runtime_rotation_advances_the_active_frequency(self):
        previous_config = rs.config
        previous_shuffle = list(rss.frequency_shuffle_remaining)
        previous_receiver = rss.current_receiver
        previous_started_at = rss.current_started_at
        try:
            rs.config = dict(rs.DEFAULT_CONFIG)
            rs.config.update({
                "frequency_khz": 10000.0,
                "frequencies_khz": [2500.0, 5000.0, 10000.0],
            })
            rss.current_receiver = {
                "id": "rotation-test",
                "url": "http://kiwi.example.test:8073",
                "name": "Rotation test receiver",
            }
            rss.current_started_at = 100.0
            with patch.object(rss.random, "shuffle", side_effect=lambda values: None):
                rss.reset_frequency_shuffle()

            rotation_seconds = rs.config["rotation_minutes"] * 60
            with (
                patch.object(rs, "get_station_preference", return_value=""),
                patch.object(rs, "check_receiver_online", return_value=(True, "")),
                patch.object(rs, "make_tune_url", return_value="http://kiwi.example.test:8073/"),
                patch.object(rss, "pick_receiver_across_frequencies") as select_receiver,
                patch.object(rss.time, "monotonic", return_value=100.0 + rotation_seconds + 1),
            ):
                select_receiver.return_value = dict(rss.current_receiver)
                state = rss._get_state()

            self.assertEqual(rs.config["frequency_khz"], 2500.0)
            select_receiver.assert_called_once_with(force_next=True)
            self.assertEqual(state["config"]["frequencies_khz"], [2500.0, 5000.0, 10000.0])
        finally:
            rs.config = previous_config
            rss.frequency_shuffle_remaining = previous_shuffle
            rss.current_receiver = previous_receiver
            rss.current_started_at = previous_started_at

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
            rs.OPENWEBRX_CUSTOM_PATH = Path(directory) / "openwebrx_custom.json"
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
        with self.assertRaises(ValueError):
            rs.validate_config({"openwebrx_custom_enabled": "false"})

    def test_radio_preset_validation(self):
        preset = rs.normalize_radio_preset({
            "name": "WWV multi-band",
            "frequency_khz": 10000,
            "frequencies_khz": [2500, 5000, 10000],
            "mode": "am",
            "passband_low": -4900,
            "passband_high": 4900,
            "rotation_minutes": 12,
        })
        self.assertEqual(preset["name"], "WWV multi-band")
        self.assertEqual(preset["frequency_khz"], 10000)
        self.assertEqual(preset["frequencies_khz"], [2500, 5000, 10000])
        self.assertEqual(preset["center_lat"], rs.DEFAULT_CONFIG["center_lat"])
        self.assertEqual(preset["center_lon"], rs.DEFAULT_CONFIG["center_lon"])
        self.assertEqual(preset["radius_km"], rs.DEFAULT_CONFIG["radius_km"])
        self.assertEqual(preset["rotation_minutes"], 12)
        self.assertEqual(preset["mode"], "am")
        self.assertTrue(preset["id"].startswith("preset-"))

        legacy = rs.normalize_radio_preset({
            "name": "Legacy single frequency",
            "frequency_khz": 10000,
            "mode": "am",
            "passband_low": -4900,
            "passband_high": 4900,
        })
        self.assertEqual(legacy["frequencies_khz"], [10000])

        with self.assertRaises(ValueError):
            rs.normalize_radio_preset({
                "name": "Duplicate frequencies",
                "frequency_khz": 10000,
                "frequencies_khz": [10000, 10000],
                "mode": "am",
                "passband_low": -100,
                "passband_high": 100,
            })
        with self.assertRaises(ValueError):
            rs.normalize_radio_preset({
                "name": "Bad mode",
                "frequency_khz": 10000,
                "mode": "unsupported",
                "passband_low": -100,
                "passband_high": 100,
            })
        with self.assertRaises(ValueError):
            rs.normalize_radio_preset({
                "name": "Bad range",
                "frequency_khz": 0,
                "mode": "am",
                "passband_low": -100,
                "passband_high": 100,
            })

    def test_legacy_radio_presets_migrate_from_schema_one(self):
        previous_path = rs.RADIO_PRESETS_PATH
        previous_presets = rs.radio_presets
        self.addCleanup(lambda: (
            setattr(rs, "RADIO_PRESETS_PATH", previous_path),
            setattr(rs, "radio_presets", previous_presets),
        ))
        with tempfile.TemporaryDirectory() as directory:
            rs.RADIO_PRESETS_PATH = Path(directory) / "radio_presets.json"
            rs.RADIO_PRESETS_PATH.write_text(json.dumps({
                "schema": 1,
                "presets": [{
                    "id": "legacy-one",
                    "name": "Legacy preset",
                    "frequency_khz": 4625,
                    "mode": "usb",
                    "passband_low": 300,
                    "passband_high": 2700,
                }],
            }), encoding="utf-8")
            rs.load_radio_presets()
            loaded = rs.get_radio_presets()[0]
            self.assertEqual(loaded["frequencies_khz"], [4625])
            self.assertEqual(loaded["rotation_minutes"], rs.DEFAULT_CONFIG["rotation_minutes"])
            migrated = json.loads(rs.RADIO_PRESETS_PATH.read_text(encoding="utf-8"))
            self.assertEqual(migrated["schema"], 2)

    def test_radio_presets_xml_export_import_preserves_multiple_frequencies(self):
        previous_path = rs.RADIO_PRESETS_PATH
        previous_presets = rs.radio_presets
        self.addCleanup(lambda: (
            setattr(rs, "RADIO_PRESETS_PATH", previous_path),
            setattr(rs, "radio_presets", previous_presets),
        ))
        with tempfile.TemporaryDirectory() as directory:
            rs.RADIO_PRESETS_PATH = Path(directory) / "radio_presets.json"
            rs.radio_presets = []
            rs.save_radio_preset({
                "name": "WWV",
                "frequency_khz": 10000,
                "frequencies_khz": [2500, 5000, 10000],
                "center_lat": 35.25,
                "center_lon": -117.5,
                "radius_km": 1800,
                "mode": "usb",
                "passband_low": 300,
                "passband_high": 2700,
                "rotation_minutes": 9,
            })
            xml_data = rs.export_radio_presets_xml()
            root = ET.fromstring(xml_data)
            self.assertEqual(root.tag, "radio-stream-presets")
            self.assertEqual(root.get("version"), "2")
            self.assertEqual(
                [float(node.text) for node in root.findall("./preset/frequencies-khz/frequency")],
                [2500, 5000, 10000],
            )

            rs.radio_presets = []
            result = rs.import_radio_presets_xml(xml_data.decode("utf-8"))
            self.assertEqual(result["added"], 1)
            self.assertEqual(result["updated"], 0)
            imported = result["presets"][0]
            self.assertEqual(imported["frequency_khz"], 10000)
            self.assertEqual(imported["frequencies_khz"], [2500, 5000, 10000])
            self.assertEqual(imported["center_lat"], 35.25)
            self.assertEqual(imported["center_lon"], -117.5)
            self.assertEqual(imported["radius_km"], 1800)
            self.assertEqual(imported["rotation_minutes"], 9)

            legacy_xml = """<radio-stream-presets version="1">
              <preset>
                <name>Old XML preset</name>
                <frequency-khz>4625</frequency-khz>
                <mode>am</mode>
                <passband-low>-4900</passband-low>
                <passband-high>4900</passband-high>
              </preset>
            </radio-stream-presets>"""
            legacy_result = rs.import_radio_presets_xml(legacy_xml)
            self.assertEqual(legacy_result["added"], 1)
            self.assertEqual(legacy_result["presets"][-1]["frequencies_khz"], [4625])
            self.assertEqual(
                legacy_result["presets"][-1]["center_lat"],
                rs.DEFAULT_CONFIG["center_lat"],
            )
            self.assertEqual(
                legacy_result["presets"][-1]["center_lon"],
                rs.DEFAULT_CONFIG["center_lon"],
            )
            self.assertEqual(
                legacy_result["presets"][-1]["radius_km"],
                rs.DEFAULT_CONFIG["radius_km"],
            )

            with self.assertRaises(ValueError):
                rs.import_radio_presets_xml('<radio-stream-presets version="99"/>')

            missing_v2_map_fields = """<radio-stream-presets version="2">
              <preset>
                <name>Invalid v2 preset</name>
                <frequency-khz>4625</frequency-khz>
                <frequencies-khz><frequency>4625</frequency></frequencies-khz>
                <mode>am</mode>
                <passband-low>-4900</passband-low>
                <passband-high>4900</passband-high>
                <rotation-minutes>14</rotation-minutes>
              </preset>
            </radio-stream-presets>"""
            with self.assertRaisesRegex(ValueError, "missing required map fields"):
                rs.import_radio_presets_xml(missing_v2_map_fields)

    def test_full_backup_xml_round_trip_restores_all_user_data(self):
        previous = {
            "CONFIG_PATH": rs.CONFIG_PATH,
            "RADIO_PRESETS_PATH": rs.RADIO_PRESETS_PATH,
            "OPENWEBRX_CUSTOM_PATH": rs.OPENWEBRX_CUSTOM_PATH,
            "STATION_PREFERENCES_PATH": rs.STATION_PREFERENCES_PATH,
            "config": rs.config,
            "radio_presets": rs.radio_presets,
            "openwebrx_custom_data": rs.openwebrx_custom_data,
            "station_preferences": rs.station_preferences,
        }
        def restore_previous():
            for key, value in previous.items():
                setattr(rs, key, value)
        self.addCleanup(restore_previous)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rs.CONFIG_PATH = root / "radiostream.json"
            rs.RADIO_PRESETS_PATH = root / "radio_presets.json"
            rs.OPENWEBRX_CUSTOM_PATH = root / "openwebrx_custom.json"
            rs.STATION_PREFERENCES_PATH = root / "station_preferences.json"

            rs.config = dict(rs.DEFAULT_CONFIG)
            rs.config.update({
                "center_lat": 42.5,
                "center_lon": -73.25,
                "radius_km": 1250,
                "frequency_khz": 10000,
                "frequencies_khz": [2500, 5000, 10000],
                "overlay_reload_notice": "Reload message\nSecond line",
                "overlay_black_notice": "Black screen message",
                "openwebrx_custom_enabled": False,
            })
            rs.radio_presets = [rs.normalize_radio_preset({
                "id": "preset-backup",
                "name": "Backup preset",
                "frequency_khz": 10000,
                "frequencies_khz": [2500, 5000, 10000],
                "center_lat": 42.5,
                "center_lon": -73.25,
                "radius_km": 1250,
                "mode": "usb",
                "passband_low": 300,
                "passband_high": 2700,
                "rotation_minutes": 11,
            })]
            rs.openwebrx_custom_data = [rs.normalize_custom_openwebrx_instance({
                "url": "https://backup-sdr.example.test/",
                "name": "Backup receiver",
                "lat": 43.0,
                "lon": -74.0,
                "frequency_ranges": [{"low_hz": 4000000, "high_hz": 12000000}],
                "frequency_checked_at": 123456.0,
            })]
            rs.station_preferences = {
                "kiwi:liked": "like",
                "kiwi:blocked": "block",
            }

            xml_backup = rs.export_all_data_xml()
            xml_root = ET.fromstring(xml_backup)
            self.assertEqual(xml_root.tag, "radiostream-plus-backup")
            self.assertEqual(xml_root.get("version"), "2")
            self.assertIsNotNone(xml_root.find("configuration"))
            self.assertIsNotNone(xml_root.find("presets"))
            self.assertIsNotNone(xml_root.find("custom_openwebrx"))
            self.assertIsNotNone(xml_root.find("station_preferences"))

            rs.config = dict(rs.DEFAULT_CONFIG)
            rs.radio_presets = []
            rs.openwebrx_custom_data = []
            rs.station_preferences = {}

            result = rs.import_all_data_xml(xml_backup.decode("utf-8"))
            self.assertEqual(result, {
                "presets": 1,
                "custom_receivers": 1,
                "station_preferences": 2,
            })
            self.assertEqual(rs.config["center_lat"], 42.5)
            self.assertEqual(rs.config["center_lon"], -73.25)
            self.assertEqual(rs.config["radius_km"], 1250)
            self.assertEqual(rs.config["frequencies_khz"], [2500, 5000, 10000])
            self.assertEqual(rs.config["overlay_reload_notice"], "Reload message\nSecond line")
            self.assertEqual(rs.config["overlay_black_notice"], "Black screen message")
            self.assertFalse(rs.config["openwebrx_custom_enabled"])
            self.assertEqual(rs.get_radio_presets()[0]["center_lat"], 42.5)
            self.assertEqual(rs.get_radio_presets()[0]["radius_km"], 1250)
            restored_receiver = rs.get_custom_openwebrx_instances()[0]
            self.assertEqual(restored_receiver["name"], "Backup receiver")
            self.assertEqual(
                restored_receiver["frequency_ranges"],
                [{"low_hz": 4000000.0, "high_hz": 12000000.0}],
            )
            self.assertEqual(rs.get_station_preference("kiwi:liked"), "like")
            self.assertEqual(rs.get_station_preference("kiwi:blocked"), "block")

            saved_config = json.loads(rs.CONFIG_PATH.read_text(encoding="utf-8"))
            saved_presets = json.loads(rs.RADIO_PRESETS_PATH.read_text(encoding="utf-8"))
            saved_receivers = json.loads(rs.OPENWEBRX_CUSTOM_PATH.read_text(encoding="utf-8"))
            saved_preferences = json.loads(rs.STATION_PREFERENCES_PATH.read_text(encoding="utf-8"))
            self.assertEqual(saved_config["radius_km"], 1250)
            self.assertEqual(saved_presets["schema"], 2)
            self.assertEqual(saved_receivers["schema"], 1)
            self.assertEqual(saved_preferences["stations"]["kiwi:blocked"], "block")

            # Version 1 backups remain importable when their presets lack map fields.
            legacy_root = ET.fromstring(xml_backup)
            legacy_root.set("version", "1")
            for preset_node in legacy_root.findall("./presets/item"):
                if preset_node.get("type") == "dict":
                    for entry in list(preset_node):
                        if entry.get("key") in {"center_lat", "center_lon", "radius_km"}:
                            preset_node.remove(entry)
            legacy_result = rs.import_all_data_xml(
                ET.tostring(legacy_root, encoding="unicode")
            )
            self.assertEqual(legacy_result["presets"], 1)
            restored_legacy_preset = rs.get_radio_presets()[0]
            self.assertEqual(
                restored_legacy_preset["center_lat"],
                rs.DEFAULT_CONFIG["center_lat"],
            )
            self.assertEqual(
                restored_legacy_preset["center_lon"],
                rs.DEFAULT_CONFIG["center_lon"],
            )
            self.assertEqual(
                restored_legacy_preset["radius_km"],
                rs.DEFAULT_CONFIG["radius_km"],
            )

    def test_full_backup_rejects_unsupported_version_without_changing_data(self):
        previous_config = rs.config
        previous_presets = rs.radio_presets
        self.addCleanup(lambda: (
            setattr(rs, "config", previous_config),
            setattr(rs, "radio_presets", previous_presets),
        ))
        rs.config = dict(rs.DEFAULT_CONFIG)
        rs.radio_presets = []
        with self.assertRaises(ValueError):
            rs.import_all_data_xml('<radiostream-plus-backup version="99"/>')
        self.assertEqual(rs.config["frequency_khz"], rs.DEFAULT_CONFIG["frequency_khz"])
        self.assertEqual(rs.radio_presets, [])

    def test_radio_presets_persist_update_and_delete(self):
        previous_path = rs.RADIO_PRESETS_PATH
        previous_presets = rs.radio_presets
        self.addCleanup(lambda: (
            setattr(rs, "RADIO_PRESETS_PATH", previous_path),
            setattr(rs, "radio_presets", previous_presets),
        ))
        with tempfile.TemporaryDirectory() as directory:
            rs.RADIO_PRESETS_PATH = Path(directory) / "radio_presets.json"
            rs.radio_presets = []
            original = {
                "name": "The Pip",
                "frequency_khz": 3750,
                "mode": "usb",
                "passband_low": 300,
                "passband_high": 2700,
            }
            saved = rs.save_radio_preset(original)
            self.assertEqual(len(saved), 1)
            first_id = saved[0]["id"]

            updated = rs.save_radio_preset({
                **original,
                "frequency_khz": 4000,
            })
            self.assertEqual(len(updated), 1)
            self.assertEqual(updated[0]["id"], first_id)
            self.assertEqual(updated[0]["frequency_khz"], 4000)

            rs.radio_presets = []
            rs.load_radio_presets()
            self.assertEqual(rs.get_radio_presets()[0]["name"], "The Pip")
            self.assertEqual(rs.get_radio_presets()[0]["frequency_khz"], 4000)

            removed = rs.remove_radio_preset(first_id)
            self.assertEqual(removed, [])

    def test_directory_schema_validation(self):
        good = {"schema": 1, "receivers": [self.sample()]}
        self.assertEqual(len(rs.validate_directory(good)), 1)
        with self.assertRaises(ValueError):
            rs.validate_directory({"schema": 2, "receivers": []})
        with self.assertRaises(ValueError):
            rs.validate_directory({"schema": 1, "receivers": "not a list"})


if __name__ == "__main__":
    unittest.main()
