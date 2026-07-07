import os

import networkx as nx

from ..AST.AST_driver import ASTDriver
from ..CFG.CFG_driver import CFGDriver
from ..DFG.DFG_driver import DFGDriver
from ...utils import postprocessor

# Visual scheme per graph type — used when a node belongs to exactly one source.
# When a node belongs to multiple sources we pick a blend colour.
_SOURCE_STYLES = {
    "AST": {"fillcolor": "#BFE6D3", "color": "#5AAA7D"},
    "CFG": {"fillcolor": "#D6E5F5", "color": "#5A8EC9"},
    "DFG": {"fillcolor": "#F5E0C6", "color": "#C98A5A"},
}

# Blend used when a node belongs to CFG *and* DFG (they share ids).
_MULTI_SOURCE_STYLE = {"fillcolor": "#D9D0E5", "color": "#7A6A9A"}  # light purple


def _merge_nodes_into(target, incoming, source_label):
    """Add *incoming* nodes/edges into *target*, merging the ``source`` attribute.

    When a node already exists in *target* its ``source`` is appended to
    (e.g. ``"CFG"`` → ``"CFG,DFG"``) and the visual style is updated to
    the multi-source blend.  Edges are simply unioned.
    """
    for nid, attrs in incoming.nodes(data=True):
        attrs = dict(attrs)  # shallow copy — don't mutate caller
        attrs.setdefault("node_source", source_label)

        if nid in target:
            old_source = target.nodes[nid].get("node_source", "")
            merged = old_source + "|" + source_label if old_source else source_label
            attrs["node_source"] = merged

            # pick visual style
            parts = set(merged.split("|"))
            if len(parts) == 1:
                style = _SOURCE_STYLES.get(list(parts)[0], {})
            else:
                style = _MULTI_SOURCE_STYLE
            attrs.update(style)

        target.add_node(nid, **attrs)

    target.add_edges_from(incoming.edges(data=True))


class CombinedDriver:
    def __init__(
        self,
        src_language="c",
        src_code="",
        output_file=None,
        graph_format="dot",
        codeviews={},
    ):
        self.src_language = src_language
        self.src_code = src_code
        self.codeviews = codeviews
        self.graph = nx.MultiDiGraph()
        self.results = {}

        if self.codeviews["DFG"]["exists"] == True:
            self.results["DFG"] = DFGDriver(
                self.src_language, self.src_code, "", self.codeviews
            )
            self.DFG = self.results["DFG"].graph

        if self.codeviews["AST"]["exists"] == True:
            self.results["AST"] = ASTDriver(
                self.src_language, self.src_code, "", self.codeviews["AST"]
            )
            self.AST = self.results["AST"].graph

        if self.codeviews["CFG"]["exists"] == True:
            self.results["CFG"] = CFGDriver(
                self.src_language, self.src_code, "", self.codeviews["CFG"]
            )
            self.CFG = self.results["CFG"].graph

        self.combine()
        if output_file:
            if graph_format == "all" or graph_format == "json":
                self.json = postprocessor.write_networkx_to_json(
                    self.graph, output_file
                )
            if graph_format == "all" or graph_format == "dot":
                postprocessor.write_to_dot(
                    self.graph,
                    output_file.split(".")[0] + ".dot",
                    output_png=True,
                    output_svg=(graph_format == "all"),
                    src_language=self.src_language,
                )
            if graph_format == "svg":
                postprocessor.write_to_dot(
                    self.graph,
                    output_file.split(".")[0] + ".dot",
                    output_svg=True,
                    src_language=self.src_language,
                )

    def get_graph(self):
        return self.graph

    def check_validity(self):
        """Write logic for valid combinations here"""
        return True

    # -- simple (single-graph) setters ----------------------------------------

    def AST_simple(self):
        self.graph = self.AST

    def DFG_simple(self):
        self.graph = self.DFG

    def CFG_simple(self):
        self.graph = self.CFG

    def DFG_collapsed(self):
        self.graph = self.DFG

    def AST_collapsed(self):
        self.graph = self.AST

    # -- multi-graph combiners ------------------------------------------------

    def combine_AST_DFG_simple(self):
        _merge_nodes_into(self.graph, self.AST, "AST")
        _merge_nodes_into(self.graph, self.DFG, "DFG")

    def combine_CFG_DFG_simple(self):
        _merge_nodes_into(self.graph, self.CFG, "CFG")
        _merge_nodes_into(self.graph, self.DFG, "DFG")

    def combine_AST_CFG_simple(self):
        _merge_nodes_into(self.graph, self.AST, "AST")
        _merge_nodes_into(self.graph, self.CFG, "CFG")

    def combine_AST_CFG_DFG_simple(self):
        _merge_nodes_into(self.graph, self.AST, "AST")
        _merge_nodes_into(self.graph, self.CFG, "CFG")
        _merge_nodes_into(self.graph, self.DFG, "DFG")

    def combine_AST_DFG_collapsed(self):
        _merge_nodes_into(self.graph, self.AST, "AST")
        _merge_nodes_into(self.graph, self.DFG, "DFG")

    # -- dispatcher -----------------------------------------------------------

    def combine(self):
        """Combine all combinations into a single graph"""

        if (
            self.codeviews["AST"]["exists"] == True
            and self.codeviews["CFG"]["exists"] == True
            and self.codeviews["DFG"]["exists"] == True
        ):
            self.combine_AST_CFG_DFG_simple()

        elif (
            self.codeviews["AST"]["exists"] == True
            and self.codeviews["DFG"]["exists"] == True
        ):
            if (
                self.codeviews["DFG"]["collapsed"] == False
                and self.codeviews["AST"]["collapsed"] == False
            ):
                self.combine_AST_DFG_simple()

            elif (
                self.codeviews["DFG"]["collapsed"] == True
                and self.codeviews["AST"]["collapsed"] == True
            ):
                self.combine_AST_DFG_collapsed()

        elif (
            self.codeviews["AST"]["exists"] == True
            and self.codeviews["CFG"]["exists"] == True
        ):
            self.combine_AST_CFG_simple()

        elif (
            self.codeviews["CFG"]["exists"] == True
            and self.codeviews["DFG"]["exists"] == True
        ):
            self.combine_CFG_DFG_simple()

        elif self.codeviews["AST"]["exists"] == True:
            if self.codeviews["AST"]["collapsed"] == True:
                self.AST_collapsed()
            else:
                self.AST_simple()

        elif self.codeviews["DFG"]["exists"] == True:
            if self.codeviews["DFG"]["collapsed"] == True:
                self.DFG_collapsed()
            else:
                self.DFG_simple()
        elif self.codeviews["CFG"]["exists"] == True:

            self.CFG_simple()
