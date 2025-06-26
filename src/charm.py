#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  Copyright 2025 Canonical Ltd.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""A Kubernetes charm for Foxglove Studio."""

import logging
import socket
from typing import Optional, cast
from urllib.parse import urlparse

from charms.blackbox_exporter_k8s.v0.blackbox_probes import BlackboxProbesProvider
from charms.catalogue_k8s.v0.catalogue import CatalogueConsumer, CatalogueItem
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.tempo_coordinator_k8s.v0.charm_tracing import trace_charm
from charms.tempo_coordinator_k8s.v0.tracing import (
    ProtocolNotRequestedError,
    TracingEndpointRequirer,
)
from charms.traefik_k8s.v2.ingress import IngressPerAppRequirer
from ops.charm import CharmBase, CollectStatusEvent
from ops.main import main
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    OpenedPort,
    WaitingStatus,
)
from ops.pebble import Layer

logger = logging.getLogger()


@trace_charm(
    tracing_endpoint="tracing_endpoint",
    extra_types=(
        CatalogueConsumer,
        GrafanaDashboardProvider,
        LogForwarder,
        IngressPerAppRequirer,
    ),
)
class FoxgloveStudioCharm(CharmBase):
    """Charm to run Foxglove studio on Kubernetes."""

    def __init__(self, *args):
        super().__init__(*args)
        self.name = "foxglove-studio"
        self.service_name = "studio"

        self.container = self.unit.get_container(self.name)

        self.ingress = IngressPerAppRequirer(
            self, strip_prefix=True, port=cast(int, self.config["server-port"])
        )
        self.framework.observe(self.ingress.on.ready, self._on_ingress_ready)
        self.framework.observe(self.ingress.on.revoked, self._on_ingress_revoked)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(
            self.on.foxglove_studio_pebble_ready, self._update_layer_and_restart
        )
        self.framework.observe(self.on.config_changed, self._on_config_changed)

        self.catalog = CatalogueConsumer(
            charm=self,
            refresh_event=[
                self.on.foxglove_studio_pebble_ready,
                self.ingress.on.ready,
                self.on["ingress"].relation_broken,
                self.on.config_changed,
            ],
            item=CatalogueItem(
                name="Foxglove Studio",
                icon="graph-line",
                url=self.external_url + "/",
                description=("Query, visualize, and understand your ROS robotics data"),
            ),
        )

        self.blackbox_probes_provider = BlackboxProbesProvider(
            charm=self,
            probes=self.self_probe,
            refresh_event=[
                self.ingress.on.ready,
                self.on.update_status,
                self.on.config_changed,
            ],
        )
        self.grafana_dashboard_provider = GrafanaDashboardProvider(self)
        self.log_forwarder = LogForwarder(self)
        self.tracing_endpoint_requirer = TracingEndpointRequirer(self)

    def _on_install(self, _):
        """Handler for the "install" event during which we will update the K8s service."""
        self.set_ports()

    def _on_config_changed(self, event):
        self.set_ports()
        port = self.config["server-port"]  # see config.yaml

        if int(port) == 22:
            self.unit.status = BlockedStatus("invalid port number, 22 is reserved for SSH")
            return

        logger.debug("New application port is requested: %s", port)
        self.ingress.provide_ingress_requirements(port=cast(int, self.config["server-port"]))
        self._update_layer_and_restart(None)

    def _on_collect_status(self, event: CollectStatusEvent):
        event.add_status(self.blackbox_probes_provider.get_status())

    def _on_ingress_ready(self, _) -> None:
        """Once Traefik tells us our external URL, make sure we reconfigure Foxglove Studio."""
        self._update_layer_and_restart(None)

    def _on_ingress_revoked(self, _) -> None:
        logger.info("This app no longer has ingress")

    def _update_layer_and_restart(self, event) -> None:
        """Define and start a workload using the Pebble API."""
        # Learn more about statuses in the SDK docs:
        # https://juju.is/docs/sdk/constructs#heading--statuses

        self.unit.status = MaintenanceStatus("Assembling pod spec")
        if self.container.can_connect():
            new_layer = self._pebble_layer.to_dict()
            # Get the current pebble layer config
            services = self.container.get_plan().to_dict().get("services", {})
            if services != new_layer["services"]:  # pyright: ignore
                # Changes were made, add the new layer
                self.container.add_layer("foxglove-studio", self._pebble_layer, combine=True)

                logger.info("Added updated layer 'foxglove-studio' to Pebble plan")

                self.container.restart(self.service_name)
                logger.info(f"Restarted '{self.service_name}' service")
            self.unit.status = ActiveStatus()
        else:
            self.unit.status = WaitingStatus("Waiting for Pebble in workload container")

    def set_ports(self):
        """Open necessary (and close no longer needed) workload ports."""
        planned_ports = (
            {OpenedPort("tcp", int(self.config["server-port"]))}
            if self.unit.is_leader()
            else set()
        )

        actual_ports = self.unit.opened_ports()

        # Ports may change across an upgrade, so need to sync
        ports_to_close = actual_ports.difference(planned_ports)
        for p in ports_to_close:
            self.unit.close_port(p.protocol, p.port)

        new_ports_to_open = planned_ports.difference(actual_ports)
        for p in new_ports_to_open:
            self.unit.open_port(p.protocol, p.port)

    @property
    def _scheme(self) -> str:
        return "http"

    @property
    def internal_host(self) -> str:
        """Return workload's internal host. Used for ingress."""
        return f"{socket.getfqdn()}"

    @property
    def internal_url(self) -> str:
        """Return workload's internal URL. Used for ingress."""
        return f"{self._scheme}://{socket.getfqdn()}:{self.config['server-port']}"

    @property
    def external_url(self) -> str:
        """Return the external URL configured, if any."""
        url = self.ingress.url
        if not url:
            logger.warning("No ingress URL configured, returning internal URL")
            return self.internal_url
        return url

    @property
    def external_host(self) -> str:
        """Return the external hostname configured, if any."""
        url = self.ingress.url
        if not url:
            logger.warning("No ingress URL configured, returning internal URL")
            return self.internal_host
        return urlparse(url).hostname or self.internal_host

    @property
    def self_probe(self):
        """The self-monitoring blackbox probe."""
        if not self.external_host:
            return []

        probe = {
            "job_name": "blackbox_http_2xx",
            "params": {"module": ["http_2xx"]},
            "static_configs": [
                {"targets": [self.external_url], "labels": {"name": "foxglove-studio"}}
            ],
        }
        return [probe]

    @property
    def _pebble_layer(self):
        """Return a dictionary representing a Pebble layer."""
        command = " ".join(
            [
                "caddy",
                "file-server",
                "--listen",
                f":{self.config['server-port']}",
                "--root",
                "foxglove",
            ]
        )

        pebble_layer = Layer(
            {
                "summary": "Foxglove-studio k8s layer",
                "description": "Foxglove-studio k8s layer",
                "services": {
                    self.service_name: {
                        "override": "replace",
                        "summary": "foxglove-studio-k8s service",
                        "command": command,
                        "startup": "enabled",
                    }
                },
            }
        )

        return pebble_layer

    @property
    def tracing_endpoint(self) -> Optional[str]:
        """Tempo endpoint for charm tracing."""
        endpoint = None
        if self.tracing_endpoint_requirer.is_ready():
            try:
                endpoint = self.tracing_endpoint_requirer.get_endpoint("otlp_http")
            except ProtocolNotRequestedError as e:
                logger.error(
                    f"Failed to get tracing endpoint with protocol 'otlp_http'.\nError: {e}"
                )
                pass

        return endpoint


if __name__ == "__main__":  # pragma: nocover
    main(FoxgloveStudioCharm)
