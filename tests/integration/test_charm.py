#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
from pathlib import Path

import aiohttp
import lightkube
import pytest
import yaml
from lightkube import codecs
from lightkube.generic_resource import create_namespaced_resource
from lightkube.resources.core_v1 import Service
from pytest_operator.plugin import OpsTest
from tenacity import retry, stop_after_delay, wait_fixed

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
CHARM_NAME = METADATA["name"]

ISTIO_GATEWAY_CHARM_NAME = "istio-gateway"
ISTIO_PILOT_CHARM_NAME = "istio-pilot"
ISTIO_PILOT_VERSION = "1.16/stable"
ISTIO_GATEWAY_VERSION = "1.16/stable"
ISTIO_GATEWAY_NAME = "kubeflow-gateway"
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
        ISTIO_PILOT_CHARM_NAME,
        channel=ISTIO_PILOT_VERSION,
        config={"default-gateway": ISTIO_GATEWAY_NAME},
        trust=True,
    )

    await ops_test.model.deploy(
        ISTIO_GATEWAY_CHARM_NAME,
        channel=ISTIO_GATEWAY_VERSION,
        config={"kind": "ingress"},
        trust=True,
    )
    await ops_test.model.add_relation(ISTIO_PILOT_CHARM_NAME, ISTIO_GATEWAY_CHARM_NAME)
    await ops_test.model.wait_for_idle(
        [ISTIO_PILOT_CHARM_NAME, ISTIO_GATEWAY_CHARM_NAME],
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
