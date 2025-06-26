#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from charmed_kubeflow_chisme.testing import (
    GRAFANA_AGENT_APP,
    assert_grafana_dashboards,
    assert_logging,
    deploy_and_assert_grafana_agent,
    get_grafana_dashboards,
)
from charmed_kubeflow_chisme.testing.cos_integration import (
    PROVIDES,
    _get_app_relation_data,
    _get_unit_relation_data,
)
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
APP_NAME = METADATA["name"]
RESOURCE_NAME = "foxglove-studio-image"
RESOURCE_PATH = METADATA["resources"][RESOURCE_NAME]["upstream-source"]


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    # Build and deploy charm from local source folder
    charm = await ops_test.build_charm(".")
    resources = {RESOURCE_NAME: RESOURCE_PATH}

    # Deploy the charm and wait for active/idle status
    await asyncio.gather(
        ops_test.model.deploy(charm, resources=resources, application_name=APP_NAME),
        ops_test.model.wait_for_idle(
            apps=[APP_NAME], status="active", raise_on_blocked=True, timeout=1000
        ),
    )

    # Deploying grafana-agent-k8s and add the logging relation
    await deploy_and_assert_grafana_agent(
        ops_test.model, APP_NAME, channel="1/stable", metrics=False, dashboard=True, logging=True
    )

    logger.info(
        "Adding relation: %s:%s and %s:%s",
        APP_NAME,
        "tracing",
        GRAFANA_AGENT_APP,
        "tracing-provider",
    )
    await ops_test.model.integrate(f"{APP_NAME}:tracing", f"{GRAFANA_AGENT_APP}:tracing-provider")


async def test_status(ops_test):
    """Assert on the unit status."""
    assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"


async def test_logging(ops_test: OpsTest):
    """Test logging is defined in relation data bag."""
    app = ops_test.model.applications[APP_NAME]
    await assert_logging(app)


async def test_grafana_dashboards(ops_test: OpsTest):
    """Test Grafana dashboards are defined in relation data bag."""
    app = ops_test.model.applications[APP_NAME]
    dashboards = get_grafana_dashboards()
    logger.info("found dashboards: %s", dashboards)
    await assert_grafana_dashboards(app, dashboards)


async def test_tracing(ops_test: OpsTest):
    """Test logging is defined in relation data bag."""
    app = ops_test.model.applications[APP_NAME]

    unit_relation_data = await _get_unit_relation_data(app, "tracing", side=PROVIDES)

    assert unit_relation_data


async def test_integrate_blackbox(ops_test: OpsTest):
    await ops_test.model.deploy(
        "blackbox-exporter-k8s", "blackbox", channel="1/edge", trust=True
    )

    logger.info(
        "Adding relation: %s:%s",
        APP_NAME,
        "probes",
    )

    await ops_test.model.integrate(
        f"{APP_NAME}",
        "blackbox:probes",
    )

    await ops_test.model.wait_for_idle(
        apps=[
            f"{APP_NAME}",
            "blackbox",
        ],
        status="active",
    )


async def test_blackbox(ops_test: OpsTest):
    """Test probes are defined in relation data bag."""
    app = ops_test.model.applications[APP_NAME]

    relation_data = await _get_app_relation_data(app, "probes", side=PROVIDES)

    assert relation_data.get("scrape_metadata")
    assert relation_data.get("scrape_probes")
