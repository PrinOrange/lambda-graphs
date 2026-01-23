import os.path
import time

import networkx as nx
from loguru import logger

from atlas.codeviews.CFG.CFG_driver import CFGDriver
from atlas.codeviews.SDFG.SDFG_c import dfg_c
from atlas.codeviews.SDFG.SDFG_cpp import dfg_cpp
from atlas.utils import postprocessor, DFG_utils

debug = False


class DfgRda:
    def __init__(
            self,
            src_language="c",
            src_code="",
            output_file=None,
            graph_format="dot",
            properties=None,
    ):
        if not properties:
            properties = {
                "CFG": {},
                "DFG": {
                    "last_use": True,
                    "last_def": True,
                    "alex_algo": True,
                },
            }
        self.src_language = src_language
        self.src_code = src_code
        self.properties = properties
        self.graph = nx.MultiDiGraph()
        start = time.time()
        self.CFG_Results = CFGDriver(
            self.src_language, self.src_code, "", self.properties["CFG"]
        )
        end = time.time()
        self.CFG = self.CFG_Results.graph
        self.rda_table = None
        self.rda_result = None
        start_dfg = time.time()
        self.graph, self.debug_graph, self.rda_table, self.rda_result = self.rda(
            self.properties["DFG"]
        )
        end_dfg = time.time()
        if debug:
            logger.warning("CFG time: " + str(end - start) + " DFG time: " + str(end_dfg - start_dfg))
        if output_file:
            if graph_format == "all" or graph_format == "json":
                self.json = postprocessor.write_networkx_to_json(
                    self.graph, output_file
                )
            if graph_format == "all" or graph_format == "dot":
                postprocessor.write_to_dot(
                    self.graph, output_file.rsplit(".", 1)[0] + ".dot", output_png=True, src_language=self.src_language
                )
            if graph_format == "all" or graph_format == "dot":
                postprocessor.write_to_dot(
                    self.debug_graph, output_file.rsplit(".", 1)[0] + "_debug.dot", output_png=True, src_language=self.src_language
                )
            self.json = postprocessor.write_networkx_to_json(self.graph, output_file)

    def get_graph(self):
        return self.graph

    def index_to_code(self):
        tokens_index = DFG_utils.tree_to_token_index(self.CFG_Results.root_node)
        code = self.src_code.split("\n")
        code_tokens = [DFG_utils.index_to_code_token(x, code) for x in tokens_index]
        index_to_code = {}

        for (ind, code) in zip(tokens_index, code_tokens):
            if ind in self.CFG_Results.parser.index:
                idx = self.CFG_Results.parser.index[ind]
            else:
                idx = -1
            index_to_code[ind] = (idx, code)

        return index_to_code

    def rda(self, properties):
        lang_map = {
            "c": dfg_c,
            "cpp": dfg_cpp,
        }
        driver = lang_map[self.src_language]
        return driver(properties, self.CFG_Results)


if __name__ == '__main__':
    for extension in ("c", "cpp"):
        file = f"data/test_manual.{extension}"
        if not os.path.isfile(file):
            continue
        with open(file, "r") as f:
            sample_file = f.read()

        output_file = f"data/{extension}_test.json"
        src_code = sample_file
        result = DfgRda(
            src_language=extension,
            src_code=src_code,
            output_file=None,
        )
        graph = result.graph
        postprocessor.write_to_dot(
            graph,
            output_file.rsplit(".", 1)[0] + ".dot",
            output_png=True,
            src_language=extension,
        )
        debug_graph = result.debug_graph
        postprocessor.write_to_dot(
            debug_graph,
            output_file.rsplit(".", 1)[0] + "_debug.dot",
            output_png=True,
            src_language=extension,
        )
