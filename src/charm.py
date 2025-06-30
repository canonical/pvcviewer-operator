#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm that allows ui access to PVCs.

https://github.com/canonical/pvcviewer-operator/
"""

import logging
import tempfile
from base64 import b64encode

import lightkube
from charmed_kubeflow_chisme.components import ContainerFileTemplate
from charmed_kubeflow_chisme.components.charm_reconciler import CharmReconciler
from charmed_kubeflow_chisme.components.kubernetes_component import KubernetesComponent
from charmed_kubeflow_chisme.components.leadership_gate_component import LeadershipGateComponent
from charmed_kubeflow_chisme.kubernetes import create_charm_default_labels
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.observability_libs.v1.kubernetes_service_patch import KubernetesServicePatch
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from lightkube.models.core_v1 import ServicePort
from lightkube.resources.admissionregistration_v1 import (
    MutatingWebhookConfiguration,
    ValidatingWebhookConfiguration,
)
from lightkube.resources.apiextensions_v1 import CustomResourceDefinition
from lightkube.resources.core_v1 import Service, ServiceAccount
from lightkube.resources.rbac_authorization_v1 import (
    ClusterRole,
    ClusterRoleBinding,
    Role,
    RoleBinding,
)
from ops import main
from ops.charm import CharmBase
from ops.framework import StoredState

from certs import gen_certs
from components.pebble_component import PvcViewerPebbleService

logger = logging.getLogger(__name__)

CERTS_FOLDER = "/tmp/k8s-webhook-server/serving-certs"
PORT = 443
WEBHOOK_PORT = 9443
METRICS_PORT = 8080
K8S_RESOURCE_FILES = [
    "src/templates/auth_manifests.yaml.j2",
    "src/templates/crd_manifests.yaml.j2",
    "src/templates/webhook_manifests.yaml.j2",
]


class PvcViewer(CharmBase):
    """PvcViewer Charm"""
    _stored = StoredState()

    def __init__(self, *args):
        """Charm for the PVC Viewer CRD controller."""
        super().__init__(*args)

        self._namespace = self.model.name
        # Expose controller's port
        webhook_port = ServicePort(port=PORT, targetPort=WEBHOOK_PORT, name=f"{self.app.name}")
        metrics_port = ServicePort(
            port=METRICS_PORT, targetPort=METRICS_PORT, name=f"{self.app.name}-metrics"
        )
        self.service_patcher = KubernetesServicePatch(
            self, [webhook_port, metrics_port], service_name=f"{self.model.app.name}"
        )
        self.prometheus_provider = MetricsEndpointProvider(
            charm=self,
            jobs=[{"static_configs": [{"targets": [f"*:{METRICS_PORT}"]}]}],
        )
        self.dashboard_provider = GrafanaDashboardProvider(self)
        self.charm_reconciler = CharmReconciler(self)

        # Generate self-signed certificates and store them
        self._gen_certs_if_missing()

        self.leadership_gate = self.charm_reconciler.add(
            component=LeadershipGateComponent(
                charm=self,
                name="leadership-gate",
            ),
            depends_on=[],
        )

        self.kubernetes_resources = self.charm_reconciler.add(
            component=KubernetesComponent(
                charm=self,
                name="kubernetes:auth-and-crds",
                resource_templates=K8S_RESOURCE_FILES,
                krh_resource_types={
                    CustomResourceDefinition,
                    Role,
                    RoleBinding,
                    ServiceAccount,
                    ClusterRole,
                    ClusterRoleBinding,
                    Service,
                    MutatingWebhookConfiguration,
                    ValidatingWebhookConfiguration,
                },
                krh_labels=create_charm_default_labels(
                    self.app.name, self.model.name, scope="auth-and-crds"
                ),
                context_callable=lambda: {
                    "app_name": self.app.name,
                    "namespace": self._namespace,
                    "cert": f"'{b64encode(self._stored.ca.encode('ascii')).decode('utf-8')}'",
                    "webhook_service_name": self.app.name,
                },
                lightkube_client=lightkube.Client(),
            ),
            depends_on=[self.leadership_gate],
        )

        # Create temporary files for the certificate data
        with tempfile.NamedTemporaryFile(delete=False) as key_file:
            key_file.write(self._stored.key.encode("utf-8"))

        with tempfile.NamedTemporaryFile(delete=False) as cert_file:
            cert_file.write(self._stored.cert.encode("utf-8"))

        with tempfile.NamedTemporaryFile(delete=False) as ca_file:
            ca_file.write(self._stored.ca.encode("utf-8"))

        # Use the temporary file paths as source_template_path
        self.pebble_service_container = self.charm_reconciler.add(
            component=PvcViewerPebbleService(
                charm=self,
                name="pvc-viewer-pebble-service",
                container_name="pvcviewer-operator",
                service_name="pvcviewer-operator",
                files_to_push=[
                    ContainerFileTemplate(
                        source_template_path=key_file.name,
                        destination_path=f"{CERTS_FOLDER}/tls.key",
                    ),
                    ContainerFileTemplate(
                        source_template_path=cert_file.name,
                        destination_path=f"{CERTS_FOLDER}/tls.crt",
                    ),
                    ContainerFileTemplate(
                        source_template_path=ca_file.name,
                        destination_path=f"{CERTS_FOLDER}/tls.ca",
                    ),
                ],
            ),
            depends_on=[self.kubernetes_resources],
        )

        self.charm_reconciler.install_default_event_handlers()
        self._logging = LogForwarder(charm=self)

    def _gen_certs_if_missing(self) -> None:
        """Generate certificates if they don't already exist in _stored."""
        logger.info("Generating certificates if missing.")
        cert_attributes = ["cert", "ca", "key"]
        # Generate new certs if any cert attribute is missing
        for cert_attribute in cert_attributes:
            try:
                getattr(self._stored, cert_attribute)
                logger.info(f"Certificate {cert_attribute} already exists, skipping generation.")
            except AttributeError:
                self._gen_certs()
                return

    def _gen_certs(self):
        """Refresh the certificates, overwriting all attributes if any attribute is missing."""
        logger.info("Generating certificates..")
        certs = gen_certs(
            service_name=self.app.name,
            namespace=self._namespace,
            webhook_service=self.app.name,
        )
        for k, v in certs.items():
            setattr(self._stored, k, v)


if __name__ == "__main__":
    main(PvcViewer)
