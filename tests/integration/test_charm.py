#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
from pathlib import Path

import aiohttp
import lightkube
import pytest
import yaml
from charmed_kubeflow_chisme.testing import (
    assert_alert_rules,
    assert_logging,
    assert_metrics_endpoint,
    deploy_and_assert_grafana_agent,
    get_alert_rules,
)
from charms_dependencies import ISTIO_GATEWAY, ISTIO_PILOT
from lightkube import codecs
from lightkube.generic_resource import create_namespaced_resource
from lightkube.resources.core_v1 import Service
from pytest_operator.plugin import OpsTest
from tenacity import retry, stop_after_delay, wait_fixed

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
CHARM_NAME = METADATA["name"]

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


def get_ingress_url(lightkube_client: lightkube.Client, model_name: str):
    """Returns url of ingress gateway in the cluster"""
    gateway_svc = lightkube_client.get(
        Service, "istio-ingressgateway-workload", namespace=model_name
    )
    ingress_record = gateway_svc.status.loadBalancer.ingress[0]
    if ingress_record.ip:
        public_url = f"http://{ingress_record.ip}.nip.io"
    if ingress_record.hostname:
        public_url = f"http://{ingress_record.hostname}"  # Use hostname (e.g. EKS)
    return public_url


async def fetch_response(url, headers):
    """Fetch provided URL and return pair - status and text (int, string)."""
    result_status = 0
    result_text = ""
    async with aiohttp.ClientSession() as session:
        async with session.get(url=url, headers=headers) as response:
            result_status = response.status
            result_text = await response.text()
    return result_status, str(result_text)


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """

    # Deploy istio-operators for ingress configuration
    await ops_test.model.deploy(
        ISTIO_PILOT.charm,
        channel=ISTIO_PILOT.channel,
        config=ISTIO_PILOT.config,
        trust=ISTIO_PILOT.trust,
    )

    await ops_test.model.deploy(
        ISTIO_GATEWAY.charm,
        channel=ISTIO_GATEWAY.channel,
        config=ISTIO_GATEWAY.config,
        trust=ISTIO_GATEWAY.trust,
    )
    await ops_test.model.integrate(ISTIO_PILOT.charm, ISTIO_GATEWAY.charm)
    await ops_test.model.wait_for_idle(
        [ISTIO_PILOT.charm, ISTIO_GATEWAY.charm],
        raise_on_blocked=False,
        status="active",
        timeout=900,
    )

    charm_under_test = await ops_test.build_charm(".")
    image_path = METADATA["resources"]["oci-image"]["upstream-source"]
    resources = {"oci-image": image_path}
    await ops_test.model.deploy(
        charm_under_test, resources=resources, application_name=CHARM_NAME, trust=True
    )
    await ops_test.model.wait_for_idle(
        apps=[CHARM_NAME], status="active", raise_on_blocked=True, timeout=300
    )
    assert ops_test.model.applications[CHARM_NAME].units[0].workload_status == "active"

    # Deploying grafana-agent-k8s and add all relations
    await deploy_and_assert_grafana_agent(
        ops_test.model, CHARM_NAME, metrics=True, dashboard=True, logging=True
    )


async def test_metrics_enpoint(ops_test):
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


@retry(stop=stop_after_delay(600), wait=wait_fixed(10))
@pytest.mark.abort_on_fail
async def test_pvcviewer_example(ops_test: OpsTest, lightkube_client: lightkube.Client):
    """Deploy pvcviewer crd example with namespace and target PVC.

    Assert on the istio gateway path to pvcviewer is accessible.
    """
    deploy_example(lightkube_client)
    ingress_url = get_ingress_url(lightkube_client, ops_test.model_name)
    result_status, result_text = await fetch_response(f"{ingress_url}{EXAMPLE_PATH}", {})

    # verify that UI is accessible
    assert result_status == 200
    assert len(result_text) > 0


@pytest.mark.abort_on_fail
async def test_remove_deletes_virtual_service(
    ops_test: OpsTest, lightkube_client: lightkube.Client
):
    """Remove pvcviewer charm.

    Assert virtual service is no longer accessible.
    """
    await ops_test.model.remove_application(CHARM_NAME, block_until_done=True)

    ingress_url = get_ingress_url(lightkube_client, ops_test.model_name)
    result_status, _ = await fetch_response(f"{ingress_url}{EXAMPLE_PATH}", {})

    # verify that UI is accessible
    assert result_status == 404
