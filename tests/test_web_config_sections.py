import unittest

from home_cinema_control.web.config_sections import (
    apply_config_section,
    apply_media_server_section,
    apply_network_access_section,
    apply_path_mappings_section,
    apply_playback_libraries_section,
)


class ConfigSectionSaveTest(unittest.TestCase):
    def test_saves_oppo_without_overwriting_other_sections(self):
        config = {
            "oppo": {"ip": "192.168.1.10", "always_on": True},
            "tv": {"enabled": True, "model": "LG", "ip": "192.168.1.20"},
            "media_servers": {
                "active": "emby",
                "providers": {
                    "emby": {"playback": {"path_mappings": [{"name": "Movies"}]}}
                },
            },
        }

        updated = apply_config_section(config, "oppo", {"ip": "192.168.1.11"})

        self.assertEqual("192.168.1.11", updated["oppo"]["ip"])
        self.assertTrue(updated["oppo"]["always_on"])
        self.assertEqual(config["tv"], updated["tv"])
        self.assertEqual(config["media_servers"], updated["media_servers"])

    def test_saves_media_server_device_selector_without_overwriting_other_playback_fields(self):
        config = {
            "media_servers": {
                "active": "emby",
                "providers": {
                    "emby": {
                        "server_url": "http://old",
                        "playback": {
                            "hcc_controlled_device": "old-client",
                            "path_mappings": [{"name": "Movies"}],
                            "libraries": [{"id": "1", "name": "Movies", "active": True}],
                        },
                    }
                },
            },
        }

        updated = apply_config_section(
            config,
            "media-server",
            {
                "media_server": {"server_url": "http://new"},
                "playback": {"hcc_controlled_device": "new-client"},
            },
        )

        emby = updated["media_servers"]["providers"]["emby"]
        self.assertEqual("http://new", emby["server_url"])
        self.assertEqual("emby", updated["media_servers"]["active"])
        self.assertEqual("new-client", emby["playback"]["hcc_controlled_device"])
        self.assertEqual([{"name": "Movies", "source_path": "", "player_path": "/", "protocol": "", "verified": False,
              "power_switch_entity_id": "", "power_wait_timeout_seconds": None}],
                         emby["playback"]["path_mappings"])
        self.assertEqual([{"id": "1", "name": "Movies", "active": True}], emby["playback"]["libraries"])

    def test_media_server_device_selector_does_not_touch_other_providers_playback(self):
        config = {
            "media_servers": {
                "active": "emby",
                "providers": {
                    "emby": {"playback": {"hcc_controlled_device": "old-client"}},
                    "jellyfin": {"playback": {"hcc_controlled_device": "jf-client"}},
                },
            },
        }

        updated = apply_config_section(
            config,
            "media-server",
            {"playback": {"hcc_controlled_device": "new-client"}},
        )

        self.assertEqual(
            "new-client",
            updated["media_servers"]["providers"]["emby"]["playback"]["hcc_controlled_device"],
        )
        self.assertEqual(
            "jf-client",
            updated["media_servers"]["providers"]["jellyfin"]["playback"]["hcc_controlled_device"],
        )

    def test_media_server_switch_lands_in_target_providers_entry(self):
        config = {
            "media_servers": {
                "active": "emby",
                "providers": {"emby": {"server_url": "http://emby"}},
            },
        }

        updated = apply_config_section(
            config,
            "media-server",
            {"media_server": {"type": "jellyfin", "server_url": "http://jf"}},
        )

        self.assertEqual("jellyfin", updated["media_servers"]["active"])
        self.assertEqual(
            "http://jf", updated["media_servers"]["providers"]["jellyfin"]["server_url"]
        )
        self.assertEqual(
            "http://emby", updated["media_servers"]["providers"]["emby"]["server_url"]
        )

    def test_saves_libraries_without_overwriting_path_mappings(self):
        config = {
            "media_servers": {
                "active": "emby",
                "providers": {
                    "emby": {
                        "playback": {
                            "path_mappings": [{"name": "Movies"}],
                            "libraries": [],
                            "use_all_libraries": True,
                        }
                    }
                },
            },
        }

        updated = apply_config_section(
            config,
            "playback-libraries",
            {"libraries": [{"name": "Series", "active": True}], "use_all_libraries": False},
        )

        emby_playback = updated["media_servers"]["providers"]["emby"]["playback"]
        self.assertEqual(
            [{"name": "Movies", "source_path": "", "player_path": "/", "protocol": "", "verified": False,
              "power_switch_entity_id": "", "power_wait_timeout_seconds": None}],
            emby_playback["path_mappings"],
        )
        self.assertEqual([{"id": "", "name": "Series", "active": True}], emby_playback["libraries"])
        self.assertFalse(emby_playback["use_all_libraries"])

    def test_libraries_save_does_not_touch_other_providers_playback(self):
        config = {
            "media_servers": {
                "active": "jellyfin",
                "providers": {
                    "emby": {"playback": {"libraries": [{"id": "1", "name": "Old", "active": True}]}},
                    "jellyfin": {},
                },
            },
        }

        updated = apply_config_section(
            config,
            "playback-libraries",
            {"libraries": [{"name": "New", "active": True}], "use_all_libraries": False},
        )

        emby_libraries = updated["media_servers"]["providers"]["emby"]["playback"]["libraries"]
        self.assertEqual([{"id": "1", "name": "Old", "active": True}], emby_libraries)

    def test_saves_path_mappings_without_overwriting_libraries(self):
        config = {
            "media_servers": {
                "active": "emby",
                "providers": {
                    "emby": {
                        "playback": {
                            "path_mappings": [{"name": "Old", "verified": False}],
                            "libraries": [{"id": "1", "name": "Movies", "active": True}],
                        }
                    }
                },
            },
        }

        updated = apply_config_section(
            config,
            "path-mappings",
            {"path_mappings": [{"name": "Movies", "source_path": "/m", "verified": True}]},
        )

        emby_playback = updated["media_servers"]["providers"]["emby"]["playback"]
        self.assertEqual(
            [{"name": "Movies", "source_path": "/m", "player_path": "/", "protocol": "", "verified": True,
              "power_switch_entity_id": "", "power_wait_timeout_seconds": None}],
            emby_playback["path_mappings"],
        )
        self.assertEqual([{"id": "1", "name": "Movies", "active": True}], emby_playback["libraries"])

    def test_saves_network_access_without_overwriting_libraries(self):
        config = {
            "oppo": {"pre_mount_smb": False, "always_on": True},
            "smb": {"username": "old", "password": "secret"},
            "media_servers": {
                "active": "emby",
                "providers": {
                    "emby": {
                        "playback": {
                            "path_mappings": [{"name": "Movies", "verified": True}],
                            "libraries": [{"id": "1", "name": "Movies", "active": True}],
                        }
                    }
                },
            },
        }

        updated = apply_config_section(
            config,
            "network-access",
            {
                "oppo": {"pre_mount_smb": True},
                "smb": {"username": "new", "password": ""},
                "path_mappings": [{"name": "Movies", "verified": False}],
            },
        )

        self.assertTrue(updated["oppo"]["pre_mount_smb"])
        self.assertTrue(updated["oppo"]["always_on"])
        self.assertEqual("new", updated["smb"]["username"])
        self.assertEqual("", updated["smb"]["password"])
        emby_playback = updated["media_servers"]["providers"]["emby"]["playback"]
        self.assertEqual(
            [{"name": "Movies", "source_path": "", "player_path": "/", "protocol": "", "verified": False,
              "power_switch_entity_id": "", "power_wait_timeout_seconds": None}],
            emby_playback["path_mappings"],
        )
        self.assertEqual([{"id": "1", "name": "Movies", "active": True}], emby_playback["libraries"])

    def test_network_access_without_path_mappings_does_not_touch_playback(self):
        config = {
            "oppo": {"pre_mount_smb": False},
            "smb": {"username": "old"},
            "media_servers": {
                "active": "emby",
                "providers": {
                    "emby": {"playback": {"path_mappings": [{"name": "Movies"}]}}
                },
            },
        }

        updated = apply_config_section(
            config, "network-access", {"oppo": {"pre_mount_smb": True}}
        )

        self.assertEqual(
            config["media_servers"]["providers"]["emby"]["playback"]["path_mappings"],
            updated["media_servers"]["providers"]["emby"]["playback"]["path_mappings"],
        )

    def test_rejects_unknown_section(self):
        with self.assertRaises(ValueError):
            apply_config_section({}, "unknown", {})


class ConfigSectionHandlerTest(unittest.TestCase):
    """The per-section handlers called directly, with no section-string seam."""

    def test_media_server_handler_accepts_flat_bare_body(self):
        config = {
            "media_servers": {
                "active": "emby",
                "providers": {"emby": {"server_url": "http://old"}},
            },
        }

        updated = apply_media_server_section(
            config, {"type": "jellyfin", "server_url": "http://jf"}
        )

        self.assertEqual("jellyfin", updated["media_servers"]["active"])
        self.assertEqual(
            "http://jf", updated["media_servers"]["providers"]["jellyfin"]["server_url"]
        )

    def test_media_server_handler_accepts_wrapped_body(self):
        config = {
            "media_servers": {
                "active": "emby",
                "providers": {"emby": {"server_url": "http://old"}},
            },
        }

        updated = apply_media_server_section(
            config, {"media_server": {"server_url": "http://new"}}
        )

        self.assertEqual("http://new", updated["media_servers"]["providers"]["emby"]["server_url"])

    def test_media_server_handler_omitted_field_does_not_blank_stored_value(self):
        config = {
            "media_servers": {
                "active": "emby",
                "providers": {
                    "emby": {"server_url": "http://keep", "display_name": "Casa"}
                },
            },
        }

        # Only display_name sent — server_url must survive untouched.
        updated = apply_media_server_section(
            config, {"media_server": {"display_name": "Salon"}}
        )

        emby = updated["media_servers"]["providers"]["emby"]
        self.assertEqual("http://keep", emby["server_url"])
        self.assertEqual("Salon", emby["display_name"])

    def test_media_server_handler_never_writes_auth_fields(self):
        config = {
            "media_servers": {
                "active": "emby",
                "providers": {"emby": {"access_token": "secret", "user_id": "u1"}},
            },
        }

        updated = apply_media_server_section(
            config, {"media_server": {"server_url": "http://new", "access_token": "HACK"}}
        )

        emby = updated["media_servers"]["providers"]["emby"]
        self.assertEqual("secret", emby["access_token"])
        self.assertEqual("u1", emby["user_id"])

    def test_libraries_handler_leaves_path_mappings_untouched(self):
        config = {
            "media_servers": {
                "active": "emby",
                "providers": {
                    "emby": {"playback": {"path_mappings": [{"name": "Movies"}]}}
                },
            },
        }

        updated = apply_playback_libraries_section(
            config, {"libraries": [{"name": "Series", "active": True}], "use_all_libraries": False}
        )

        playback = updated["media_servers"]["providers"]["emby"]["playback"]
        self.assertEqual([{"id": "", "name": "Series", "active": True}], playback["libraries"])
        self.assertFalse(playback["use_all_libraries"])
        self.assertEqual(1, len(playback["path_mappings"]))

    def test_path_mappings_handler_leaves_libraries_untouched(self):
        config = {
            "media_servers": {
                "active": "emby",
                "providers": {
                    "emby": {
                        "playback": {"libraries": [{"id": "1", "name": "Movies", "active": True}]}
                    }
                },
            },
        }

        updated = apply_path_mappings_section(
            config, {"path_mappings": [{"name": "Movies", "source_path": "/m"}]}
        )

        playback = updated["media_servers"]["providers"]["emby"]["playback"]
        self.assertEqual([{"id": "1", "name": "Movies", "active": True}], playback["libraries"])
        self.assertEqual("/m", playback["path_mappings"][0]["source_path"])

    def test_network_access_handler_without_path_mappings_skips_playback(self):
        config = {
            "oppo": {"pre_mount_smb": False},
            "smb": {"username": "old"},
            "media_servers": {
                "active": "emby",
                "providers": {"emby": {"playback": {"path_mappings": [{"name": "Movies"}]}}},
            },
        }

        updated = apply_network_access_section(config, {"oppo": {"pre_mount_smb": True}})

        self.assertTrue(updated["oppo"]["pre_mount_smb"])
        self.assertEqual(
            config["media_servers"]["providers"]["emby"]["playback"]["path_mappings"],
            updated["media_servers"]["providers"]["emby"]["playback"]["path_mappings"],
        )


if __name__ == "__main__":
    unittest.main()
