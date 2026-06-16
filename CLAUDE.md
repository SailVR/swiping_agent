# CLAUDE.md

此文件为 Claude Code（claude.ai/code）操作此仓库时提供指导。

## 项目概述

多智能体智能数据查询系统（信用卡刷卡金数据分析系统）。基于 LangGraph 的"一主三从"架构，支持 NL2SQL、ECharts 数据可视化、Tavily 联网搜索、以及双层记忆（短期 + 长期）。业务领域为信用卡刷卡金数据分析。

**技术栈**: LangGraph, LangChain, DashScope（通义千问 via OpenAI 兼容接口）, Tavily, MCP 协议, SQLite, Flask, ECharts, Rich。

## 架构

```
MultiAgentSystem (agent.py)
  └── MasterAgent (agents/master_agent.py) — 意图路由 / 协调 / 记忆
          ├── SQLQueryAgent (agents/sql_agent.py) — NL2SQL + 自动纠错 via MCP
          ├── DataAnalysisAgent (agents/analysis_agent.py) — 分析 + ECharts 图表
          └── WebSearchAgent (agents/search_agent.py) — Tavily 联网搜索
```

### LangGraph 状态图

`MasterAgent` 构建了一个包含 8 个节点和条件路由的 `StateGraph`：

```
intent → [按 6 种意图做条件路由]
  ├── simple_answer → END
  ├── sql_only → call_sql → summarize → END
  ├── analysis_only → call_analysis → summarize → END
  ├── sql_and_analysis → call_both → summarize → END
  ├── web_search → call_web_search → summarize → END
  └── search_and_sql → call_search_and_sql → summarize → END
```

状态定义为 `MasterAgentState` TypedDict，使用 `add_messages` reducer。图使用 `MemorySaver` 作为 checkpointer 实现对话持久化。

### 意图路由（6 种）

| 意图                 | 触发场景        | 调用链路                                                        |
| -------------------- | --------------- | --------------------------------------------------------------- |
| `simple_answer`    | 问候、闲聊      | 硬编码映射直接回复                                              |
| `sql_only`         | 纯数据查询      | NL2SQL → MCP 执行 → 汇总                                      |
| `analysis_only`    | 分析已有结果    | 从 `session_data[thread_id].last_sql_result` 读取 → LLM 分析 |
| `sql_and_analysis` | 查询 + 深度分析 | SQL → MCP → 分析（同一个节点内完成）                          |
| `web_search`       | 联网信息检索    | Tavily 搜索 → LLM 综合 → 汇总                                 |
| `search_and_sql`   | 内外数据对比    | SQL 查询 + Tavily 搜索 → LLM 联合分析 → 汇总                  |

关键点：`analysis_only` 复用了当前线程 `session_data` 中最近一次 SQL 查询结果——不会重新查询数据库。

### 优雅降级

当 `TAVILY_API_KEY` 未配置时，`search_agent.available = False`。如果意图路由器选中 `web_search` 或 `search_and_sql`，路由边会自动降级到 `simple_answer` 并提示配置信息。其他功能不受影响。

## 通信模式

- **前端 ↔ 后端**: HTTP REST API（`/api/login`, `/api/query`, `/api/query_stream`）+ SSE 流（`/api/query_stream`）
- **SQL 执行**: `SQLQueryAgent` 通过 stdio 传输拉起 `mcp_sql_server.py` 的 MCP 客户端进程，调用 `execute_sql` 工具
- **LangGraph 状态**: `MasterAgentState` TypedDict 以 `add_messages` reducer 流经图节点
- **SSE 事件**（7 种类型）: `status`, `intent`, `sql`, `sources`, `chart`, `chunk`, `done`
- **配置**: `config/config.yaml` 支持 `${ENV_VAR}` 替换——如 `tavily_api_key: "${TAVILY_API_KEY}"`
- **dotenv**: `app.py` 启动时调用 `load_dotenv()`——可在 `.env` 文件中存放本地密钥

## 关键设计模式

1. **双层 SQL 安全校验**: `sql_validator.py`（白名单机制：仅允许 SELECT/WITH/EXPLAIN 只读查询，检测多语句注入和危险关键词）在 `SQLQueryAgent._generate_sql()` 和 `mcp_sql_server.py` 两处都被调用，形成防御纵深，防止 LLM 生成的 DML/DDL 破坏数据库。
2. **优雅降级**: 联网搜索自动检测 API Key 缺失。SQL 自动纠错最多重试 3 次，最终失败时返回错误字符串。
3. **会话数据存储**: `master_agent.session_data[thread_id]` 存储 `last_sql_result`、`last_answer`、`last_chart_config`、`has_data`——支撑 `analysis_only` 重新分析功能和 `/api/export` 导出最新结果。
4. **短期记忆压缩**: 当消息超过 10 条或估算 token 数超过 `short_term_max_tokens` 时，LLM 自动总结对话。
5. **长期记忆提取**: 对话达到 6 条消息后，`MemoryExtractor` 自动将偏好和知识提取到 SQLite（`long_term_memory.db` 中的 `users`、`user_preferences`、`user_knowledge` 三张表）。
6. **多格式 LLM 输出处理**: `_llm_to_str()` 静态方法（在 master_agent.py、sql_agent.py、analysis_agent.py 中均有实现）统一处理 str/AIMessage/GenerationChunk，并自动剥离推理模型（如 qwen3.5-plus）的 `<think>` 标签。
7. **事件循环兼容**: `sql_agent.py` 的 `_run_async()` 检测正在运行的事件循环（可能来自 httpx/openai 内部），回退到 ThreadPoolExecutor 而非直接报错。
8. **每用户独立会话**: `app.py` 维护一个 `user_systems` 字典，每个 user_id 对应一个独立的 `MultiAgentSystem` 实例。

## 常用命令

### 环境设置

```bash
pip install -r requirements.txt
# 必需：设置 DashScope API Key
export DASHSCOPE_API_KEY=your_key
# 可选：联网搜索
export TAVILY_API_KEY=your_key
# 可选：创建 .env 文件（app.py 启动时自动加载）
echo "DASHSCOPE_API_KEY=your_key" > .env
```

### 初始化数据库

```bash
python data/init_db.py            # 创建 credit_bonus.db，包含 5 张表和 80 个模拟用户
python data/init_memory_db.py     # 创建 long_term_memory.db（users, preferences, knowledge 表）
```

### 运行

```bash
python agent.py                   # CLI 交互模式（输入用户 ID，然后提问）
python app.py                     # Web 服务器，访问 http://localhost:5001
bash start_web.sh                 # 一步启动 Web（含数据库检查）
```

### 测试 / 验证

```bash
python sql_validator.py           # 运行 SQL 校验器自测（21 个测试用例）
python data/test_db.py            # 运行数据库完整性测试
python demo.py                    # 快速测试 DashScope LLM 连通性
```

### 数据库 Schema

业务数据库（`credit_bonus.db`）包含 5 张表：`user_info`（80 个用户）、`card_transaction`（约 500 条交易，涵盖 8 种商户类型）、`cash_bonus_record`（每笔交易的刷卡金发放记录）、`cash_bonus_usage`（核销记录）、`activity_config`（5 个活动配置）。

## 项目文件

详细目录结构见 README.md。关键入口点：

- `agent.py` — `MultiAgentSystem` 类 + CLI 交互式入口
- `app.py` — Flask 服务器（端口 5001），REST + SSE 流式接口
- `agents/master_agent.py` — LangGraph 图定义，全部 8 个节点，记忆提取触发
- `agents/sql_agent.py` — NL2SQL + MCP 客户端，3 次重试纠错循环
- `agents/analysis_agent.py` — 数据分析 + 自动生成 ECharts 图表配置
- `agents/search_agent.py` — Tavily 集成，兼容 dict/tuple/list 多种返回格式
- `mcp_sql_server.py` — FastMCP 服务器，SQLite 查询执行
- `sql_validator.py` — 只读查询白名单校验器，基于正则表达式和语句规范化
- `export.py` — Excel（openpyxl）和 PDF（fpdf2）导出，自动检测系统现有中文字体
- `logger.py` — 轮转文件日志（5MB，3 个备份）+ 控制台 WARNING+ 输出，自动抑制 httpx/openai/langchain 等噪讯库
- `prompts.py` — 所有提示词模板：NL2SQL few-shot、意图分类（6 类）、数据分析、图表配置、SQL 纠错、搜索综合、搜索+SQL 联合分析
