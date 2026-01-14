# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, Mock, patch

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
    """Mocks the Lightkube Client in charm.py and service_mesh_component.py, returning a mock."""
    mocked_lightkube_client = MagicMock()
    mocker.patch("charm.lightkube.Client", return_value=mocked_lightkube_client)
    mocker.patch("components.service_mesh_component.Client", return_value=mocked_lightkube_client)
    yield mocked_lightkube_client


@pytest.fixture()
def mocked_kubernetes_service_patch(mocker):
    """Mocks the KubernetesServicePatch for the charm."""
    mocked_kubernetes_service_patch = mocker.patch(
        "charm.KubernetesServicePatch", lambda x, y, service_name: None
    )
    yield mocked_kubernetes_service_patch


@pytest.fixture()
def mocked_service_mesh_component(mocker):
    """Mocks the ServiceMeshComponent for the charm."""
    mock = mocker.patch("charm.ServiceMeshComponent")
    mock_instance = MagicMock()
    mock_instance.is_ambient_mesh_enabled.return_value = False
    mock_instance.get_gateway_name.return_value = "kubeflow-gateway"
    mock_instance.get_gateway_namespace.return_value = "kubeflow"
    mock_instance.get_status.return_value = ActiveStatus()
    mock_instance.name = "service-mesh"
    mock_instance.status = ActiveStatus()
    mock.return_value = mock_instance
    yield mock


def test_metrics(
    harness,
    mocked_lightkube_client,
    mocked_kubernetes_service_patch,
    mocked_service_mesh_component,
):
    """Test MetricsEndpointProvider initialization."""
    with patch("charm.MetricsEndpointProvider") as mock_metrics:
        harness.begin()
        mock_metrics.assert_called_once_with(
            charm=harness.charm,
            jobs=[{"static_configs": [{"targets": ["*:8080"]}]}],
        )


def test_grafana_dashboard(
    harness,
    mocked_lightkube_client,
    mocked_kubernetes_service_patch,
    mocked_service_mesh_component,
):
    """Test GrafanaDashboardProvider initialization."""
    with patch("charm.GrafanaDashboardProvider") as mock_grafana:
        harness.begin()
        mock_grafana.assert_called_once_with(harness.charm)


def test_log_forwarding(
    harness,
    mocked_lightkube_client,
    mocked_kubernetes_service_patch,
    mocked_service_mesh_component,
):
    """Test LogForwarder initialization."""
    with patch("charm.LogForwarder") as mock_logging:
        harness.begin()
        mock_logging.assert_called_once_with(charm=harness.charm)


def test_not_leader(
    harness,
    mocked_lightkube_client,
    mocked_kubernetes_service_patch,
    mocked_service_mesh_component,
):
    """Test when we are not the leader."""
    harness.begin_with_initial_hooks()
    # Assert that we are not Active, and that the leadership-gate is the cause.
    assert not isinstance(harness.charm.model.unit.status, ActiveStatus)
    assert harness.charm.model.unit.status.message.startswith("[leadership-gate]")


def test_kubernetes_created_method(
    harness,
    mocked_lightkube_client,
    mocked_kubernetes_service_patch,
    mocked_service_mesh_component,
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
    harness,
    mocked_lightkube_client,
    mocked_kubernetes_service_patch,
    mocked_service_mesh_component,
):
    """Test that if the Kubernetes Component is Active, the pebble services successfully start."""
    # Arrange
    harness.begin()
    harness.set_can_connect("pvcviewer-operator", True)

    # Mock:
    # * leadership_gate to have get_status=>Active
    # * object_storage_relation to return mock data, making the item go active
    # * kubernetes_resources to have get_status=>Active
    # * service_mesh to have get_status=>Active
    harness.charm.leadership_gate.get_status = MagicMock(return_value=ActiveStatus())
    harness.charm.kubernetes_resources.get_status = MagicMock(return_value=ActiveStatus())
    harness.charm.service_mesh.get_status = MagicMock(return_value=ActiveStatus())

    # Act
    harness.charm.on.install.emit()

    # Assert
    container = harness.charm.unit.get_container("pvcviewer-operator")
    service = container.get_service("pvcviewer-operator")
    assert service.is_running()


def test_get_certs(
    harness,
    mocked_lightkube_client,
    mocked_kubernetes_service_patch,
    mocked_service_mesh_component,
):
    """Test certs generated on init."""
    # Act
    harness.begin()

    # Assert
    cert_attributes = ["cert", "ca", "key"]

    # Certs should be available
    for attr in cert_attributes:
        assert hasattr(harness.charm._stored, attr)


@pytest.mark.parametrize(
    "has_relation,expected_ambient,expected_gateway_name,expected_gateway_namespace",
    [
        (False, False, "kubeflow-gateway", "kubeflow"),  # sidecar mode
        (True, True, "istio-gateway", "istio-system"),  # ambient mode
    ],
)
def test_service_mesh_component_modes(
    harness,
    mocked_lightkube_client,
    mocked_kubernetes_service_patch,
    has_relation,
    expected_ambient,
    expected_gateway_name,
    expected_gateway_namespace,
):
    """Test ServiceMeshComponent in different modes (sidecar vs ambient)."""
    # Arrange
    harness.set_leader(True)
    harness.begin()

    # Mock components to be active
    harness.charm.leadership_gate.get_status = MagicMock(return_value=ActiveStatus())
    harness.charm.kubernetes_resources.get_status = MagicMock(return_value=ActiveStatus())

    if has_relation:
        # Add gateway-metadata relation for ambient mode
        relation_id = harness.add_relation("gateway-metadata", "istio-beacon")
        harness.add_relation_unit(relation_id, "istio-beacon/0")

        # Mock the gateway metadata
        mock_metadata = Mock()
        mock_metadata.namespace = expected_gateway_namespace
        mock_metadata.gateway_name = expected_gateway_name

        harness.charm.service_mesh.component._gateway_metadata_requirer.get_metadata = MagicMock(
            return_value=mock_metadata
        )

    # Act
    is_ambient = harness.charm.service_mesh.component.is_ambient_mesh_enabled()
    gateway_name = harness.charm.service_mesh.component.get_gateway_name()
    gateway_namespace = harness.charm.service_mesh.component.get_gateway_namespace()

    # Assert
    assert is_ambient is expected_ambient
    assert gateway_name == expected_gateway_name
    assert gateway_namespace == expected_gateway_namespace


@pytest.mark.parametrize(
    "is_ambient,gateway_name,gateway_namespace,expected_use_istio,expected_use_gateway_api",
    [
        (False, "kubeflow-gateway", "kubeflow", "true", "false"),  # sidecar mode
        (True, "istio-gateway", "istio-system", "false", "true"),  # ambient mode
    ],
)
def test_pebble_layer_environment(
    harness,
    mocked_lightkube_client,
    mocked_kubernetes_service_patch,
    mocked_service_mesh_component,
    is_ambient,
    gateway_name,
    gateway_namespace,
    expected_use_istio,
    expected_use_gateway_api,
):
    """Test that pebble layer contains correct environment variables for different mesh modes."""
    # Arrange
    harness.set_leader(True)
    harness.begin()
    harness.set_can_connect("pvcviewer-operator", True)

    # Mock components
    harness.charm.leadership_gate.get_status = MagicMock(return_value=ActiveStatus())
    harness.charm.kubernetes_resources.get_status = MagicMock(return_value=ActiveStatus())
    harness.charm.service_mesh.get_status = MagicMock(return_value=ActiveStatus())

    # Mock mesh mode
    harness.charm.service_mesh.component.is_ambient_mesh_enabled = MagicMock(
        return_value=is_ambient
    )
    harness.charm.service_mesh.component.get_gateway_name = MagicMock(return_value=gateway_name)
    harness.charm.service_mesh.component.get_gateway_namespace = MagicMock(
        return_value=gateway_namespace
    )

    # Act
    harness.charm.on.install.emit()

    # Assert
    container = harness.charm.unit.get_container("pvcviewer-operator")
    plan = container.get_plan()

    env = plan.services["pvcviewer-operator"].environment
    assert env["USE_ISTIO"] == expected_use_istio
    assert env["USE_GATEWAY_API"] == expected_use_gateway_api
    assert env["K8S_GATEWAY_NAME"] == gateway_name
    assert env["K8S_GATEWAY_NAMESPACE"] == gateway_namespace


def test_service_mesh_blocked_status(
    harness, mocked_lightkube_client, mocked_kubernetes_service_patch
):
    """Test BlockedStatus with service-mesh relation without gateway-metadata relation."""
    # Arrange
    harness.set_leader(True)
    harness.begin()

    # Add only service-mesh relation
    harness.add_relation("service-mesh", "istio-beacon")

    # Act
    status = harness.charm.service_mesh.component.get_status()

    # Assert
    from ops import BlockedStatus

    assert isinstance(status, BlockedStatus)
    assert "Service mesh relation present without gateway metadata relation" in status.message


def test_service_mesh_waiting_status(
    harness, mocked_lightkube_client, mocked_kubernetes_service_patch
):
    """Test that service mesh component returns WaitingStatus when data is not ready."""
    # Arrange
    harness.set_leader(True)
    harness.begin()

    # Add gateway-metadata relation
    relation_id = harness.add_relation("gateway-metadata", "istio-beacon")
    harness.add_relation_unit(relation_id, "istio-beacon/0")

    # Mock the gateway metadata to return None (data not ready)
    harness.charm.service_mesh.component._gateway_metadata_requirer.get_metadata = MagicMock(
        return_value=None
    )

    # Act
    status = harness.charm.service_mesh.component.get_status()

    # Assert
    from ops import WaitingStatus

    assert isinstance(status, WaitingStatus)
    assert "Waiting for gateway metadata relation data" in status.message


def test_service_mesh_active_status_with_gateway_data(
    harness, mocked_lightkube_client, mocked_kubernetes_service_patch
):
    """Test ActiveStatus when gateway-metadata relation has data."""
    # Arrange
    harness.set_leader(True)
    harness.begin()

    # Add gateway-metadata relation
    relation_id = harness.add_relation("gateway-metadata", "istio-beacon")
    harness.add_relation_unit(relation_id, "istio-beacon/0")

    # Mock the gateway metadata to return valid data
    mock_metadata = Mock()
    mock_metadata.namespace = "istio-system"
    mock_metadata.gateway_name = "istio-gateway"

    harness.charm.service_mesh.component._gateway_metadata_requirer.get_metadata = MagicMock(
        return_value=mock_metadata
    )

    # Act
    status = harness.charm.service_mesh.component.get_status()

    # Assert
    assert isinstance(status, ActiveStatus)
