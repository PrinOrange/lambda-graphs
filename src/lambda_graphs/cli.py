"""CLI for lambda-graphs"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

from .codeviews.combined_graph.combined_driver import CombinedDriver
from .utils.multi_file_merger import merge_files
from . import get_language_map

get_language_map()
app = typer.Typer()


@app.callback(invoke_without_command=True)
def main(
    lang: str = typer.Option(..., help="c, cpp, java"),
    code: Optional[str] = typer.Option(
        None,
        help="""
    int main() {
        int x = 3;
        x = x + 3;
        int y = 4;
        y += 1;
        return 0;
    }
    """,
    ),
    code_file: Optional[Path] = typer.Option(None, help="./test_file.c"),
    code_folder: Optional[Path] = typer.Option(
        None, help="./project_folder/ - combines all source files"
    ),
    combined_name: Optional[str] = typer.Option(
        None,
        help="Custom name for combined file (without extension), e.g., 'myproject'",
    ),
    graphs: str = typer.Option("ast,dfg", help="ast, cfg, dfg"),
    output: str = typer.Option("dot", help="all/json/dot/svg (dot generates png as well)"),
    blacklisted: str = typer.Option("", help="Nodes to be removed from the AST"),
    collapsed: bool = typer.Option(
        False, help="Collapses all occurrences of a variable into one node"
    ),
    last_def: bool = typer.Option(
        False, help="Adds last definition information to the DFG"
    ),
    last_use: bool = typer.Option(False, help="Adds last use information to the DFG"),
    throw_parse_error: bool = typer.Option(
        False, help="Throws an error if the code cannot be parsed"
    ),
    debug: bool = typer.Option(False, help="Enables debug logs"),
):
    """
    lambda-graphs

    Generates, customizes and combines multiple source code representations (AST, CFG, DFG)


    """
    if debug:
        level = "DEBUG"
    else:
        level = "WARNING"

    config = {
        "handlers": [{"sink": sys.stderr, "level": level}],
    }
    logger.configure(**config)

    codeviews = {
        "AST": {
            "exists": False,
            "collapsed": collapsed,
            "minimized": bool(blacklisted),
            "blacklisted": blacklisted.split(","),
        },
        "DFG": {
            "exists": False,
            "collapsed": collapsed,
            "minimized": False,
            "statements": True,
            "last_def": last_def,
            "last_use": last_use,
        },
        "CFG": {
            "exists": False,
        },
    }

    if "ast" in graphs.lower():
        codeviews["AST"] = {
            "exists": True,
            "collapsed": collapsed,
            "minimized": bool(blacklisted),
            "blacklisted": blacklisted.split(","),
        }
    if "dfg" in graphs.lower():
        codeviews["DFG"] = {
            "exists": True,
            "collapsed": collapsed,
            "minimized": False,
            "statements": True,
            "last_def": last_def,
            "last_use": last_use,
        }
    if "cfg" in graphs.lower():
        codeviews["CFG"] = {
            "exists": True,
        }

    try:
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)

        if code_folder:
            logger.info(f"Combining source files from folder: {code_folder}")

            temp_dir = Path("temp")
            temp_dir.mkdir(exist_ok=True)

            if combined_name:
                output_base_name = combined_name
            else:
                output_base_name = code_folder.name

            if lang == "c":
                combined_source_file = str(temp_dir / f"{output_base_name}.c")
            elif lang == "java":
                combined_source_file = str(temp_dir / f"{output_base_name}.java")
            else:
                combined_source_file = str(temp_dir / f"{output_base_name}.cpp")

            combined_file_path = merge_files(
                str(code_folder), lang, combined_source_file
            )
            logger.info(f"Combined source written to: {combined_file_path}")

            with open(combined_file_path, "r") as file_handle:
                src_code = file_handle.read()

            output_file_name = str(output_dir / f"{output_base_name}.json")
            CombinedDriver(
                src_language=lang,
                src_code=src_code,
                output_file=output_file_name,
                graph_format=output,
                codeviews=codeviews,
            )
        elif code_file:
            file_handle = open(code_file, "r")
            src_code = file_handle.read()
            file_handle.close()
            output_base_name = code_file.stem
            output_file_name = str(output_dir / f"{output_base_name}.json")
            CombinedDriver(
                src_language=lang,
                src_code=src_code,
                output_file=output_file_name,
                graph_format=output,
                codeviews=codeviews,
            )
        else:
            if not code:
                raise Exception("No code provided")
            output_file_name = str(output_dir / "output.json")
            CombinedDriver(
                src_language=lang,
                src_code=code,
                output_file=output_file_name,
                graph_format=output,
                codeviews=codeviews,
            )
    except Exception as e:
        try:
            logger.error(e.msg)
        except AttributeError:
            logger.error(e)
        sys.exit(-1)
