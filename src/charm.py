#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  Copyright 2023 Canonical Ltd.
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

from ops.charm import (
    CharmBase,
    HookEvent,
    RelationJoinedEvent,
)

from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, OpenedPort, WaitingStatus
from ops.pebble import Layer

import logging
from pathlib import Path
import subprocess

from charms.observability_libs.v0.cert_handler import CertHandler
from charms.traefik_route_k8s.v0.traefik_route import TraefikRouteRequirer
from charms.catalogue_k8s.v0.catalogue import CatalogueConsumer, CatalogueItem
import socket

logger = logging.getLogger()


class FoxgloveStudioCharm(CharmBase):
    """Charm to run Foxglove studio on Kubernetes."""

    def __init__(self, *args):
        super().__init__(*args)
        self.name = "foxglove-studio"

        self.container = self.unit.get_container(self.name)

        # -- cert_handler
        self.cert_handler = CertHandler(
            charm=self,
            key="foxglove-studio-server-cert",
            peer_relation_name="replicas",
            extra_sans_dns=[socket.getfqdn()],
        )

        # -- ingress via raw traefik_route
        self.ingress = TraefikRouteRequirer(self, self.model.get_relation("ingress"), "ingress")  # type: ignore
        self.framework.observe(self.on["ingress"].relation_joined, self._configure_ingress)
        self.framework.observe(self.ingress.on.ready, self._on_ingress_ready)
        self.framework.observe(self.on.leader_elected, self._configure_ingress)
        self.framework.observe(self.on.config_changed, self._configure_ingress)
        self.framework.observe(self.cert_handler.on.cert_changed, self._configure_ingress)

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
                name="Foxglove-studio",
                icon="bar-chart",
                url=self.external_url,
                description=("Foxglove-studio allows you to robotics data"),
            ),
        )

        # -- cert_handler observations
        self.framework.observe(
            self.cert_handler.on.cert_changed, self._on_server_cert_changed  # pyright: ignore
        )

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
        self._update_layer_and_restart(None)

    def _on_ingress_ready(self, _) -> None:
        """Once Traefik tells us our external URL, make sure we reconfigure Foxglove Studio."""
        self._update_layer_and_restart(None)

    def _configure_ingress(self, event: HookEvent) -> None:
        """Set up ingress if a relation is joined, config changed, or a new leader election."""
        if not self.unit.is_leader():
            return

        # If it's a RelationJoinedEvent, set it in the ingress object
        if isinstance(event, RelationJoinedEvent):
            self.ingress._relation = event.relation

        # No matter what, check readiness -- this blindly checks whether `ingress._relation` is not
        # None, so it overlaps a little with the above, but works as expected on leader elections
        # and config-change
        if self.ingress.is_ready():
            self._update_layer_and_restart(None)
            self.ingress.submit_to_traefik(self._ingress_config)

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

                self.container.restart(self.name)
                logger.info(f"Restarted '{self.name}' service")
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
        return "https" if self.cert_handler.cert else "http"

    @property
    def internal_url(self) -> str:
        """Return workload's internal URL. Used for ingress."""
        return f"{self._scheme}://{socket.getfqdn()}:{self.config['server-port']}"

    @property
    def external_url(self) -> str:
        """Return the external hostname configured, if any."""
        if self.ingress.external_host:
            path_prefix = f"{self.model.name}-{self.model.app.name}"
            return f"{self._scheme}://{self.ingress.external_host}/{path_prefix}"
        return self.internal_url

    @property
    def _ingress_config(self) -> dict:
        """Build a raw ingress configuration for Traefik."""
        # The path prefix is the same as in ingress per app
        external_path = f"{self.model.name}-{self.model.app.name}"

        redirect_middleware = (
            {
                f"juju-sidecar-redir-https-{self.model.name}-{self.model.app.name}": {
                    "redirectScheme": {
                        "permanent": True,
                        "port": 443,
                        "scheme": "https",
                    }
                }
            }
            if self._scheme == "https"
            else {}
        )

        middlewares = {
            f"juju-sidecar-trailing-slash-handler-{self.model.name}-{self.model.app.name}": {
                "redirectRegex": {
                    "regex": [f"^(.*)\\/{external_path}$"],
                    "replacement": [f"/{external_path}/"],
                    "permanent": True,
                }
            },
            f"juju-sidecar-noprefix-{self.model.name}-{self.model.app.name}": {
                "stripPrefix": {"forceSlash": False, "prefixes": [f"/{external_path}"]},
            },
            **redirect_middleware,
        }

        routers = {
            "juju-{}-{}-router".format(self.model.name, self.model.app.name): {
                "entryPoints": ["web"],
                "rule": f"PathPrefix(`/{external_path}`)",
                "middlewares": list(middlewares.keys()),
                "service": "juju-{}-{}-service".format(self.model.name, self.app.name),
            },
            "juju-{}-{}-router-tls".format(self.model.name, self.model.app.name): {
                "entryPoints": ["websecure"],
                "rule": f"PathPrefix(`/{external_path}`)",
                "middlewares": list(middlewares.keys()),
                "service": "juju-{}-{}-service".format(self.model.name, self.app.name),
                "tls": {
                    "domains": [
                        {
                            "main": self.ingress.external_host,
                            "sans": [f"*.{self.ingress.external_host}"],
                        },
                    ],
                },
            },
        }

        services = {
            "juju-{}-{}-service".format(self.model.name, self.model.app.name): {
                "loadBalancer": {"servers": [{"url": self.internal_url}]}
            }
        }

        return {"http": {"routers": routers, "services": services, "middlewares": middlewares}}

    @property
    def _pebble_layer(self):
        """Return a dictionary representing a Pebble layer."""
        command = " ".join(
            [
                "caddy",
                "file-server",
                "--listen",
                f":{self.config['server-port']}"
            ]
        )
        if self._scheme == "https":
            command = " ".join(
            [
                "caddy",
                "file-server",
                "--listen",
                f":{self.config['server-port']}",
                "-key /etc/caddy/foxglove.key -cert /etc/caddy/foxglove.crt",
            ]
        )

        pebble_layer = Layer(
            {
                "summary": "Foxglove-studio k8s layer",
                "description": "Foxglove-studio k8s layer",
                "services": {
                    self.name: {
                        "override": "replace",
                        "summary": "foxglove-studio-k8s service",
                        "command": command,
                        "startup": "enabled",
                    }
                },
            }
        )

        return pebble_layer

    def _on_server_cert_changed(self, _):
        self._update_cert()
        self._update_layer_and_restart()

    def _update_cert(self):
        container = self.containers["workload"]
        ca_cert_path = Path("/usr/local/share/ca-certificates/cos-ca.crt")
        if self.cert_handler.cert and self.cert_handler.key and self.cert_handler.ca:
            # Save the workload certificates
            container.push(
                "/etc/caddy/foxglove.crt",
                self.cert_handler.cert,
                make_dirs=True,
            )
            container.push(
                "/etc/caddy/foxglove.key",
                self.cert_handler.key,
                make_dirs=True,
            )
            # Save the CA among the trusted CAs and trust it
            container.push(
                ca_cert_path,
                self.cert_handler.ca,
                make_dirs=True,
            )

            # Repeat for the charm container. We need it there for grafana client requests.
            ca_cert_path.parent.mkdir(exist_ok=True, parents=True)
            ca_cert_path.write_text(self.cert_handler.ca)
        else:
            container.remove_path("/etc/caddy/foxglove.crt", recursive=True)
            container.remove_path("/etc/caddy/foxglove.key", recursive=True)
            container.remove_path(ca_cert_path, recursive=True)
            # Repeat for the charm container.
            ca_cert_path.unlink(missing_ok=True)

if __name__ == "__main__":  # pragma: nocover
    main(FoxgloveStudioCharm)
