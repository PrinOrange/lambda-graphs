"""lambda-graphs — generate program code representations (AST, CFG, DFG) from source code.

Usage::

    from lambda_graphs import generate

    result = generate("cpp", code="int main() { return 0; }", graphs=["cfg", "dfg"])
    print(result.cfg.nodes(data=True))
    result.to_json("output.json")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

import networkx as nx

from .codeviews.combined_graph.combined_driver import CombinedDriver
from .utils import postprocessor
from .utils.language import get_language_map, SUPPORTED_LANGUAGES

_DEFAULT_GRAPHS = ("ast", "cfg", "dfg")


# ---------------------------------------------------------------------------
# Graph descriptor helpers (internal)
# ---------------------------------------------------------------------------


def _build_codeviews(
    graphs: List[str],
    collapsed: bool = False,
    last_def: bool = False,
    last_use: bool = False,
    blacklisted: Optional[List[str]] = None,
) -> dict:
    """Convert a list of graph names to the ``codeviews`` dict that CombinedDriver expects."""
    if blacklisted is None:
        blacklisted = []

    codeviews: dict = {
        "AST": {"exists": False},
        "DFG": {"exists": False},
        "CFG": {"exists": False},
    }

    graphs_lower = [g.lower() for g in graphs]

    if "ast" in graphs_lower:
        codeviews["AST"] = {
            "exists": True,
            "collapsed": collapsed,
            "minimized": bool(blacklisted),
            "blacklisted": blacklisted,
        }
    if "dfg" in graphs_lower:
        codeviews["DFG"] = {
            "exists": True,
            "collapsed": collapsed,
            "minimized": False,
            "statements": True,
            "last_def": last_def,
            "last_use": last_use,
        }
    if "cfg" in graphs_lower:
        codeviews["CFG"] = {"exists": True}

    return codeviews


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass
class GraphsResult:
    """Container for generated code-view graphs.

    Attributes:
        language: Source language that was parsed.
        combined: The combined multi-view graph (always present).
        ast: AST graph, or ``None`` if not requested.
        cfg: CFG graph, or ``None`` if not requested.
        dfg: DFG graph, or ``None`` if not requested.
    """

    language: str
    combined: nx.MultiDiGraph
    ast: Optional[nx.MultiDiGraph] = None
    cfg: Optional[nx.MultiDiGraph] = None
    dfg: Optional[nx.MultiDiGraph] = None

    # internal bookkeeping
    _source_path: Optional[Path] = field(default=None, repr=False)

    # -- output helpers --------------------------------------------------

    def to_json(self, path: Union[str, Path]) -> Path:
        """Write the **combined** graph to *path* as JSON (node-link format)."""
        path = Path(path)
        postprocessor.write_networkx_to_json(self.combined, str(path))
        return path

    def to_dot(self, path: Union[str, Path]) -> Path:
        """Write the **combined** graph to *path* in Graphviz DOT format."""
        path = Path(path)
        postprocessor.write_to_dot(
            self.combined,
            str(path),
            output_png=False,
            output_svg=False,
            src_language=self.language,
        )
        return path

    def to_png(self, path: Union[str, Path]) -> Path:
        """Render the **combined** graph to a PNG image at *path*."""
        import tempfile, shutil

        path = Path(path)
        with tempfile.NamedTemporaryFile(suffix=".dot", delete=False) as tmp:
            tmp_dot = tmp.name
        try:
            postprocessor.write_to_dot(
                self.combined,
                tmp_dot,
                output_png=True,
                output_svg=False,
                src_language=self.language,
            )
            # write_to_dot produces <tmp>.png alongside the dot file
            rendered = Path(tmp_dot).with_suffix(".png")
            shutil.move(str(rendered), str(path))
        finally:
            Path(tmp_dot).unlink(missing_ok=True)
        return path

    def to_svg(self, path: Union[str, Path]) -> Path:
        """Render the **combined** graph to an SVG image at *path*."""
        import tempfile, shutil

        path = Path(path)
        with tempfile.NamedTemporaryFile(suffix=".dot", delete=False) as tmp:
            tmp_dot = tmp.name
        try:
            postprocessor.write_to_dot(
                self.combined,
                tmp_dot,
                output_png=False,
                output_svg=True,
                src_language=self.language,
            )
            rendered = Path(tmp_dot).with_suffix(".svg")
            shutil.move(str(rendered), str(path))
        finally:
            Path(tmp_dot).unlink(missing_ok=True)
        return path


def generate(
    language: str,
    code: Optional[str] = None,
    *,
    code_file: Optional[Union[str, Path]] = None,
    code_folder: Optional[Union[str, Path]] = None,
    combined_name: Optional[str] = None,
    graphs: Optional[List[str]] = None,
    collapsed: bool = False,
    last_def: bool = False,
    last_use: bool = False,
    blacklisted: Optional[List[str]] = None,
) -> GraphsResult:
    """Parse source code and build the requested graphs.

    Parameters
    ----------
    language:
        One of ``"c"``, ``"cpp"``, ``"java"``.
    code:
        Source code as a string.  Mutually exclusive with *code_file* and
        *code_folder*.
    code_file:
        Path to a source file to read.
    code_folder:
        Path to a folder of source files — they will be merged into a single
        translation unit before parsing.
    combined_name:
        Custom base name used for the merged file when *code_folder* is given.
    graphs:
        Which graphs to generate, e.g. ``["ast", "cfg"]``.  Defaults to all
        three (``["ast", "cfg", "dfg"]``).
    collapsed:
        Collapse duplicate variable nodes into a single node (AST / DFG only).
    last_def:
        Annotate DFG edges with last-definition information.
    last_use:
        Annotate DFG edges with last-use information.
    blacklisted:
        AST node types to exclude, e.g. ``["comment", "string_literal"]``.

    Returns
    -------
    GraphsResult
        Container with ``.ast``, ``.cfg``, ``.dfg``, and ``.combined``
        :class:`networkx.MultiDiGraph` attributes.
    """
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Unsupported language: {language!r}. Use one of {SUPPORTED_LANGUAGES}."
        )

    if graphs is None:
        graphs = list(_DEFAULT_GRAPHS)

    # -- resolve source code -------------------------------------------------
    src_code: str
    source_path: Optional[Path] = None

    providers = sum(bool(x) for x in (code, code_file, code_folder))
    if providers == 0:
        raise ValueError(
            "One of 'code', 'code_file', or 'code_folder' must be provided."
        )
    if providers > 1:
        raise ValueError(
            "Only one of 'code', 'code_file', or 'code_folder' may be provided."
        )

    if code is not None:
        src_code = code
    elif code_file is not None:
        path = Path(code_file)
        src_code = path.read_text()
        source_path = path
    elif code_folder is not None:
        from .utils.multi_file_merger import merge_files
        import tempfile
        import os

        folder = Path(code_folder)
        combined = combined_name or folder.name
        ext_map = {"c": ".c", "cpp": ".cpp", "java": ".java"}
        suffix = ext_map.get(language, ".cpp")
        tmp_dir = tempfile.mkdtemp(prefix="lambda_graphs_")
        merged_path = os.path.join(tmp_dir, f"{combined}{suffix}")
        merge_files(str(folder), language, merged_path)
        src_code = Path(merged_path).read_text()
        source_path = Path(merged_path)
    else:
        raise AssertionError("unreachable")

    # -- build codeviews config ----------------------------------------------
    codeviews = _build_codeviews(
        graphs,
        collapsed=collapsed,
        last_def=last_def,
        last_use=last_use,
        blacklisted=blacklisted,
    )

    # -- drive ---------------------------------------------------------------
    driver = CombinedDriver(
        src_language=language,
        src_code=src_code,
        output_file=None,  # no auto file output
        graph_format="dot",
        codeviews=codeviews,
    )

    return GraphsResult(
        language=language,
        combined=driver.graph,
        ast=getattr(driver, "AST", None),
        cfg=getattr(driver, "CFG", None),
        dfg=getattr(driver, "DFG", None),
        _source_path=source_path,
    )
