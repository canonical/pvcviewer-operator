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
                "summary": "kfp-viewer layer",
                "description": "Pebble config layer for pvcviewer",
                "services": {
                    self.service_name: {
                        "override": "replace",
                        "summary": "Entry point for pvcviewer image",
                        "command": "/manager --leader-elect",
                        "startup": "enabled",
                        "environment": {},
                    }
                },
            }
        )
