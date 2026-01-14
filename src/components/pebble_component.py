# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
import dataclasses
import logging

from charmed_kubeflow_chisme.components.pebble_component import PebbleServiceComponent
from ops.pebble import Layer

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PvcViewerInputs:
    """Defines the required inputs for PvcViewerPebbleService."""

    gateway_name: str
    gateway_namespace: str
    istio_ambient: bool


class PvcViewerPebbleService(PebbleServiceComponent):
    def get_layer(self) -> Layer:
        """Defines and returns Pebble layer configuration

        This method is required for subclassing PebbleServiceContainer
        """
        try:
            inputs: PvcViewerInputs = self._inputs_getter()
        except Exception as err:
            raise ValueError("Failed to get inputs for Pebble container.") from err
        logger.info("PebbleServiceComponent.get_layer executing")
        return Layer(
            {
                "summary": "pvcviewer layer",
                "description": "Pebble config layer for pvcviewer",
                "services": {
                    self.service_name: {
                        "override": "replace",
                        "summary": "Entry point for pvcviewer image",
                        "command": "/manager --health-probe-bind-address=:8081 --metrics-bind-address=:8080 --leader-elect",  # noqa: E501
                        "startup": "enabled",
                        "environment": {
                            # Sidecar mode: USE_ISTIO=true, USE_GATEWAY_API=false
                            # Ambient mode: USE_ISTIO=false, USE_GATEWAY_API=true
                            "USE_ISTIO": str(not inputs.istio_ambient).lower(),
                            "USE_GATEWAY_API": str(inputs.istio_ambient).lower(),
                            "K8S_GATEWAY_NAME": inputs.gateway_name,
                            "K8S_GATEWAY_NAMESPACE": inputs.gateway_namespace,
                        },
                    }
                },
            }
        )
