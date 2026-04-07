#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import jubilant

from tests.integration.constants import (
    APP_GRAFANA_DASHBOARD,
    APP_LOGGING,
    APP_NAME,
    APP_PROBES,
    APP_TRACING,
    BLACKBOX_APP,
    BLACKBOX_PROBES,
    GRAFANA_AGENT_APP,
    GRAFANA_AGENT_GRAFANA_DASHBOARD,
    GRAFANA_AGENT_LOGGING_PROVIDER,
    GRAFANA_AGENT_TRACING_PROVIDER,
)
from tests.integration.juju import relation_application_data

logger = logging.getLogger(__name__)


def wait_for_active_idle_without_error(juju: jubilant.Juju, timeout: int = 60 * 45):
    """Wait for the model to settle without errors."""
    logger.info(f"waiting for the model ({juju.model}) to settle ...")
    # grafana_agent_app stays in blocked state by design
    juju.wait(
        ready=lambda status: jubilant.all_active(status, APP_NAME, BLACKBOX_APP),
        delay=10,
        timeout=timeout,
        error=jubilant.any_error,
    )
    logger.info("waiting for agents idle ...")
    juju.wait(
        jubilant.all_agents_idle,
        delay=10,
        timeout=timeout,
        error=lambda status: jubilant.any_error(status, APP_NAME, BLACKBOX_APP),
    )


def test_deploy(juju):
    """Assert deployment of charm-under-test reaches active status."""
    wait_for_active_idle_without_error(juju)


def test_logging(juju):
    """Test logging relation data bag is populated."""
    app_unit = f"{APP_NAME}/0"
    agent_unit = f"{GRAFANA_AGENT_APP}/0"
    relation_data = relation_application_data(
        juju,
        app_unit,
        APP_LOGGING,
        agent_unit,
        GRAFANA_AGENT_LOGGING_PROVIDER,
    )
    assert relation_data


def test_grafana_dashboards(juju):
    """Test Grafana dashboards are defined in relation data bag."""
    app_unit = f"{APP_NAME}/0"
    agent_unit = f"{GRAFANA_AGENT_APP}/0"
    relation_data = relation_application_data(
        juju,
        agent_unit,
        GRAFANA_AGENT_GRAFANA_DASHBOARD,
        app_unit,
        APP_GRAFANA_DASHBOARD,
    )
    assert relation_data
    assert relation_data[0].get("dashboards")


def test_tracing(juju):
    """Test tracing relation data bag is populated."""
    app_unit = f"{APP_NAME}/0"
    agent_unit = f"{GRAFANA_AGENT_APP}/0"
    relation_data = relation_application_data(
        juju,
        app_unit,
        APP_TRACING,
        agent_unit,
        GRAFANA_AGENT_TRACING_PROVIDER,
    )
    assert relation_data


def test_blackbox(juju):
    """Test probes are defined in relation data bag."""
    app_unit = f"{APP_NAME}/0"
    blackbox_unit = f"{BLACKBOX_APP}/0"
    relation_data = relation_application_data(
        juju,
        blackbox_unit,
        BLACKBOX_PROBES,
        app_unit,
        APP_PROBES,
    )
    assert relation_data
    assert relation_data[0].get("scrape_metadata")
    assert relation_data[0].get("scrape_probes")
