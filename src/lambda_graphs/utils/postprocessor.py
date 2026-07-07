import copy
import json
import os
import re
from subprocess import check_call

import networkx as nx
from networkx.readwrite import json_graph

# Visual attributes that only make sense in DOT / PNG / SVG output.
# They are stripped from JSON to keep it data-only.
_JSON_STRIP_NODE_ATTRS = ("shape", "style", "fillcolor", "color")
_JSON_STRIP_EDGE_ATTRS = ("color", "shape", "style", "fillcolor")


def networkx_to_json(graph):
    """Convert a networkx graph to a json object (visual attrs stripped)."""
    graph_json = json_graph.node_link_data(graph)
    _strip_visual_attrs(graph_json)
    return graph_json


def write_networkx_to_json(graph, filename):
    """Convert a networkx graph to a json object and write to *filename*."""
    graph_json = json_graph.node_link_data(graph)
    _strip_visual_attrs(graph_json)
    if not os.getenv("GITHUB_ACTIONS"):
        with open(filename, "w") as f:
            json.dump(graph_json, f)
    return graph_json


def _strip_visual_attrs(graph_json):
    """Remove visual-only attributes from nodes and edges *in place*.

    Also drops ``label`` from CFG / DFG nodes that already expose the same
    information via ``statement`` + ``line_no`` (AST nodes keep ``label``).
    """
    for node in graph_json.get("nodes", []):
        for attr in _JSON_STRIP_NODE_ATTRS:
            node.pop(attr, None)
        if "statement" in node:
            node.pop("label", None)
    for link in graph_json.get("links", []):
        for attr in _JSON_STRIP_EDGE_ATTRS:
            link.pop(attr, None)


def to_dot(graph):
    return nx.nx_pydot.to_pydot(graph)


def write_to_dot(
    og_graph, filename, output_png=False, output_svg=False, src_language=None
):
    graph = copy.deepcopy(og_graph)
    if not os.getenv("GITHUB_ACTIONS"):
        dot_reserved_keywords = {
            "node",
            "edge",
            "graph",
            "digraph",
            "subgraph",
            "strict",
            "Node",
            "Edge",
            "Graph",
            "Digraph",
            "Subgraph",
            "Strict",
        }

        for node in graph.nodes:
            if "label" in graph.nodes[node]:
                label = graph.nodes[node]["label"]

                if src_language in ["c", "cpp", "java", "javascript"]:
                    label = str(label)
                    label = label.replace("\\", "\\\\")
                    label = label.replace('"', '\\"')
                    label = label.replace("\n", " ")
                    label = label.replace("\r", " ")
                else:
                    label = re.escape(label)

                if (
                    src_language in ["c", "cpp", "java", "javascript"]
                    or label in dot_reserved_keywords
                ):
                    label = f'"{label}"'

                graph.nodes[node]["label"] = label

            # Quote any string attribute that contains DOT-special characters
            for attr in ("statement", "token", "node_type", "statement_type"):
                val = graph.nodes[node].get(attr)
                if isinstance(val, str) and any(c in val for c in ':\\"<>{}|&#'):
                    escaped = val.replace("\\", "\\\\").replace('"', '\\"')
                    graph.nodes[node][attr] = f'"{escaped}"'

        for u, v, key, data in graph.edges(keys=True, data=True):
            for attr_name in ["used_def", "used_var", "returned_value"]:
                if attr_name in data:
                    attr_value = str(data[attr_name])
                    needs_quoting = attr_value in dot_reserved_keywords or (
                        src_language in ["c", "cpp", "java"] and "::" in attr_value
                    )
                    if needs_quoting:
                        graph.edges[u, v, key][attr_name] = f'"{attr_value}"'

        nx.nx_pydot.write_dot(graph, filename)
        if output_png:
            check_call(
                ["dot", "-Tpng", filename, "-o", filename.rsplit(".", 1)[0] + ".png"]
            )
        if output_svg:
            check_call(
                ["dot", "-Tsvg", filename, "-o", filename.rsplit(".", 1)[0] + ".svg"]
            )
