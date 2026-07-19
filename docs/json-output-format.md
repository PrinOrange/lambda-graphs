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

每个节点代表程序中的一个语法或语义元素。

### 通用属性

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `integer` | 节点唯一标识符 |
| `node_type` | `string` | 节点来源图，取值见[[#node_type-取值说明]] |

**`node_type` 取值说明：**

在组合图中，`node_type` 以 `|` 分隔表示节点所属的图：

| 值 | 含义 |
|------|------|
| `"AST"` | 仅来自抽象语法树 |
| `"CFG"` | 仅来自控制流图 |
| `"DFG"` | 仅来自数据流图 |
| `"AST|CFG"` | 同时属于 AST 和 CFG |
| `"AST|DFG"` | 同时属于 AST 和 DFG |
| `"CFG|DFG"` | 同时属于 CFG 和 DFG |
| `"AST|CFG|DFG"` | 同时属于三种图 |

### AST 节点专有属性

AST 节点对应 tree-sitter 解析出的语法树节点。

| 字段 | 类型 | 说明 |
|------|------|------|
| `syntax_element` | `string` | tree-sitter AST 节点类型，如 `"function_definition"`、`"identifier"`、`"binary_expression"`、`"return_statement"`、`"translation_unit"` 等 |
| `token` | `string` | 节点的源代码文本；对于叶子节点，显示其字面量（如 `"int"`、`"add"`、`"a"`）；对于非叶子节点，显示其类型名（如 `"function_definition"`） |

示例：

```json
{
  "id": 9,
  "syntax_element": "identifier",
  "token": "add",
  "node_type": "AST"
}
```

### CFG 节点专有属性

CFG 节点以**语句**为粒度，每个节点代表一条可执行语句。

| 字段 | 类型 | 说明 |
|------|------|------|
| `statement` | `string` | 完整的源代码语句文本 |
| `line_no` | `integer` | 语句所在行号（从 1 开始） |
| `statement_type` | `string` | 语句类型分类，见[[#statement_type-取值]] |
| `label` | `string` | （仅组合图中的纯 CFG 节点保留）可视化标签，格式为 `"{line_no}_ {statement}"` |

#### `statement_type` 取值

**C 语言：**

| 值 | 含义 |
|------|------|
| `"start"` | 函数入口虚拟节点 |
| `"function_definition"` | 函数定义 |
| `"declaration"` | 变量声明 |
| `"expression_statement"` | 表达式语句（赋值、函数调用等） |
| `"if"` | if 条件判断 |
| `"while"` | while 循环 |
| `"for"` | for 循环 |
| `"do"` | do-while 循环 |
| `"switch"` | switch 语句 |
| `"case"` | case 分支 |
| `"return"` | return 返回语句 |
| `"break"` | break 语句 |
| `"continue"` | continue 语句 |
| `"goto"` | goto 跳转 |
| `"label"` | 标签语句 |

**C++ 语言**（包含上述 C 全部，外加）：

| 值 | 含义 |
|------|------|
| `"try"` | try 块 |
| `"catch"` | catch 异常捕获 |
| `"enum"` | 枚举定义 |
| `"union"` | 联合体定义 |
| `"typedef"` | 类型别名 |
| `"friend"` | 友元声明 |
| `"static_assert"` | 静态断言 |
| `"namespace_alias"` | 命名空间别名 |
| `"using"` | using 声明 |
| `"new"` | new 表达式 |
| `"implicit_return"` | 隐式返回（合成节点） |
| `"synthetic_constructor"` | 隐式默认构造函数（合成节点） |

**Java 语言：**

| 值 | 含义 |
|------|------|
| `"start"` | 函数入口虚拟节点 |
| `"method_declaration"` | 方法声明 |
| `"constructor_declaration"` | 构造函数声明 |
| `"class_declaration"` | 类声明 |
| `"interface_declaration"` | 接口声明 |
| `"declaration"` | 变量声明 |
| `"expression_statement"` | 表达式语句 |
| `"if"` | if 条件判断 |
| `"while"` | while 循环 |
| `"for"` | for / enhanced-for 循环 |
| `"do"` | do-while 循环 |
| `"switch"` | switch 语句/表达式 |
| `"case"` | case 分支 |
| `"return"` | return 返回语句 |
| `"break"` | break 语句 |
| `"continue"` | continue 语句 |
| `"try"` | try / try-with-resources 块 |
| `"catch"` | catch 异常捕获 |
| `"finally"` | finally 块 |
| `"synchronized"` | synchronized 同步块 |
| `"label"` | 标签语句 |

**JavaScript 语言：**

JavaScript 的 `statement_type` 直接使用 tree-sitter AST 原始类型名，包括但不限于：

`"start"`、`"expression_statement"`、`"if_statement"`、`"while_statement"`、`"for_statement"`、`"for_in_statement"`、`"do_statement"`、`"break_statement"`、`"continue_statement"`、`"return_statement"`、`"switch_statement"`、`"throw_statement"`、`"try_statement"`、`"catch_clause"`、`"finally_clause"`、`"function_declaration"`、`"method_definition"`、`"arrow_function"`、`"class_declaration"`、`"lexical_declaration"`、`"variable_declaration"`、`"import_statement"`、`"export_statement"`、`"debugger_statement"`、`"labeled_statement"`

### DFG 节点

DFG 节点继承自 CFG 节点，属性完全相同（`statement`、`line_no`、`statement_type`），仅 `node_type` 标记为 `"DFG"`（独立 DFG）或在组合图中合并为 `"CFG|DFG"` 等形式。

### 组合图中的节点

当同一节点同时属于多个图（如语句级别的节点既在 AST 中又在 CFG 中），合并后的节点包含所有来源的全部属性：

- 纯 AST 节点拥有 `syntax_element`、`token`
- 纯 CFG/DFG 节点拥有 `statement`、`line_no`、`statement_type`
- 合并节点同时拥有以上全部属性
- `node_type` 以 `|` 拼接多个来源

---

## 边 (`links`)

每条边连接两个节点，表示语法或语义关系。

### 通用属性（所有边都有）

| 字段 | 类型 | 说明 |
|------|------|------|
| `from_node` | `integer` | 起始节点 ID |
| `to_node` | `integer` | 目标节点 ID |
| `key` | `integer` | 多重图键值（同一对 `from_node→to_node` 可有多条边，`key` 区分它们） |

### AST 边

`edge_type` = `"AST_edge"`，表示语法树的父子关系。

| 字段 | 类型 | 说明 |
|------|------|------|
| `edge_type` | `"AST_edge"` | 固定值 |

示例：

```json
{
  "edge_type": "AST_edge",
  "from_node": 6,
  "to_node": 7,
  "key": 0
}
```

### CFG 边

`edge_type` = `"CFG_edge"`，表示控制流关系。

| 字段 | 类型 | 说明 |
|------|------|------|
| `edge_type` | `"CFG_edge"` | 固定值 |
| `controlflow_type` | `string` | 控制流类型，见[[#controlflow_type-取值]] |
| `call_id` | `string`（可选） | 函数/方法调用标识符，出现在调用类边中，用于区分不同调用点 |

#### `controlflow_type` 取值

**基础控制流：**

| 值 | 含义 | 适用语言 |
|------|------|----------|
| `"first_next_line"` | 函数入口 → 第一条语句 | C, C++, Java, JS |
| `"next_line"` | 顺序执行：上一条 → 下一条 | C, C++ |
| `"next"` | 通用跳转到下一条 | C, C++, Java, JS |
| `"next_line 1~9, $"` | Java 中的顺序执行变体 | Java |

**条件分支：**

| 值 | 含义 | 适用语言 |
|------|------|----------|
| `"true_branch"` | 条件为真时的分支（旧名 `pos_next`） | C, C++, Java, JS |
| `"false_branch"` | 条件为假时的分支（旧名 `neg_next`） | C, C++, Java, JS |
| `"else_next"` | else 分支跳转 | JS |

**循环：**

| 值 | 含义 | 适用语言 |
|------|------|----------|
| `"loop_control"` | 循环控制（条件判断到体） | C, C++, Java |
| `"loop_update"` | 循环自更新（末尾 → 头部条件） | C, C++, Java |
| `"loop_next"` | 循环进入下一次 | JS |
| `"loop_exit"` | 循环退出 | JS |

**switch/case：**

| 值 | 含义 | 适用语言 |
|------|------|----------|
| `"switch_case"` | switch 进入某 case | C, C++, Java, JS |
| `"switch_exit"` | switch 退出 | C, C++, Java |
| `"switch_default"` | switch default 分支 | JS |
| `"case_next"` | case 穿透（fall-through） | C, C++, Java, JS |

**跳转：**

| 值 | 含义 | 适用语言 |
|------|------|----------|
| `"jump_next"` | goto / 跳转 | C, C++, Java |
| `"break"` | break 跳出 | JS |
| `"continue"` | continue 继续 | JS |

**函数/方法调用**（末尾可能附带 `|call_id` 后缀，存储在 `call_id` 字段中）：

| 值 | 含义 | 适用语言 |
|------|------|----------|
| `"function_call"` | 函数调用 | C, C++ |
| `"function_return"` | 函数返回 | C, C++ |
| `"method_call"` | 方法调用 | C++, Java |
| `"method_return"` | 方法返回 | C++, Java |
| `"virtual_call"` | 虚函数调用 | C++ |
| `"static_call"` | 静态方法调用 | C++ |
| `"static_return"` | 静态方法返回 | C++ |
| `"constructor_call"` | 构造函数调用 | C++, Java |
| `"constructor_return"` | 构造函数返回 | C++ |
| `"destructor_call"` | 析构函数调用 | C++ |
| `"destructor_chain"` | 析构函数链 | C++ |
| `"destructor_return"` | 析构函数返回 | C++ |
| `"operator_call"` | 运算符重载调用 | C++ |
| `"lambda_invocation"` | Lambda 调用 | C++, Java |
| `"lambda_return"` | Lambda 返回 | C++, Java |
| `"base_destructor_call"` | 基类析构调用 | C++ |
| `"implicit_base_constructor_call"` | 隐式基类构造调用 | C++ |

**异常处理：**

| 值 | 含义 | 适用语言 |
|------|------|----------|
| `"try_body"` | try 块入口 | JS |
| `"catch_next"` | catch 块入口 | C++, JS |
| `"catch_exception"` | 捕获异常 | C++, Java |
| `"finally_next"` | finally 块入口 | JS |
| `"throw_exit"` | throw 退出 | C++, Java |

**C++ 特有的其他边类型：**

| 值 | 含义 |
|------|------|
| `"program_entry"` | 程序入口 |
| `"static_init_start"` | 静态初始化开始 |
| `"static_init_next"` | 静态初始化下一条 |
| `"static_init_to_main"` | 静态初始化到 main |
| `"implicit_return"` | 隐式函数返回 |
| `"scope_exit_destructor"` | 作用域退出析构 |
| `"scope_destructor_return"` | 作用域析构返回 |

**Java 特有的其他边类型：**

| 值 | 含义 |
|------|------|
| `"class_next"` | 类声明下一条 |
| `"class_return"` | 类声明返回 |
| `"constructor_next"` | 构造函数下一条 |
| `"main_method_next"` | main 方法下一条 |
| `"return_next"` | return 下一条 |

示例：

```json
{
  "controlflow_type": "true_branch",
  "edge_type": "CFG_edge",
  "from_node": 6,
  "to_node": 18,
  "key": 0
}
```

带 `call_id` 的调用边示例：

```json
{
  "controlflow_type": "method_call",
  "edge_type": "CFG_edge",
  "call_id": "1",
  "from_node": 20,
  "to_node": 5,
  "key": 0
}
```

### DFG 边

`edge_type` = `"DFG_edge"`，表示数据流关系。

| 字段 | 类型 | 说明 |
|------|------|------|
| `edge_type` | `"DFG_edge"` | 固定值 |
| `dataflow_type` | `string` | 数据流类型，见下表 |
| `used_def` | `string` | 涉及的变量名 |
| `object_name` | `string`（可选） | 构造/析构边上的对象名（如 `"this"`） |
| `interprocedural` | `string`（可选） | 过程间数据流标记（如 `"call_to_function"`） |
| `lambda_var` | `string`（可选） | lambda 变量名 |

#### `dataflow_type` 取值

| 值 | 含义 | 适用语言 |
|------|------|----------|
| `"comesFrom"` | 变量使用点 → 变量定义点（最常见的数据流边） | C, C++, JS |
| `"parameter"` | 形参传递 | C, C++ |
| `"lastDef"` | 变量在某处的最后一个定义（需启用 `last_def=True`） | C, C++ |
| `"lastUse"` | 变量在某处的最后一个使用（需启用 `last_use=True`） | C, C++ |
| `"loop_carried"` | 循环携带的数据依赖 | C++ |
| `"constructor_call"` | 构造函数数据流 | C++ |
| `"base_constructor_call"` | 基类构造函数数据流 | C++ |
| `"destructor_call"` | 析构函数数据流 | C++ |
| `"base_destructor_call"` | 基类析构函数数据流 | C++ |
| `"virtual_dispatch"` | 虚函数派发数据流 | C++ |
| `"lambda_call"` | Lambda 数据流 | C++ |

示例：

```json
{
  "dataflow_type": "comesFrom",
  "edge_type": "DFG_edge",
  "used_def": "a",
  "from_node": 6,
  "to_node": 18,
  "key": 1
}
```

---

## JSON 输出处理规则

以下属性属于**可视化属性**，生成 JSON 时会被自动移除：

**节点上移除：**
- `shape`、`style`、`fillcolor`、`color`
- `label`（仅当节点同时拥有 `statement` 字段时移除；纯 AST 节点保留 `label`）

**边上移除：**
- `color`、`shape`、`style`、`fillcolor`、`label`

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
      "node_type": "CFG|DFG"
    },
    {
      "id": 5,
      "syntax_element": "translation_unit",
      "token": "translation_unit",
      "node_type": "AST"
    },
    {
      "id": 6,
      "syntax_element": "function_definition",
      "token": "function_definition",
      "statement": " int add(int a, int b)",
      "line_no": 2,
      "statement_type": "function_definition",
      "node_type": "AST|CFG|DFG"
    },
    {
      "id": 9,
      "syntax_element": "identifier",
      "token": "add",
      "node_type": "AST"
    },
    {
      "id": 18,
      "syntax_element": "declaration",
      "token": "declaration",
      "statement": "int c = a + b;",
      "line_no": 3,
      "statement_type": "declaration",
      "node_type": "AST|CFG|DFG"
    },
    {
      "id": 25,
      "syntax_element": "return_statement",
      "token": "return_statement",
      "statement": "return c;",
      "line_no": 4,
      "statement_type": "return",
      "node_type": "AST|CFG|DFG"
    }
  ],
  "links": [
    { "edge_type": "AST_edge", "from_node": 5, "to_node": 6, "key": 0 },
    {
      "controlflow_type": "first_next_line",
      "edge_type": "CFG_edge",
      "from_node": 6, "to_node": 18, "key": 0
    },
    {
      "dataflow_type": "comesFrom",
      "edge_type": "DFG_edge",
      "used_def": "a",
      "from_node": 6, "to_node": 18, "key": 1
    },
    {
      "dataflow_type": "comesFrom",
      "edge_type": "DFG_edge",
      "used_def": "b",
      "from_node": 6, "to_node": 18, "key": 2
    },
    {
      "controlflow_type": "next_line",
      "edge_type": "CFG_edge",
      "from_node": 18, "to_node": 25, "key": 0
    },
    {
      "dataflow_type": "comesFrom",
      "edge_type": "DFG_edge",
      "used_def": "c",
      "from_node": 18, "to_node": 25, "key": 1
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
                                   return (id:25)
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
    ntype = attrs.get("node_type", "")
    if "AST" in ntype:
        print(f"AST node: {attrs.get('syntax_element')} → {attrs.get('token')}")
    if "CFG" in ntype or "DFG" in ntype:
        print(f"CFG/DFG node: line {attrs.get('line_no')} → {attrs.get('statement')} ({attrs.get('statement_type')})")

# 遍历边
for u, v, k, attrs in combined.edges(keys=True, data=True):
    etype = attrs.get("edge_type", "")
    if etype == "DFG_edge":
        print(f"DFG: {u}→{v}, var={attrs.get('used_def')}, type={attrs.get('dataflow_type')}")
    elif etype == "CFG_edge":
        cid = attrs.get("call_id", "")
        print(f"CFG: {u}→{v}, flow={attrs.get('controlflow_type')}{'|' + cid if cid else ''}")
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
