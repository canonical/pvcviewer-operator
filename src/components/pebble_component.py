# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.


"""Pebble service definition."""


import logging

from charmed_kubeflow_chisme.components.pebble_component import PebbleServiceComponent
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class PvcViewerPebbleService(PebbleServiceComponent):
    """Pebble service."""
    def get_layer(self) -> Layer:
        """Define and return Pebble layer configuration.

        This method is required for subclassing PebbleServiceContainer.
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
