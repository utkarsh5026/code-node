"""
code-node: see how Python code works, read with ast and never run. A graph of who calls whom from an entry point and
what each path reaches (AWS calls, HTTP, environment variables), and the steps of each call.
"""

from __future__ import annotations

from .analysis.graph import CodeGraph, GraphEdge, GraphNode, code_graph
from .analysis.mapping import map_code
from .analysis.model import CodeMap
from .platforms import Platform, get_platform, register_platform
from .project import EntryPoint, Project, entry_points, read_project

__version__ = "0.1.0"

__all__ = ["CodeGraph", "CodeMap", "EntryPoint", "GraphEdge", "GraphNode", "Platform", "Project", "code_graph",
           "entry_points", "get_platform", "map_code", "read_project", "register_platform"]
