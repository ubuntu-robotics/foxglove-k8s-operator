#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import pathlib

import yaml

METADATA = yaml.safe_load(pathlib.Path("./charmcraft.yaml").read_text(encoding="utf-8"))
APP_NAME = METADATA["name"]
RESOURCE_NAME = "foxglove-studio-image"

GRAFANA_AGENT_APP = "grafana-agent"
GRAFANA_AGENT_CHARM = "grafana-agent-k8s"
GRAFANA_AGENT_CHANNEL = "1/stable"
GRAFANA_AGENT_GRAFANA_DASHBOARD = "grafana-dashboards-consumer"
GRAFANA_AGENT_LOGGING_PROVIDER = "logging-provider"
GRAFANA_AGENT_TRACING_PROVIDER = "tracing-provider"

BLACKBOX_APP = "blackbox"
BLACKBOX_CHARM = "blackbox-exporter-k8s"
BLACKBOX_CHANNEL = "1/stable"
BLACKBOX_PROBES = "probes"

APP_GRAFANA_DASHBOARD = "grafana-dashboard"
APP_LOGGING = "logging"
APP_TRACING = "tracing"
APP_PROBES = "probes"
