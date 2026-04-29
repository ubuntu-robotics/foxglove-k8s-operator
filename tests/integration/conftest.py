#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from __future__ import annotations

import os
import pathlib
import subprocess
from collections.abc import Generator
from typing import Any

import jubilant
import pytest
import yaml

from tests.integration.constants import (
    APP_GRAFANA_DASHBOARD,
    APP_LOGGING,
    APP_NAME,
    APP_PROBES,
    APP_TRACING,
    BLACKBOX_APP,
    BLACKBOX_CHANNEL,
    BLACKBOX_CHARM,
    BLACKBOX_PROBES,
    GRAFANA_AGENT_APP,
    GRAFANA_AGENT_CHANNEL,
    GRAFANA_AGENT_CHARM,
    GRAFANA_AGENT_GRAFANA_DASHBOARD,
    GRAFANA_AGENT_LOGGING_PROVIDER,
    GRAFANA_AGENT_TRACING_PROVIDER,
    RESOURCE_NAME,
)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@pytest.fixture(scope="module")
def juju(request: pytest.FixtureRequest) -> Generator[jubilant.Juju, None, None]:
    """Pytest fixture wrapping Jubilant model lifecycle."""

    def show_debug_log(current_juju: jubilant.Juju):
        if request.session.testsfailed:
            print(current_juju.debug_log(limit=1000), end="")

    use_existing = _env_flag("JUJU_USE_EXISTING", default=False)
    if use_existing:
        current_juju = jubilant.Juju()
        yield current_juju
        show_debug_log(current_juju)
        return

    model = os.environ.get("JUJU_MODEL")
    if model:
        current_juju = jubilant.Juju(model=model)
        yield current_juju
        show_debug_log(current_juju)
        return

    keep_models = _env_flag("JUJU_KEEP_MODELS", default=False)
    with jubilant.temp_model(keep=keep_models) as current_juju:
        current_juju.wait_timeout = 10 * 60
        yield current_juju
        show_debug_log(current_juju)


@pytest.fixture(scope="session")
def metadata() -> dict[str, Any]:
    """Provides charm metadata."""
    return yaml.safe_load(pathlib.Path("./charmcraft.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def charm_file(metadata: dict[str, Any]) -> str:
    """Pack charm and return filename, or use CHARM_FILE if set."""
    charm_file_env = os.environ.get("CHARM_FILE")
    if charm_file_env:
        return charm_file_env

    try:
        pack_cmd = ["charmcraft", "pack"]
        subprocess.run(pack_cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise OSError(f"Error packing charm: {exc}; stderr:\n{exc.stderr}") from None

    app_name = metadata["name"]
    repo_root = pathlib.Path(__file__).parent.parent.parent
    charms = [path.absolute() for path in repo_root.glob(f"{app_name}_*.charm")]
    assert charms, f"{app_name} .charm file not found"
    assert len(charms) == 1, f"{app_name} has more than one .charm file, unsure which to use"
    return str(charms[0])


@pytest.fixture(scope="module", autouse=True)
def app_fixture(juju: jubilant.Juju, metadata: dict[str, Any], charm_file: str) -> str:
    """Builds and deploys the charm and its required relations/resources."""
    charm_oci_image = metadata["resources"][RESOURCE_NAME]["upstream-source"]

    juju.deploy(
        charm=charm_file,
        app=APP_NAME,
        resources={RESOURCE_NAME: charm_oci_image},
    )
    juju.deploy(
        GRAFANA_AGENT_CHARM,
        app=GRAFANA_AGENT_APP,
        channel=GRAFANA_AGENT_CHANNEL,
    )
    juju.deploy(BLACKBOX_CHARM, app=BLACKBOX_APP, channel=BLACKBOX_CHANNEL, trust=True)

    juju.integrate(
        f"{APP_NAME}:{APP_GRAFANA_DASHBOARD}",
        f"{GRAFANA_AGENT_APP}:{GRAFANA_AGENT_GRAFANA_DASHBOARD}",
    )
    juju.integrate(
        f"{APP_NAME}:{APP_LOGGING}", f"{GRAFANA_AGENT_APP}:{GRAFANA_AGENT_LOGGING_PROVIDER}"
    )
    juju.integrate(
        f"{APP_NAME}:{APP_TRACING}", f"{GRAFANA_AGENT_APP}:{GRAFANA_AGENT_TRACING_PROVIDER}"
    )
    juju.integrate(f"{APP_NAME}:{APP_PROBES}", f"{BLACKBOX_APP}:{BLACKBOX_PROBES}")

    juju.wait(lambda status: jubilant.all_active(status, APP_NAME, BLACKBOX_APP), timeout=15 * 60)

    # grafana_agent_app is
    # in a blocked state by design.
    juju.wait(lambda status: jubilant.all_blocked(status, GRAFANA_AGENT_APP), timeout=15 * 60)
    return APP_NAME
