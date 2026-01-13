# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
import logging
from typing import Tuple

from charmed_kubeflow_chisme.components import Component
from charmed_kubeflow_chisme.service_mesh import generate_allow_all_authorization_policy
from charmed_service_mesh_helpers.interfaces import GatewayMetadataRequirer
from charms.istio_beacon_k8s.v0.service_mesh import (
    MeshType,
    PolicyResourceManager,
    ServiceMeshConsumer,
    UnitPolicy,
)
from lightkube import Client
from ops import ActiveStatus, BlockedStatus, WaitingStatus

logger = logging.getLogger(__name__)


class ServiceMeshComponent(Component):
    """Component to manage service mesh integration for pvcviewer."""

    def __init__(
        self,
        *args,
        service_mesh_relation_name: str = "service-mesh",
        gateway_metadata_relation_name: str = "gateway-metadata",
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self._service_mesh_relation_name = service_mesh_relation_name
        self._gateway_metadata_relation_name = gateway_metadata_relation_name

        # Observe relation changed events for both relations
        self._events_to_observe = [
            self._charm.on[relation_name].relation_changed
            for relation_name in [
                self._service_mesh_relation_name,
                self._gateway_metadata_relation_name,
            ]
        ]

        # Initialize ServiceMeshConsumer to create the policy for metrics endpoint
        # The policy gets created when the service-mesh relation is established (with beacon)
        self._mesh = ServiceMeshConsumer(
            self._charm,
            policies=[
                UnitPolicy(
                    relation="metrics-endpoint",
                ),
            ],
        )

        self._gateway_metadata_requirer = GatewayMetadataRequirer(
            self._charm, relation_name=self._gateway_metadata_relation_name
        )

        self._policy_resource_manager = PolicyResourceManager(
            charm=self._charm,
            lightkube_client=Client(
                field_manager=f"{self._charm.app.name}-{self._charm.model.name}"
            ),
            labels={
                "app.kubernetes.io/instance": f"{self._charm.app.name}-{self._charm.model.name}",
                "kubernetes-resource-handler-scope": f"{self._charm.app.name}-allow-all",
            },
            logger=logger,
        )

        # Allow allow policy needed to allow the K8s API to talk to the webhook
        self._allow_all_policy = generate_allow_all_authorization_policy(
            app_name=self._charm.app.name,
            namespace=self._charm.model.name,
        )

    def _configure_app_leader(self, event):
        """Reconcile the allow-all policy when the app is leader."""
        logger.info("Reconciling PRM")
        self._policy_resource_manager.reconcile(
            policies=[], mesh_type=MeshType.istio, raw_policies=[self._allow_all_policy]
        )

    def get_gateway_metadata(self) -> Tuple[str, str]:
        """Retrieve the gateway metadata from the relation or provide defaults.

        Returns:
            A tuple of (namespace, gateway_name)
        """
        gateway_metadata = self._gateway_metadata_requirer.get_metadata()
        if gateway_metadata:
            gateway_namespace = gateway_metadata.namespace
            gateway_name = gateway_metadata.gateway_name
            logger.info(
                f"Retrieved gateway metadata: namespace={gateway_namespace}, "
                f"gateway_name={gateway_name}"
            )
        else:
            logger.warning(
                f"Relation {self._gateway_metadata_relation_name} not found, "
                "defaulting to sidecar configuration."
            )
            gateway_namespace = "kubeflow"
            gateway_name = "kubeflow-gateway"
        return gateway_namespace, gateway_name

    def get_gateway_namespace(self) -> str:
        """Retrieve the gateway namespace from the relation."""
        return self.get_gateway_metadata()[0]

    def get_gateway_name(self) -> str:
        """Retrieve the gateway name from the relation."""
        return self.get_gateway_metadata()[1]

    def is_ambient_mesh_enabled(self) -> bool:
        """Check if ambient mesh is enabled based on the presence of gateway metadata relation."""
        gateway_metadata_relation = self.model.get_relation(self._gateway_metadata_relation_name)
        return gateway_metadata_relation is not None

    def remove(self, event):
        """Remove all policies on charm removal."""
        self._policy_resource_manager.reconcile(
            policies=[], mesh_type=MeshType.istio, raw_policies=[]
        )

    def get_status(self):
        """Validate relations and return status."""
        service_mesh_relation = self.model.get_relation(self._service_mesh_relation_name)
        gateway_metadata_relation = self.model.get_relation(self._gateway_metadata_relation_name)

        if service_mesh_relation and not gateway_metadata_relation:
            return BlockedStatus(
                "Service mesh relation present without gateway metadata relation",
            )

        if gateway_metadata_relation:
            gateway_data = self._gateway_metadata_requirer.get_metadata()
            if gateway_data is None:
                return WaitingStatus("Waiting for gateway metadata relation data")

        return ActiveStatus()
