"""
code-node: see how Python code works, read with ast and never run. A graph of who calls whom from an entry point and
what each path reaches (AWS calls, HTTP, environment variables), and the steps of each call.
"""

from __future__ import annotations

from .analysis.graph import CodeGraph, CodeSpan, GraphEdge, GraphNode, code_graph
from .analysis.mapping import map_code
from .analysis.model import CodeMap, Deployment, LibraryCall
from .deploys import Deploy, find_deployment, register_deploy
from .libraries import Library, register_library
from .platforms import Platform, get_platform, register_platform
from .project import EntryPoint, Project, entry_points, read_project

__version__ = "0.2.0"

__all__ = [
    "CodeGraph",
    "CodeMap",
    "CodeSpan",
    "Deploy",
    "Deployment",
    "EntryPoint",
    "GraphEdge",
    "GraphNode",
    "Library",
    "LibraryCall",
    "Platform",
    "Project",
    "code_graph",
    "entry_points",
    "find_deployment",
    "get_platform",
    "map_code",
    "read_project",
    "register_deploy",
    "register_library",
    "register_platform",
]
