# lambda-graphs: Multi-View Code Representation Tool for C, C++, Java, and JavaScript

lambda-graphs aims to generate combined multi-code view graphs that can be used with various types of machine learning models (sequence models, graph neural networks, etc).

Tool Demonstration link: [https://youtu.be/50DvEbenp14](https://youtu.be/50DvEbenp14)

## Overview

`lambda-graphs` is a CLI tool and Python library for generating code representations (AST, CFG, DFG) from source code. It supports **C**, **C++**, **Java**, and **JavaScript**, at both method-level and file-level granularity.

- **AST** (Abstract Syntax Tree)
- **CFG** (Control Flow Graph)
- **DFG** (Data Flow Graph)
- **Combined graphs** (any combination of the above)

`lambda-graphs` provides both a CLI and a **Python API** so you can generate graphs programmatically without shelling out. It is designed to be easily extendable to various programming languages. This is primarily because we use [tree-sitter](https://tree-sitter.github.io/tree-sitter/), a highly efficient incremental parser that supports over 40 languages.

---
## Setup

**1. Create a new virtual environment:**
```console
python -m venv .venv
```

**2. Activate the environment:**
```console
source .venv/bin/activate  # On Linux/Mac
# or
.venv\Scripts\activate  # On Windows
```

**3. Install the package in development mode:**
```console
pip install -e .
```

**4. Install GraphViz (Optional - for visualization):**

GraphViz is only required if you want to generate DOT, PNG, or SVG output files.

**Ubuntu/Debian:**
```console
sudo apt install graphviz
```

**MacOS:**
```console
brew install graphviz
```

**Windows:**
Download from [graphviz.org](https://graphviz.org/download/)

---
## Generating Graphs

### Using CLI

After setup, use the `lambda-graphs` command directly.

The attributes and options supported by the CLI are well documented and can be viewed by running:
```console
lambda-graphs --help
```

**Single File Analysis:**

Generate a combined CFG and DFG graph for a C++ file:
```console
lambda-graphs --lang "cpp" --code-file ./test.cpp --graphs "cfg,dfg"
```

Generate an AST for a C file with output in JSON format:
```console
lambda-graphs --lang "c" --code-file ./example.c --graphs "ast" --output "json"
```

**Folder Analysis (Multi-file Projects):**

lambda-graphs can analyze entire projects by combining multiple source files from a folder:

```console
lambda-graphs --lang "c" --code-folder ./project/src --graphs "cfg,dfg" --output "json"
```

This will:
1. Recursively scan the folder for all `.c` and `.h` files
2. Combine them into a single temporary file (preserving includes, declarations, definitions)
3. Generate the requested codeviews from the combined source
4. Output results to the `output/` directory

You can customize the combined output file name:
```console
lambda-graphs --lang "cpp" --code-folder ./mylib --combined-name "myproject" --graphs "ast,cfg"
```

**Inline Code Analysis:**

You can also analyze code snippets directly without a file:
```console
lambda-graphs --lang "c" --code "int main() { int x = 5; return x; }" --graphs "ast,cfg"
```

**Additional CLI Options:**

| Option | Description |
|--------|-------------|
| `--output` | Output format: `json`, `dot`, `svg`, or `all` (dot generates PNG; svg generates SVG). Default: `dot` |
| `--collapsed` | Collapse duplicate variable nodes into a single node in AST |
| `--last-def` | Add last definition information to DFG edges (shows where variables were last defined) |
| `--blacklisted` | Comma-separated list of AST node types to exclude from the graph |

**Flag-Codeview Compatibility:**

| Flag | AST | CFG | DFG |
|------|:---:|:---:|:---:|
| `--collapsed` | ✓ | ✗ | ✗ |
| `--blacklisted` | ✓ | ✗ | ✗ |
| `--last-def` | ✗ | ✗ | ✓ |
| `--last-use` | ✗ | ✗ | ✓ |

**Examples:**

```console
# Generate all output formats (DOT, JSON, PNG)
lambda-graphs --lang "c" --code-file test.c --graphs "cfg" --output "all"

# Collapse duplicate variable nodes in DFG
lambda-graphs --lang "cpp" --code-file test.cpp --graphs "ast" --collapsed

# Add last definition tracking to DFG
lambda-graphs --lang "c" --code-file test.c --graphs "dfg" --last-def

# Exclude specific AST node types
lambda-graphs --lang "c" --code-file test.c --graphs "ast,cfg" --blacklisted "comment,string_literal"
```

### Using the Python API

You can also use `lambda-graphs` as a library to get graph objects directly (no file I/O):

```python
from lambda_graphs import generate

# -- 从代码字符串生成 ------------------------------------------------------
result = generate(
    "cpp",
    code="int main() { int x = 5; return x; }",
    graphs=["ast", "cfg", "dfg"],
)

# 每个图都是 networkx.MultiDiGraph
print(result.ast.nodes(data=True))
print(result.cfg.nodes(data=True))
print(result.dfg.nodes(data=True))
print(result.combined.nodes(data=True))

# 图级元数据（这里的 graph 对应 JSON 中的 "graph" 键）
print(result.combined.graph)  # {"language": "cpp", "views": ["ast", "cfg", "dfg"]}

# -- 从文件或文件夹生成 ----------------------------------------------------
result = generate("cpp", code_file="./test.cpp", graphs=["cfg", "dfg"])
result = generate("c", code_folder="./project/src", graphs=["cfg", "dfg"])

# -- 带额外选项 -----------------------------------------------------------
result = generate(
    "cpp",
    code="...",
    graphs=["ast", "dfg"],
    collapsed=True,                              # 合并重复变量节点
    last_def=True,                               # DFG 边附加 last-def 信息
    blacklisted=["comment", "number_literal"],   # 排除 AST 节点类型
)

# -- 导出到磁盘 -----------------------------------------------------------
result.to_json("output.json")   # JSON
result.to_dot("output.dot")     # DOT
result.to_png("output.png")     # PNG 图片
result.to_svg("output.svg")     # SVG 图片
```

`generate()` 返回的 `GraphsResult` 对象包含以下属性：

| 属性 | 类型 | 说明 |
|------|------|------|
| `.ast` | `nx.MultiDiGraph` \| `None` | AST 图 |
| `.cfg` | `nx.MultiDiGraph` \| `None` | CFG 图 |
| `.dfg` | `nx.MultiDiGraph` \| `None` | DFG 图 |
| `.combined` | `nx.MultiDiGraph` | 组合多视图图（始终存在） |
| `.language` | `str` | 源语言 |

`generate()` 参数说明：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `language` | `str` | ✓ | 源语言，支持 `"c"` / `"cpp"` / `"java"` / `"javascript"` |
| `code` | `str` | 三选一 | 源代码字符串 |
| `code_file` | `str\|Path` | 三选一 | 源代码文件路径 |
| `code_folder` | `str\|Path` | 三选一 | 源码文件夹路径（自动合并多文件） |
| `graphs` | `list[str]` | | 要生成的图类型，默认 `["ast", "cfg", "dfg"]` |
| `collapsed` | `bool` | | 合并重复变量节点，默认 `False` |
| `last_def` | `bool` | | DFG 边附加 last-def 信息，默认 `False` |
| `last_use` | `bool` | | DFG 边附加 last-use 信息，默认 `False` |
| `blacklisted` | `list[str]` | | 要排除的 AST 节点类型 |
| `combined_name` | `str` | | 多文件合并时的自定义名称（仅 `code_folder` 模式） |

> 更多 JSON 输出格式细节请参考 [docs/json-output-format.md](docs/json-output-format.md)。

---
## Limitations

While `lambda-graphs` provides _method-level_ and _file-level_ support, it's important to note the following limitations and known issues:

### General Limitations
- **Syntax Errors in Code**: To ensure accurate codeviews, the input code must be free of syntax errors. Code with syntax errors may not be correctly parsed and displayed in the generated codeviews. Note that the code does not need to be compilable, only syntactically valid.

### C++ Specific Limitations
In addition to the general limitations, the tool has the following limitations specific to C++:

- **Limited Template Metaprogramming Support**: Complex template metaprogramming patterns may not be fully captured in the generated codeviews.

- **Partial Preprocessor Directive Support**: Preprocessor directives (e.g., `#define`, `#ifdef`) are parsed but not fully processed. Conditional compilation may not be accurately reflected in the codeviews.

- **Limited Support for Advanced C++ Features**: Some advanced C++ features such as:
  - Complex inheritance hierarchies
  - Multiple inheritance with virtual functions
  - Template specializations
  - SFINAE patterns
  - Concepts (C++20)

  may not be fully represented in the generated codeviews.

---

## Output Examples

### Example 1: C++ Function Pointers and Control Flow

**CLI Command**:

```bash
lambda-graphs --lang "cpp" --code-file paper_assets/function_pointers.cpp --graphs "cfg,dfg"
```
---

**C++ Code Snippet** ([function_pointers.cpp](paper_assets/function_pointers.cpp)):

```cpp
#include <iostream>
void f1(int times) {
    if(!times)
        return;
    std::cout << "In f1()\n";
    f1(times-1);
}
void f2() {
    std::cout << "In f2()\n";
}
int main() {
    void (*fptr_1)(int);
    void (*fptr_2)(void);
    fptr_1 = &f1;
    fptr_2 = &f2;

    int var = 0;
    std::cin >> var;
    (var > 0) ? fptr_1(3) : fptr_2();
}
```
---

**Generated Codeview**:

![C++ Function Pointers Example](paper_assets/function_pointers_cfg_dfg.png)

---

### Example 2: C++ Class with Pass-by-Reference

**CLI Command**:

```bash
lambda-graphs --lang "cpp" --code-file paper_assets/pass_by_reference.cpp --graphs "cfg,dfg"
```
---

**C++ Code Snippet** ([pass_by_reference.cpp](paper_assets/pass_by_reference.cpp)):

```cpp
#include <iostream>

class TestClass {
public:
    int x;
    TestClass(int _x) {
        x = _x + 20;
    }
    void f1(int& a) {
        a += 100;
        a -= x;
    }
};
int main() {
    TestClass obj(30);
    int k = 0;
    obj.f1(k);
    std::cout << k; // prints 50
    return 0;
}
```
---

**Generated Codeview**:

![C++ Class Example](paper_assets/pass_by_reference_cfg_dfg.png)

---

## Code Organization

The code is structured in the following way:

1. **Preprocessing** (`src/lambda_graphs/utils/`): The `multi_file_merger.py` module combines multiple source files from a folder into a single file for analysis.

2. **Parsing** (`src/lambda_graphs/tree_parser/`): For each code-view, first the source code is parsed using the tree-sitter parser. The Parser and ParserDriver are implemented with various functionalities commonly required by all code-views. Language-specific features are further developed in the language-specific parsers (`c_parser.py`, `cpp_parser.py`, `java_parser.py`, `js_parser.py`).

3. **Codeview Generation** (`src/lambda_graphs/codeviews/`): This directory contains the core logic for the various codeviews:
   - `AST/` - Abstract Syntax Tree (language-agnostic)
   - `CFG/` - Control Flow Graph (language-specific: `CFG_c.py`, `CFG_cpp.py`, `CFG_java.py`, `CFG_js.py`)
   - `DFG/` - Data Flow Graph (language-agnostic)
   - `combined_graph/` - Combines multiple codeviews into a single graph

4. **CLI & API Entry Points** (`src/lambda_graphs/cli.py`, `__init__.py`): The CLI is implemented with Typer. The `generate()` function in `__init__.py` exposes the same functionality as a Python API.

5. **Node Definitions** (`src/lambda_graphs/utils/`): `c_nodes.py`, `cpp_nodes.py`, `java_nodes.py`, and `js_nodes.py` define AST node type categorizations used throughout the codebase.

---

## Acknowledgments

This tool builds upon the tree-sitter parsing framework and is inspired by research on source code representation learning for AI-driven software engineering tasks.
