"""Charms dependencies for tests."""

from charmed_kubeflow_chisme.testing import CharmSpec

ISTIO_GATEWAY = CharmSpec(
    charm="istio-gateway", channel="latest/edge", config={"kind": "ingress"}, trust=True
)
ISTIO_PILOT = CharmSpec(
    charm="istio-pilot",
    channel="latest/edge",
    config={"default-gateway": "kubeflow-gateway"},
    trust=True,
)
