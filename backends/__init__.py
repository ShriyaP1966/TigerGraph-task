import os

from backends.base import GraphBackend


def get_backend() -> GraphBackend:
    kind = os.environ.get("GRAPH_BACKEND", "mock")
    if kind == "mock":
        from backends.mock import MockBackend

        return MockBackend()
    if kind == "local":
        from backends.local import LocalBackend

        return LocalBackend()
    if kind == "tigergraph":
        from backends.tigergraph import TigerGraphBackend

        return TigerGraphBackend()
    raise ValueError(f"unknown GRAPH_BACKEND: {kind}")
