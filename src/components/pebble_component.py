# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import logging

from charmed_kubeflow_chisme.components.pebble_component import PebbleServiceComponent
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class PvcViewerPebbleService(PebbleServiceComponent):
    def get_layer(self) -> Layer:
        """Defines and returns Pebble layer configuration

        This method is required for subclassing PebbleServiceContainer
        """
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
                    }
                },
            }
        )


class RbacProxyPebbleService(PebbleServiceComponent):
    def get_layer(self) -> Layer:
        """Defines and returns Pebble layer configuration

        This method is required for subclassing PebbleServiceContainer
        """
        logger.info("PebbleServiceComponent.get_layer executing")
        return Layer(
            {
                "summary": "kube rbac proxy layer",
                "description": "Pebble config layer for kube rbac proxy",
                "services": {
                    self.service_name: {
                        "override": "replace",
                        "summary": "Entry point for kube rbac proxy image",
                        "command": "/usr/local/bin/kube-rbac-proxy --secure-listen-address=0.0.0.0:8443 --upstream=http://127.0.0.1:8080/ --logtostderr=true --v=0",  # noqa: E501
                        "startup": "enabled",
                    }
                },
            }
        )
