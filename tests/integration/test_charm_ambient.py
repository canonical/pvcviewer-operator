#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
from pathlib import Path

import lightkube
import pytest
import yaml
from charmed_kubeflow_chisme.testing import (
    assert_alert_rules,
    assert_logging,
    assert_metrics_endpoint,
    assert_path_reachable_through_ingress,
    assert_security_context,
    deploy_and_assert_grafana_agent,
    deploy_and_integrate_service_mesh_charms,
    generate_container_securitycontext_map,
    get_alert_rules,
    get_pod_names,
)
from lightkube import codecs
from lightkube.generic_resource import create_namespaced_resource
from pytest_operator.plugin import OpsTest
from tenacity import retry, stop_after_delay, wait_fixed

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
CHARM_NAME = METADATA["name"]
CONTAINERS_SECURITY_CONTEXT_MAP = generate_container_securitycontext_map(METADATA)

EXAMPLE_FILE = "./tests/integration/pvcviewer_example/pvcviewer_example.yaml"
EXAMPLE_PATH = "/pvcviewer/kubeflow-user-example-com/pvcviewer-sample/files/"


@pytest.fixture(scope="session")
def lightkube_client() -> lightkube.Client:
    """Returns lightkube Kubernetes client"""
    client = lightkube.Client(field_manager=f"{CHARM_NAME}")
    create_namespaced_resource(
        group="kubeflow.org", version="v1alpha1", kind="PVCViewer", plural="pvcviewers"
    )
    return client


def _safe_load_file_to_text(filename: str):
    """Returns the contents of filename if it is an existing file, else it returns filename."""
    try:
        text = Path(filename).read_text()
    except FileNotFoundError:
        text = filename
    return text


def deploy_example(lightkube_client: lightkube.Client):
    """Creates a PVCViewer example namespace with manifests."""
    yaml_text = _safe_load_file_to_text(EXAMPLE_FILE)

    for obj in codecs.load_all_yaml(yaml_text):
        try:
            lightkube_client.apply(obj)
        except lightkube.core.exceptions.ApiError as e:
            raise e


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """

    charm_under_test = await ops_test.build_charm(".")
    image_path = METADATA["resources"]["oci-image"]["upstream-source"]
    resources = {"oci-image": image_path}
    await ops_test.model.deploy(
        charm_under_test, resources=resources, application_name=CHARM_NAME, trust=True
    )

    await deploy_and_integrate_service_mesh_charms(
        CHARM_NAME,
        ops_test.model,
        relate_to_ingress_route_endpoint=False,
        relate_to_ingress_gateway_endpoint=True,
    )

    await ops_test.model.wait_for_idle(
        apps=[CHARM_NAME], status="active", raise_on_blocked=True, timeout=300
    )
    assert ops_test.model.applications[CHARM_NAME].units[0].workload_status == "active"

    # Deploying grafana-agent-k8s and add all relations
    await deploy_and_assert_grafana_agent(
        ops_test.model, CHARM_NAME, metrics=True, dashboard=True, logging=True
    )


async def test_metrics_endpoint(ops_test):
    """Test metrics_endpoints are defined in relation data bag and their accessibility.

    This function gets all the metrics_endpoints from the relation data bag, checks if
    they are available from the grafana-agent-k8s charm and finally compares them with the
    ones provided to the function.
    """
    app = ops_test.model.applications[CHARM_NAME]
    await assert_metrics_endpoint(app, metrics_port=8080, metrics_path="/metrics")


async def test_logging(ops_test: OpsTest):
    """Test logging is defined in relation data bag."""
    app = ops_test.model.applications[CHARM_NAME]
    await assert_logging(app)


async def test_alert_rules(ops_test: OpsTest):
    """Test check charm alert rules and rules defined in relation data bag."""
    app = ops_test.model.applications[CHARM_NAME]
    alert_rules = get_alert_rules()
    logger.info("found alert_rules: %s", alert_rules)
    await assert_alert_rules(app, alert_rules)


@pytest.mark.abort_on_fail
async def test_pvcviewer_example(ops_test: OpsTest, lightkube_client: lightkube.Client):
    """Deploy pvcviewer crd example with namespace and target PVC.

    Assert on the istio gateway path to pvcviewer is accessible.
    """
    deploy_example(lightkube_client)

    # verify that UI is accessible with retry
    retry_assert_path_reachable = retry(stop=stop_after_delay(120), wait=wait_fixed(10))(
        assert_path_reachable_through_ingress
    )
    await retry_assert_path_reachable(
        http_path=EXAMPLE_PATH,
        namespace=ops_test.model.name,
        expected_response_text="File Browser",
    )


@pytest.mark.parametrize("container_name", list(CONTAINERS_SECURITY_CONTEXT_MAP.keys()))
@pytest.mark.abort_on_fail
async def test_container_security_context(
    ops_test: OpsTest,
    lightkube_client: lightkube.Client,
    container_name: str,
):
    """Test container security context is correctly set.

    Verify that container spec defines the security context with correct
    user ID and group ID.
    """
    pod_name = get_pod_names(ops_test.model.name, CHARM_NAME)[0]
    assert_security_context(
        lightkube_client,
        pod_name,
        container_name,
        CONTAINERS_SECURITY_CONTEXT_MAP,
        ops_test.model.name,
    )
