# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest
from unittest.mock import patch

import ops
import ops.testing
from charm import FoxgloveStudioCharm
import yaml

ops.testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = ops.testing.Harness(FoxgloveStudioCharm)
        self.addCleanup(self.harness.cleanup)

        self.name = "foxglove-studio"
        self.harness.set_model_name("testmodel")
        self.harness.begin_with_initial_hooks()
        self.harness.container_pebble_ready(self.name)

    def test_foxglove_studio_pebble_ready(self):
        # Expected plan after Pebble ready with default config
        command = " ".join(
            [
                "caddy",
                "file-server",
                "--listen",
                ":8080",
            ]
        )

        expected_plan = {
            "services": {
                self.name: {
                    "override": "replace",
                    "summary": "foxglove-studio-k8s service",
                    "command": command,
                    "startup": "enabled",
                }
            },
        }
        # Simulate the container coming up and emission of pebble-ready event
        self.harness.container_pebble_ready(self.name)
        # Get the plan now we've run PebbleReady
        updated_plan = self.harness.get_container_pebble_plan(self.name).to_dict()
        # Check we've got the plan we expected
        self.assertEqual(expected_plan, updated_plan)
        # Check the service was started
        service = self.harness.model.unit.get_container(self.name).get_service(self.name)
        self.assertTrue(service.is_running())
        # Ensure we set an ActiveStatus with no message
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())

    def test_config_changed_valid_can_connect(self):
        # Ensure the simulated Pebble API is reachable
        self.harness.set_can_connect("foxglove-studio", True)
        # Trigger a config-changed event with an updated value
        self.harness.update_config({"server-port": 5050})
        # Get the plan now we've run PebbleReady
        updated_plan = self.harness.get_container_pebble_plan("foxglove-studio").to_dict()
        updated_env = updated_plan["services"]["foxglove-studio"]["command"]
        # Check the config change was effective
        self.assertEqual(updated_env, "caddy file-server --listen :5050")
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())

    def test_config_changed_invalid(self):
        # Ensure the simulated Pebble API is reachable
        self.harness.set_can_connect("foxglove-studio", True)
        # Trigger a config-changed event with an updated value
        self.harness.update_config({"server-port": 22})
        # Check the charm is in BlockedStatus
        self.assertIsInstance(self.harness.model.unit.status, ops.BlockedStatus)

    @patch.multiple("charm.TraefikRouteRequirer", external_host="1.2.3.4")
    @patch("socket.getfqdn", new=lambda *args: "foxglove-studio-0.testmodel.svc.cluster.local")
    def test_ingress_relation_sets_options_and_rel_data(self):
        self.harness.set_leader(True)
        self.harness.container_pebble_ready(self.name)
        rel_id = self.harness.add_relation("ingress", "traefik")
        self.harness.add_relation_unit(rel_id, "traefik/0")

        expected_rel_data = {
            "http": {
                "middlewares": {
                    "juju-sidecar-noprefix-testmodel-foxglove-studio": {
                        "stripPrefix": {
                            "forceSlash": False,
                            "prefixes": ["/testmodel-foxglove-studio"],
                        }
                    },
                    "juju-sidecar-trailing-slash-handler-testmodel-foxglove-studio": {
                        "redirectRegex": {
                            "permanent": False,
                            "regex": "^(.*)\/testmodel-foxglove-studio$",  # noqa
                            "replacement": "/testmodel-foxglove-studio/",
                        }
                    },
                },
                "routers": {
                    "juju-testmodel-foxglove-studio-router": {
                        "entryPoints": ["web"],
                        "middlewares": [
                            "juju-sidecar-trailing-slash-handler-testmodel-foxglove-studio",
                            "juju-sidecar-noprefix-testmodel-foxglove-studio",
                        ],
                        "rule": "PathPrefix(`/testmodel-foxglove-studio`)",
                        "service": "juju-testmodel-foxglove-studio-service",
                    },
                    "juju-testmodel-foxglove-studio-router-tls": {
                        "entryPoints": ["websecure"],
                        "middlewares": [
                            "juju-sidecar-trailing-slash-handler-testmodel-foxglove-studio",
                            "juju-sidecar-noprefix-testmodel-foxglove-studio",
                        ],
                        "rule": "PathPrefix(`/testmodel-foxglove-studio`)",
                        "service": "juju-testmodel-foxglove-studio-service",
                        "tls": {"domains": [{"main": "1.2.3.4", "sans": ["*.1.2.3.4"]}]},
                    },
                },
                "services": {
                    "juju-testmodel-foxglove-studio-service": {
                        "loadBalancer": {
                            "servers": [
                                {
                                    "url": "http://foxglove-studio-0.testmodel.svc.cluster.local:8080"
                                }
                            ]
                        }
                    },
                },
            }
        }
        rel_data = self.harness.get_relation_data(rel_id, self.harness.charm.app.name)

        # The insanity of YAML here. It works for the lib, but a single load just strips off
        # the extra quoting and leaves regular YAML. Double parse it for the tests
        self.maxDiff = None
        self.assertEqual(yaml.safe_load(rel_data["config"]), expected_rel_data)

        self.assertEqual(
            self.harness.charm.external_url, "http://1.2.3.4/testmodel-foxglove-studio"
        )
