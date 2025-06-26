# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest

import ops
import ops.testing

from charm import FoxgloveStudioCharm

ops.testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = ops.testing.Harness(FoxgloveStudioCharm)
        self.addCleanup(self.harness.cleanup)

        self.name = "foxglove-studio"
        self.service_name = "studio"
        self.harness.set_model_name("testmodel")
        self.harness.begin_with_initial_hooks()
        self.harness.container_pebble_ready(self.name)

        self.maxDiff = None

    def test_foxglove_studio_pebble_ready(self):
        # Expected plan after Pebble ready with default config
        command = " ".join(
            [
                "caddy",
                "file-server",
                "--listen",
                ":8080",
                "--root",
                "foxglove",
            ]
        )

        expected_plan = {
            "services": {
                self.service_name: {
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
        service = self.harness.model.unit.get_container(self.name).get_service(self.service_name)
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
        self.assertIn("studio", updated_plan["services"])
        updated_env = updated_plan["services"]["studio"]["command"]
        # Check the config change was effective
        self.assertEqual(updated_env, "caddy file-server --listen :5050 --root foxglove")
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())

    def test_config_changed_invalid(self):
        # Ensure the simulated Pebble API is reachable
        self.harness.set_can_connect("foxglove-studio", True)
        # Trigger a config-changed event with an updated value
        self.harness.update_config({"server-port": 22})
        # Check the charm is in BlockedStatus
        self.assertIsInstance(self.harness.model.unit.status, ops.BlockedStatus)
