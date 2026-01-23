from .CFG_c import CFGGraph_c
from .CFG_cpp import CFGGraph_cpp
from ...tree_parser.parser_driver import ParserDriver
from ...utils import postprocessor


class CFGDriver:
    def __init__(
        self,
        src_language="c",
        src_code="",
        output_file="CFG_output.json",
        properties={},
    ):
        self.src_language = src_language

        self.parser = ParserDriver(src_language, src_code).parser
        self.root_node = self.parser.root_node
        self.src_code = self.parser.src_code
        self.properties = properties

        self.CFG_map = {
            "c": CFGGraph_c,
            "cpp": CFGGraph_cpp,
        }

        self.CFG = self.CFG_map[self.src_language](
            self.src_language,
            self.src_code,
            self.properties,
            self.root_node,
            self.parser,
        )
        self.node_list = self.CFG.node_list
        self.graph = self.CFG.graph
        if output_file:
            self.json = postprocessor.write_networkx_to_json(self.graph, output_file)
            postprocessor.write_to_dot(
                self.graph, output_file.split(".")[0] + ".dot",
                output_png=True, src_language=self.src_language
            )
