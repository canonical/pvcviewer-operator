# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, patch

import pytest
from ops.model import ActiveStatus
from ops.testing import Harness

from charm import PvcViewer


@pytest.fixture
def harness() -> Harness:
    harness = Harness(PvcViewer)
    return harness


@pytest.fixture()
def mocked_lightkube_client(mocker):
    """Mocks the Lightkube Client in charm.py, returning a mock instead."""
    mocked_lightkube_client = MagicMock()
    mocker.patch("charm.lightkube.Client", return_value=mocked_lightkube_client)
    yield mocked_lightkube_client


@pytest.fixture()
def mocked_kubernetes_service_patch(mocker):
    """Mocks the KubernetesServicePatch for the charm."""
    mocked_kubernetes_service_patch = mocker.patch(
        "charm.KubernetesServicePatch", lambda x, y, service_name: None
    )
    yield mocked_kubernetes_service_patch


def test_metrics(harness, mocked_lightkube_client, mocked_kubernetes_service_patch):
    """Test MetricsEndpointProvider initialization."""
    with patch("charm.MetricsEndpointProvider") as mock_metrics:
        harness.begin()
        mock_metrics.assert_called_once_with(
            charm=harness.charm,
            jobs=[{"static_configs": [{"targets": ["*:8080"]}]}],
        )


def test_grafana_dashboard(harness, mocked_lightkube_client, mocked_kubernetes_service_patch):
    """Test GrafanaDashboardProvider initialization."""
    with patch("charm.GrafanaDashboardProvider") as mock_grafana:
        harness.begin()
        mock_grafana.assert_called_once_with(harness.charm)


def test_log_forwarding(harness, mocked_lightkube_client, mocked_kubernetes_service_patch):
    """Test LogForwarder initialization."""
    with patch("charm.LogForwarder") as mock_logging:
        harness.begin()
        mock_logging.assert_called_once_with(charm=harness.charm)


def test_not_leader(harness, mocked_lightkube_client, mocked_kubernetes_service_patch):
    """Test when we are not the leader."""
    harness.begin_with_initial_hooks()
    # Assert that we are not Active, and that the leadership-gate is the cause.
    assert not isinstance(harness.charm.model.unit.status, ActiveStatus)
    assert harness.charm.model.unit.status.message.startswith("[leadership-gate]")


def test_kubernetes_created_method(
    harness, mocked_lightkube_client, mocked_kubernetes_service_patch
):
    """Test whether we try to create Kubernetes resources when we have leadership."""
    # Arrange
    # Needed because kubernetes component will only apply to k8s if we are the leader
    harness.set_leader(True)
    harness.begin()

    # Need to mock the leadership-gate to be active, and the kubernetes auth component so that it
    # sees the expected resources when calling _get_missing_kubernetes_resources

    harness.charm.leadership_gate.get_status = MagicMock(return_value=ActiveStatus())

    harness.charm.kubernetes_resources.component._get_missing_kubernetes_resources = MagicMock(
        return_value=[]
    )

    # Act
    harness.charm.on.install.emit()

    # Assert
    assert mocked_lightkube_client.apply.call_count == 13
    assert isinstance(harness.charm.kubernetes_resources.status, ActiveStatus)


def test_pebble_services_running(
    harness, mocked_lightkube_client, mocked_kubernetes_service_patch
):
    """Test that if the Kubernetes Component is Active, the pebble services successfully start."""
    # Arrange
    harness.begin()
    harness.set_can_connect("pvcviewer-operator", True)

    # Mock:
    # * leadership_gate to have get_status=>Active
    # * object_storage_relation to return mock data, making the item go active
    # * kubernetes_resources to have get_status=>Active
    harness.charm.leadership_gate.get_status = MagicMock(return_value=ActiveStatus())
    harness.charm.kubernetes_resources.get_status = MagicMock(return_value=ActiveStatus())

    # Act
    harness.charm.on.install.emit()

    # Assert
    container = harness.charm.unit.get_container("pvcviewer-operator")
    service = container.get_service("pvcviewer-operator")
    assert service.is_running()


def test_get_certs(harness, mocked_lightkube_client, mocked_kubernetes_service_patch):
    """Test certs generated on init."""
    # Act
    harness.begin()

    # Assert
    cert_attributes = ["cert", "ca", "key"]

    # Certs should be available
    for attr in cert_attributes:
        assert hasattr(harness.charm._stored, attr)
