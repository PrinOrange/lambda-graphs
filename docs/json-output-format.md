# JSON 输出格式说明

`lambda-graphs` 生成的 JSON 文件采用 **NetworkX node-link** 格式，完整描述了程序代码的多视图图结构（AST、CFG、DFG 及其组合）。

## 顶层结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `directed` | `boolean` | 是否为有向图，始终为 `true` |
| `multigraph` | `boolean` | 是否为多重图，始终为 `true`（同一对节点间可有多条不同类型边） |
| `graph` | `object` | **图级元数据**，描述图的整体属性 |
| `nodes` | `array` | 节点列表 |
| `links` | `array` | 边列表 |

### `graph` — 图级元数据

```json
{
  "language": "c",
  "views": ["ast", "cfg", "dfg"]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `language` | `string` | 源码语言，取值: `"c"` \| `"cpp"` \| `"java"` \| `"javascript"` |
| `views` | `string[]` | 生成时包含的图类型，如 `["ast"]`、`["cfg", "dfg"]`、`["ast", "cfg", "dfg"]` |

---

## 节点 (`nodes`)

每个节点代表程序中的一个语法或语义元素。节点属性取决于其来源图类型。

### 通用属性（所有节点都有）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `integer` | 节点唯一标识符，在 `links` 中通过 `source`/`target` 引用 |
| `node_source` | `string` | 节点来源图，取值见下表 |

`node_source` 取值说明：

| 值 | 含义 |
|------|------|
| `"AST"` | 仅来自抽象语法树 |
| `"CFG"` | 仅来自控制流图 |
| `"DFG"` | 仅来自数据流图 |
| `"AST\|CFG"` | 同时属于 AST 和 CFG（组合图） |
| `"AST\|DFG"` | 同时属于 AST 和 DFG |
| `"CFG\|DFG"` | 同时属于 CFG 和 DFG |
| `"AST\|CFG\|DFG"` | 同时属于三种图 |

### AST 节点专有属性

AST 节点对应 tree-sitter 解析出的语法树节点。

| 字段 | 类型 | 说明 |
|------|------|------|
| `node_type` | `string` | AST 节点类型，如 `"function_definition"`、`"identifier"`、`"binary_expression"`、`"return_statement"`、`"translation_unit"` 等 |
| `token` | `string` | 节点的源代码文本；对于非叶子节点，显示其类型名（如 `"function_definition"`）；对于叶子节点，显示其字面量（如 `"int"`、`"add"`、`"a"`） |

示例：

```json
{
  "id": 9,
  "node_type": "identifier",
  "token": "add",
  "node_source": "AST"
}
```

### CFG 节点专有属性

CFG 节点以**语句**为粒度，每个节点代表一条可执行语句。

| 字段 | 类型 | 说明 |
|------|------|------|
| `statement` | `string` | 完整的源代码语句文本 |
| `line_no` | `integer` | 语句所在行号（从 1 开始） |
| `statement_type` | `string` | 语句类型分类 |

`statement_type` 典型取值：

| 值 | 含义 |
|------|------|
| `"start"` | 函数入口虚拟节点 |
| `"function_definition"` | 函数定义 |
| `"declaration"` | 变量声明 / 赋值 |
| `"return"` | 返回语句 |
| `"if"` | if 条件判断 |
| `"while"` / `"for"` | 循环语句 |
| `"else_if"` / `"else"` | 条件分支 |

> **注意**: CFG 节点在 DOT/PNG/SVG 输出中有 `label` 字段（可视化标签），但 JSON 中会被**自动删除**，因为 `statement` + `line_no` 已提供相同信息。

示例：

```json
{
  "id": 18,
  "statement": "int c = a + b;",
  "line_no": 3,
  "statement_type": "declaration",
  "node_source": "CFG|DFG"
}
```

### DFG 节点

DFG 节点继承自 CFG 节点，属性完全相同（`statement`、`line_no`、`statement_type`），仅 `node_source` 标记为 `"DFG"`。

### 组合节点

当同一节点同时属于多个图（如语句级别的节点既在 CFG 中又在 AST 中），合并后的节点包含所有来源的全部属性，`node_source` 以 `|` 分隔。

---

## 边 (`links`)

每条边连接两个节点，表示语法或语义关系。边的类型由 `edge_type` 区分。

### 通用属性（所有边都有）

| 字段 | 类型 | 说明 |
|------|------|------|
| `source` | `integer` | 起始节点 ID |
| `target` | `integer` | 目标节点 ID |
| `key` | `integer` | 多重图键值（同一对 `source→target` 可有多条边，`key` 区分它们） |

### AST 边

| 字段 | 类型 | 说明 |
|------|------|------|
| `edge_type` | `"AST_edge"` | 固定值，标识 AST 父子关系 |

AST 边表示语法树的父子关系：父节点（如函数定义）→ 子节点（如函数名、参数列表、函数体）。

示例：

```json
{
  "edge_type": "AST_edge",
  "source": 6,
  "target": 7,
  "key": 0
}
```

### CFG 边

| 字段 | 类型 | 说明 |
|------|------|------|
| `edge_type` | `"CFG_edge"` | 固定值 |
| `controlflow_type` | `string` | 控制流类型，详细分类见下表 |
| `label` | `string` | 控制流标签，用于可视化（与 `controlflow_type` 对应） |

`controlflow_type` 取值：

| 值 | 含义 |
|------|------|
| `"first_next_line"` | 函数入口 → 第一条语句 |
| `"next_line"` | 顺序执行：上一条语句 → 下一条语句 |
| `"next"` | 跳转到下一条（如循环末尾 → 循环头部） |
| `"true"` | 条件为真时的分支 |
| `"false"` | 条件为假时的分支 |
| `"end"` | 函数末尾 |
| `"method_call"` | 普通方法调用 |
| `"constructor_call"` | 构造函数调用 |
| `"virtual_call"` | 虚函数调用 |

部分调用类型边会附加 `call_id` 字段，用于区分不同的调用点。

示例：

```json
{
  "controlflow_type": "first_next_line",
  "edge_type": "CFG_edge",
  "label": "first_next_line",
  "source": 6,
  "target": 18,
  "key": 0
}
```

### DFG 边

| 字段 | 类型 | 说明 |
|------|------|------|
| `edge_type` | `"DFG_edge"` | 固定值 |
| `dataflow_type` | `string` | 数据流类型，见下表 |
| `used_def` | `string` | 涉及的变量名 |

`dataflow_type` 取值：

| 值 | 含义 |
|------|------|
| `"comesFrom"` | 变量使用点 → 变量定义点（最常见的数据流边） |
| `"parameter"` | 形参传递 |
| `"lastDef"` | 变量在某处的最后一个定义（需启用 `last_def=True`） |

示例：

```json
{
  "dataflow_type": "comesFrom",
  "edge_type": "DFG_edge",
  "used_def": "a",
  "source": 6,
  "target": 18,
  "key": 1
}
```

---

## 完整示例

代码：

```c
int add(int a, int b) {
    int c = a + b;
    return c;
}
```

生成命令：

```python
from lambda_graphs import generate
result = generate("c", code=code, graphs=["ast", "cfg", "dfg"])
result.to_json("output.json")
```

输出（格式化后）：

```json
{
  "directed": true,
  "multigraph": true,
  "graph": {
    "language": "c",
    "views": ["ast", "dfg", "cfg"]
  },
  "nodes": [
    {
      "id": 1,
      "statement": "start_node",
      "line_no": 1,
      "statement_type": "start",
      "node_source": "CFG|DFG"
    },
    {
      "id": 5,
      "node_type": "translation_unit",
      "token": "translation_unit",
      "node_source": "AST"
    },
    {
      "id": 6,
      "node_type": "function_definition",
      "token": "function_definition",
      "node_source": "AST|CFG|DFG",
      "statement": " int add(int a, int b)",
      "line_no": 2,
      "statement_type": "function_definition"
    },
    {
      "id": 9,
      "node_type": "identifier",
      "token": "add",
      "node_source": "AST"
    },
    {
      "id": 18,
      "node_type": "declaration",
      "token": "declaration",
      "node_source": "AST|CFG|DFG",
      "statement": "int c = a + b;",
      "line_no": 3,
      "statement_type": "declaration"
    },
    {
      "id": 25,
      "node_type": "return_statement",
      "token": "return_statement",
      "node_source": "AST|CFG|DFG",
      "statement": "return c;",
      "line_no": 4,
      "statement_type": "return"
    }
  ],
  "links": [
    { "edge_type": "AST_edge", "source": 5, "target": 6, "key": 0 },
    { "edge_type": "AST_edge", "source": 6, "target": 7, "key": 0 },
    { "edge_type": "AST_edge", "source": 6, "target": 8, "key": 0 },
    { "edge_type": "AST_edge", "source": 6, "target": 17, "key": 0 },
    {
      "controlflow_type": "first_next_line",
      "edge_type": "CFG_edge",
      "label": "first_next_line",
      "source": 6, "target": 18, "key": 0
    },
    {
      "dataflow_type": "comesFrom",
      "edge_type": "DFG_edge",
      "used_def": "a",
      "source": 6, "target": 18, "key": 1
    },
    {
      "dataflow_type": "comesFrom",
      "edge_type": "DFG_edge",
      "used_def": "b",
      "source": 6, "target": 18, "key": 2
    },
    {
      "controlflow_type": "next_line",
      "edge_type": "CFG_edge",
      "label": "next_line",
      "source": 18, "target": 25, "key": 0
    },
    {
      "dataflow_type": "comesFrom",
      "edge_type": "DFG_edge",
      "used_def": "c",
      "source": 18, "target": 25, "key": 1
    }
  ]
}
```

### 边类型图示

```
start_node (id:1) ───CFG: next──▶  function_definition (id:6)
                                        │
               ┌── DFG: comesFrom(a) ───┤
               ├── DFG: comesFrom(b) ───┤
               └── CFG: first_next_line─┤
                                        ▼
                                   declaration (id:18)
                                       │
               ┌── DFG: comesFrom(c) ──┤
               └── CFG: next_line ─────┤
                                       ▼
                                   return_statement (id:25)
```

---

## 通过 Python API 访问

```python
import json
from lambda_graphs import generate

result = generate("cpp", code=code, graphs=["ast", "cfg", "dfg"])

# 获取组合图
combined = result.combined

# 图级元数据
print(combined.graph["language"])   # "cpp"
print(combined.graph["views"])      # ["ast", "cfg", "dfg"]

# 遍历节点
for nid, attrs in combined.nodes(data=True):
    source = attrs.get("node_source", "")
    if "AST" in source:
        print(f"AST node: {attrs.get('node_type')} → {attrs.get('token')}")
    if "CFG" in source:
        print(f"CFG node: line {attrs.get('line_no')} → {attrs.get('statement')}")

# 遍历边
for u, v, k, attrs in combined.edges(keys=True, data=True):
    etype = attrs.get("edge_type", "")
    if etype == "DFG_edge":
        print(f"DFG: {u}→{v}, var={attrs.get('used_def')}")
    elif etype == "CFG_edge":
        print(f"CFG: {u}→{v}, flow={attrs.get('controlflow_type')}")
    elif etype == "AST_edge":
        print(f"AST: {u}→{v}")

# 单独访问某个图
if result.ast:
    print(f"AST: {result.ast.number_of_nodes()} nodes")
if result.cfg:
    print(f"CFG: {result.cfg.number_of_nodes()} nodes")
if result.dfg:
    print(f"DFG: {result.dfg.number_of_nodes()} nodes")

# 转为字典
import networkx as nx
from networkx.readwrite import json_graph
data = json_graph.node_link_data(result.combined)
print(json.dumps(data, indent=2))
```
