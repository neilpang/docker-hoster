#!/usr/bin/python3
import unittest
from unittest.mock import MagicMock

import hoster


class TestGetContainerData(unittest.TestCase):
    """Tests for get_container_data to ensure it handles missing keys gracefully."""

    def _make_docker_client(self, inspect_return):
        client = MagicMock()
        client.inspect_container.return_value = inspect_return
        return client

    def test_missing_ip_address_key(self):
        """KeyError: 'IPAddress' should not be raised when IPAddress is missing from NetworkSettings."""
        info = {
            "Config": {"Hostname": "abc123", "Domainname": ""},
            "Name": "/my_container",
            "NetworkSettings": {
                # No "IPAddress" key at all
                "Networks": {}
            },
            "HostConfig": {"NetworkMode": "default"},
        }
        client = self._make_docker_client(info)
        result = hoster.get_container_data(client, "container_id_1")
        self.assertIsInstance(result, list)

    def test_ip_address_present(self):
        """Normal case where IPAddress is present."""
        info = {
            "Config": {"Hostname": "abc123", "Domainname": ""},
            "Name": "/my_container",
            "NetworkSettings": {
                "IPAddress": "172.17.0.2",
                "Networks": {}
            },
            "HostConfig": {"NetworkMode": "default"},
        }
        client = self._make_docker_client(info)
        result = hoster.get_container_data(client, "container_id_2")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ip"], "172.17.0.2")

    def test_networks_is_none(self):
        """Should not crash when Networks is None."""
        info = {
            "Config": {"Hostname": "abc123", "Domainname": ""},
            "Name": "/my_container",
            "NetworkSettings": {
                "IPAddress": "172.17.0.2",
                "Networks": None
            },
            "HostConfig": {"NetworkMode": "default"},
        }
        client = self._make_docker_client(info)
        result = hoster.get_container_data(client, "container_id_3")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ip"], "172.17.0.2")

    def test_networks_missing_key(self):
        """Should not crash when Networks key is missing entirely."""
        info = {
            "Config": {"Hostname": "abc123", "Domainname": ""},
            "Name": "/my_container",
            "NetworkSettings": {
                "IPAddress": "172.17.0.2",
            },
            "HostConfig": {"NetworkMode": "default"},
        }
        client = self._make_docker_client(info)
        result = hoster.get_container_data(client, "container_id_4")
        self.assertEqual(len(result), 1)

    def test_aliases_none(self):
        """A network with an IP but Aliases=None must still map the container name.

        Docker leaves Aliases null on the default bridge network, so requiring
        aliases here would drop every default-bridge container.
        """
        info = {
            "Config": {"Hostname": "abc123", "Domainname": ""},
            "Name": "/my_container",
            "NetworkSettings": {
                "IPAddress": "",
                "Networks": {
                    "bridge": {
                        "IPAddress": "172.17.0.2",
                        "Aliases": None
                    }
                }
            },
            "HostConfig": {"NetworkMode": "default"},
        }
        client = self._make_docker_client(info)
        result = hoster.get_container_data(client, "container_id_5")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ip"], "172.17.0.2")
        self.assertIn("my_container", result[0]["domains"])

    def test_aliases_missing_key(self):
        """A network with an IP but no Aliases key must still map the container name."""
        info = {
            "Config": {"Hostname": "abc123", "Domainname": ""},
            "Name": "/my_container",
            "NetworkSettings": {
                "IPAddress": "",
                "Networks": {
                    "bridge": {
                        "IPAddress": "172.17.0.2",
                        # No "Aliases" key
                    }
                }
            },
            "HostConfig": {"NetworkMode": "default"},
        }
        client = self._make_docker_client(info)
        result = hoster.get_container_data(client, "container_id_6")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ip"], "172.17.0.2")
        self.assertIn("my_container", result[0]["domains"])

    def test_host_network_mode(self):
        """Should set IP to 127.0.0.1 for host network mode."""
        info = {
            "Config": {"Hostname": "abc123", "Domainname": ""},
            "Name": "/my_container",
            "NetworkSettings": {
                "IPAddress": "",
                "Networks": {}
            },
            "HostConfig": {"NetworkMode": "host"},
        }
        client = self._make_docker_client(info)
        result = hoster.get_container_data(client, "container_id_7")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ip"], "127.0.0.1")

    def test_missing_host_config(self):
        """Should not crash when HostConfig is missing."""
        info = {
            "Config": {"Hostname": "abc123", "Domainname": ""},
            "Name": "/my_container",
            "NetworkSettings": {
                "Networks": {}
            },
        }
        client = self._make_docker_client(info)
        result = hoster.get_container_data(client, "container_id_8")
        self.assertIsInstance(result, list)

    def test_missing_domainname(self):
        """Should not crash when Domainname is missing from Config."""
        info = {
            "Config": {"Hostname": "abc123"},
            "Name": "/my_container",
            "NetworkSettings": {
                "IPAddress": "172.17.0.2",
                "Networks": {}
            },
            "HostConfig": {"NetworkMode": "default"},
        }
        client = self._make_docker_client(info)
        result = hoster.get_container_data(client, "container_id_9")
        self.assertEqual(len(result), 1)

    def test_network_entry_missing_ip(self):
        """Should handle network entries missing IPAddress gracefully."""
        info = {
            "Config": {"Hostname": "abc123", "Domainname": ""},
            "Name": "/my_container",
            "NetworkSettings": {
                "IPAddress": "",
                "Networks": {
                    "mynet": {
                        "Aliases": ["alias1", "alias2"],
                        # No "IPAddress" key
                    }
                }
            },
            "HostConfig": {"NetworkMode": "default"},
        }
        client = self._make_docker_client(info)
        result = hoster.get_container_data(client, "container_id_10")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ip"], "")

    def test_default_bridge_container_on_modern_api(self):
        """A default-bridge container must be mapped on Docker >= 28.

        Docker dropped the top-level NetworkSettings.IPAddress field, and the
        default bridge network carries no Aliases. Both of the old lookup paths
        therefore come up empty and the container silently disappears from
        /etc/hosts. This is the exact payload shape seen from Docker 29.7.1.
        """
        info = {
            "Config": {"Hostname": "9f3c1b2a4d5e"},
            "Name": "/charm1dir",
            "NetworkSettings": {
                # no top-level "IPAddress" -- removed by the modern API
                "Networks": {
                    "bridge": {
                        "IPAddress": "172.17.0.5",
                        "Aliases": None,
                    }
                },
            },
            "HostConfig": {"NetworkMode": "default"},
        }
        client = self._make_docker_client(info)
        result = hoster.get_container_data(client, "container_id_11")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ip"], "172.17.0.5")
        self.assertIn("charm1dir", result[0]["domains"])

    def test_no_duplicate_entry_when_legacy_and_network_ip_agree(self):
        """Old daemons report the same IP twice; emit it once."""
        info = {
            "Config": {"Hostname": "abc123", "Domainname": ""},
            "Name": "/my_container",
            "NetworkSettings": {
                "IPAddress": "172.17.0.2",
                "Networks": {
                    "bridge": {
                        "IPAddress": "172.17.0.2",
                        "Aliases": None,
                    }
                },
            },
            "HostConfig": {"NetworkMode": "default"},
        }
        client = self._make_docker_client(info)
        result = hoster.get_container_data(client, "container_id_12")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ip"], "172.17.0.2")


class TestHandleEvent(unittest.TestCase):
    """Tests for the docker event stream handling.

    Docker's event payload used to carry top-level "status" and "id" fields.
    The modern API emits "Action" and "Actor.ID" instead and omits the legacy
    pair entirely, which made the old event loop die with KeyError on the very
    first container event.
    """

    def setUp(self):
        hoster.hosts = {}

    def _make_docker_client(self, inspect_return):
        client = MagicMock()
        client.inspect_container.return_value = inspect_return
        return client

    def _container_info(self, name, ip):
        return {
            "Config": {"Hostname": "hostname1"},
            "Name": "/" + name,
            "NetworkSettings": {"Networks": {"bridge": {"IPAddress": ip, "Aliases": None}}},
            "HostConfig": {"NetworkMode": "default"},
        }

    def test_modern_start_event_adds_container(self):
        """A modern start event (Action/Actor.ID, no status/id) registers the container."""
        event = {
            "Type": "container",
            "Action": "start",
            "Actor": {"ID": "cid1", "Attributes": {"name": "web"}},
            "scope": "local",
        }
        client = self._make_docker_client(self._container_info("web", "172.17.0.2"))
        changed = hoster.handle_event(client, event)
        self.assertTrue(changed)
        self.assertIn("cid1", hoster.hosts)

    def test_modern_die_event_removes_container(self):
        """A modern die event deregisters a known container."""
        hoster.hosts["cid1"] = [{"ip": "172.17.0.2", "name": "web", "domains": ["web"]}]
        event = {
            "Type": "container",
            "Action": "die",
            "Actor": {"ID": "cid1", "Attributes": {"name": "web"}},
        }
        client = self._make_docker_client({})
        changed = hoster.handle_event(client, event)
        self.assertTrue(changed)
        self.assertNotIn("cid1", hoster.hosts)

    def test_legacy_start_event_still_works(self):
        """Old daemons that still send status/id must keep working."""
        event = {
            "Type": "container",
            "status": "start",
            "id": "cid2",
            "from": "someimage",
        }
        client = self._make_docker_client(self._container_info("api", "172.17.0.3"))
        changed = hoster.handle_event(client, event)
        self.assertTrue(changed)
        self.assertIn("cid2", hoster.hosts)

    def test_non_container_event_ignored(self):
        """Network/image/volume events must not touch the hosts table."""
        event = {
            "Type": "network",
            "Action": "connect",
            "Actor": {"ID": "netid", "Attributes": {}},
        }
        client = self._make_docker_client({})
        changed = hoster.handle_event(client, event)
        self.assertFalse(changed)
        self.assertEqual(hoster.hosts, {})

    def test_qualified_action_is_not_treated_as_start(self):
        """Actions like 'exec_start: ls -l' must not be mistaken for 'start'."""
        event = {
            "Type": "container",
            "Action": "exec_start: ls -l",
            "Actor": {"ID": "cid3", "Attributes": {}},
        }
        client = self._make_docker_client(self._container_info("web", "172.17.0.4"))
        changed = hoster.handle_event(client, event)
        self.assertFalse(changed)
        self.assertNotIn("cid3", hoster.hosts)

    def test_event_without_identifiable_container_is_ignored(self):
        """A malformed event must be skipped rather than crash the loop."""
        event = {"Type": "container", "Action": "start"}
        client = self._make_docker_client({})
        changed = hoster.handle_event(client, event)
        self.assertFalse(changed)
        self.assertEqual(hoster.hosts, {})

    def test_unknown_die_event_is_a_noop(self):
        """A die event for a container we never registered changes nothing."""
        event = {
            "Type": "container",
            "Action": "die",
            "Actor": {"ID": "never-seen"},
        }
        client = self._make_docker_client({})
        changed = hoster.handle_event(client, event)
        self.assertFalse(changed)


if __name__ == "__main__":
    unittest.main()
