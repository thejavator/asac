"""Ports: the interfaces the engine depends on.

Each port is a ``typing.Protocol``. Adapters implement them and are selected
by configuration. A conformance suite per port lives in ``tests/conformance``.
"""

from asac.ports.harness import Harness, HarnessDescriptor
from asac.ports.policy import PolicyEngine
from asac.ports.registry import Registry
from asac.ports.runner import Runner
from asac.ports.state import GateRecord, StateStore

__all__ = [
    "GateRecord",
    "Harness",
    "HarnessDescriptor",
    "PolicyEngine",
    "Registry",
    "Runner",
    "StateStore",
]
