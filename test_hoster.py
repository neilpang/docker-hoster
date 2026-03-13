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
        """Should skip network entries where Aliases is None."""
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
        # Aliases is None so the network entry is skipped, and container_ip is empty
        self.assertEqual(len(result), 0)

    def test_aliases_missing_key(self):
        """Should skip network entries where Aliases key is missing."""
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
        self.assertEqual(len(result), 0)

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


if __name__ == "__main__":
    unittest.main()
