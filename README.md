# 多智能体智能数据查询系统 v3.0

> 信用卡刷卡金数据分析系统 —— 基于 LangGraph 的**一主三从**多智能体架构，支持 NL2SQL、ECharts 数据可视化、Tavily 联网搜索、双层记忆（短期 + 长期）、Excel/PDF 导出。

![demo](https://github.com/user-attachments/assets/597693d0-df09-4198-93bd-242497f23e09)

---

## 架构设计

```
MultiAgentSystem (agent.py)
    └── MasterAgent（主智能体 — 意图路由 / 协调 / 记忆）
            ├── SQLQueryAgent     （子智能体1 — NL2SQL + 自动纠错）
            ├── DataAnalysisAgent （子智能体2 — 数据分析 + ECharts 可视化）
            └── WebSearchAgent    （子智能体3 — Tavily 联网搜索）
```

### 意图路由（6 种）

| 意图 | 触发场景 | 调用链路 |
|------|---------|---------|
| `simple_answer` | 问候/闲聊 | 主智能体直接回答 |
| `sql_only` | 纯数据查询 | SQLQueryAgent（NL2SQL → MCP 执行 → 汇总） |
| `analysis_only` | 分析已有结果 | DataAnalysisAgent（复用最近一次 SQL 结果） |
| `sql_and_analysis` | 查询 + 深度分析 | SQLQueryAgent → DataAnalysisAgent |
| `web_search` | 联网信息检索 | WebSearchAgent（Tavily → LLM 综合） |
| `search_and_sql` | 内外部数据对比 | SQL 查询 + Tavily 搜索 → LLM 联合分析 |

---

## 核心功能

### 1. NL2SQL 查询（SQLQueryAgent）

- **Few-shot 提示词**引导 LLM 生成 SQL
- **Reflection 自动纠错**：执行失败时将错误信息反馈 LLM 重新生成，最多重试 3 次
- **双层 SQL 安全校验**（`sql_validator.py`）：白名单机制仅允许 SELECT/WITH/EXPLAIN 只读查询，检测多语句注入和危险关键词 — 在 SQL 生成和 MCP 执行两端均调用
- 通过 **MCP 协议**调用独立 SQL 服务器执行查询

### 2. 数据分析与可视化（DataAnalysisAgent）

- 自动统计数值字段（最小/最大/平均/总和），生成文字分析报告
- **ECharts 可视化**：LLM 自动选择图表类型（柱状图/折线图/饼图）并生成配置，前端直接渲染交互式图表

### 3. 联网搜索（WebSearchAgent）

- **纯搜索模式**：Tavily API 检索互联网信息，LLM 综合多来源内容并附带可信来源 URL
- **搜索+SQL 联合对比**：同时查询内部数据库与互联网，双维度对比分析
- **优雅降级**：未配置 `TAVILY_API_KEY` 时自动禁用搜索，不影响其他功能

### 4. 双层记忆系统

| 记忆层 | 技术 | 功能 |
|--------|------|------|
| **短期记忆** | LangGraph MemorySaver | 会话内对话历史保留；消息 > 10 条或 token > 1000 时 LLM 自动压缩总结 |
| **长期记忆** | SQLite（`long_term_memory.db`） | 跨会话持久化（`users`、`user_preferences`、`user_knowledge` 三张表）；对话 ≥ 6 条消息时自动提取用户偏好和知识 |

### 5. 数据导出（Export）

- **Excel 导出**（openpyxl）：表格数据带样式表头
- **PDF 导出**（fpdf2）：回答文本 + 数据明细表，自动检测系统中文字体（macOS 苹方/Windows 雅黑/Linux 文泉驿）

### 6. 流式输出（SSE）

前端接收 7 种 SSE 事件类型：

| 事件类型 | 说明 |
|---------|------|
| `status` | 当前处理步骤描述 |
| `intent` | 识别出的意图标签 |
| `sql` | 生成的 SQL 语句 |
| `sources` | 搜索来源 URL 列表 |
| `chart` | ECharts 图表配置 JSON |
| `chunk` | 回答文字流片段 |
| `done` | 完成信号 |

---

## 快速开始

### 环境要求

- Python 3.10+
- DashScope API Key（通义千问）

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 设置 API 密钥

```bash
# 必需：DashScope（通义千问）
export DASHSCOPE_API_KEY=your_dashscope_key

# 可选：Tavily 联网搜索（https://tavily.com，免费 1000 次/月）
export TAVILY_API_KEY=your_tavily_key
```

也可在项目根目录创建 `.env` 文件（`app.py` 启动时自动加载）：

```bash
echo "DASHSCOPE_API_KEY=your_key" > .env
echo "TAVILY_API_KEY=your_key" >> .env
```

### 3. 初始化数据库

```bash
python data/init_db.py             # 创建 credit_bonus.db（5 张表，80 用户）
python data/init_memory_db.py      # 创建 long_term_memory.db
```

### 4. 启动

**Web 模式**（推荐）：

```bash
# 一键启动（含数据库检查）
bash start_web.sh

# 或手动启动
python app.py
# 浏览器访问 http://localhost:5001
```

**CLI 模式**：

```bash
python agent.py
# 输入用户 ID 后即可提问
```

### 5. 命令行特殊命令

| 命令 | 功能 |
|------|------|
| `new` | 新会话（清空短期记忆，保留长期记忆） |
| `info` | 查看当前用户信息和偏好 |
| `exit` / `quit` | 退出系统 |

---

## 业务数据库 Schema

`credit_bonus.db`（信用卡刷卡金业务数据集）：

| 表名 | 说明 | 数据量 |
|------|------|--------|
| `user_info` | 用户信息（姓名、手机、等级、开卡时间） | 80 个模拟用户 |
| `card_transaction` | 信用卡交易流水（金额、商户类型、时间） | ~500 条，涵盖 8 种商户类型 |
| `cash_bonus_record` | 刷卡金发放记录（每笔交易的返现/活动赠送） | 关联每笔交易 |
| `cash_bonus_usage` | 刷卡金核销记录 | 使用明细 |
| `activity_config` | 活动配置表 | 5 个活动 |

---

## REST API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | Web 前端页面 |
| `/api/login` | POST | 用户登录，返回长期记忆偏好和知识 |
| `/api/query` | POST | 阻塞式查询接口 |
| `/api/query_stream` | POST | **流式 SSE 接口（推荐）** |
| `/api/new_session` | POST | 新建会话 |
| `/api/user_info` | POST | 获取用户信息和知识列表 |
| `/api/export` | POST | 导出最新查询结果（Excel/PDF） |
| `/api/health` | GET | 健康检查 |

---

## 测试问题示例

**简单问答**
- 你好，你能帮我做什么？
- 介绍一下系统能查询哪些数据

**数据查询**
- 总共有多少个用户？他们的等级分布如何？
- 查询所有餐饮类交易，按金额降序排列
- 哪些用户的刷卡金总额超过 500 元？

**查询 + 分析**
- 对比不同商户类型的交易金额分布
- 分析近 30 天交易趋势，给出图表
- 找出刷卡金使用率最高的用户群体特征

**仅分析**
- 帮我分析一下刚才的查询结果
- 从上次的数据中能看到什么趋势？

**联网搜索**
- 2025 年信用卡行业的最新政策有哪些？
- 目前银行刷卡金营销活动的主流玩法是什么？

**搜索 + SQL 联合对比**
- 我们平台的刷卡金使用率和行业平均水平相比怎么样？
- 当前信用卡消费趋势和我们内部数据是否一致？

---

## 配置说明

编辑 `config/config.yaml`：

```yaml
llm:
  provider: "dashscope"
  model: "qwen-turbo"          # 也可用 qwen-plus / qwen-max
  temperature: 0.1
  max_tokens: 2048

database:
  path: "./data/credit_bonus.db"

nl2sql:
  num_examples: 3              # Few-shot 示例数量

memory:
  long_term_db: "./data/long_term_memory.db"
  short_term_max_tokens: 1000
  compression_threshold: 10
  auto_extract_knowledge: true

search:
  tavily_api_key: "${TAVILY_API_KEY}"   # 支持 ${ENV_VAR} 替换
  max_results: 5
```

---

## 目录结构

```
swiping_agent/
├── agents/                    # 智能体模块
│   ├── master_agent.py       # 主智能体（LangGraph 图定义，8 个节点）
│   ├── sql_agent.py          # SQL 查询子智能体（NL2SQL + MCP 客户端 + 3 次纠错）
│   ├── analysis_agent.py     # 数据分析子智能体（ECharts 图表配置）
│   └── search_agent.py       # 联网搜索子智能体（Tavily 封装）
├── memory/                    # 记忆模块
│   ├── long_term_memory.py   # 长期记忆管理器（SQLite CRUD）
│   └── memory_extractor.py   # 记忆提取器（LLM 自动提取偏好/知识）
├── config/
│   └── config.yaml           # 全局配置（支持 ${ENV_VAR} 替换）
├── data/
│   ├── credit_bonus.db       # 业务数据库（5 张表）
│   ├── long_term_memory.db   # 长期记忆数据库
│   ├── init_db.py            # 业务数据库初始化脚本
│   ├── init_memory_db.py     # 记忆数据库初始化脚本
│   └── test_db.py            # 数据库完整性测试
├── static/                    # Web 前端
│   ├── index.html            # 主页面（蓝紫渐变主题）
│   ├── style.css             # 样式
│   └── app.js                # 前端逻辑（SSE 流式 / ECharts / 登录）
├── videos/                    # 演示视频
├── agent.py                   # MultiAgentSystem 类 + CLI 入口
├── app.py                     # Flask Web 服务器（端口 5001）
├── prompts.py                 # 提示词模板（NL2SQL / 意图分类 / 分析等）
├── mcp_sql_server.py          # MCP SQL 服务器（FastMCP）
├── sql_validator.py           # SQL 安全校验器（白名单 + 21 个测试用例）
├── export.py                  # 数据导出（Excel openpyxl / PDF fpdf2）
├── logger.py                  # 轮转文件日志（5MB，3 备份，自动抑制噪讯库）
├── demo.py                    # DashScope LLM 连通性测试
├── start_web.sh               # Linux/Mac 启动脚本
├── start_web.bat              # Windows 启动脚本
└── CLAUDE.md                  # 开发者指南（供 Claude Code 使用）
```

---

## 技术栈

| 类别 | 技术 |
|------|------|
| 工作流编排 | LangGraph（StateGraph + MemorySaver） |
| LLM 框架 | LangChain |
| 大语言模型 | 通义千问（DashScope OpenAI 兼容接口） |
| 联网搜索 | Tavily（via langchain-tavily） |
| 数据库协议 | MCP（Model Context Protocol, stdio 传输） |
| 数据存储 | SQLite |
| Web 框架 | Flask + Flask-CORS |
| 前端可视化 | ECharts 5, marked.js, highlight.js |
| 数据导出 | openpyxl（Excel）, fpdf2（PDF） |
| SQL 校验 | 正则白名单（只读查询，防注入） |
| 终端美化 | Rich |
| 日志 | 轮转文件日志（logging.handlers.RotatingFileHandler） |

---

## 关键设计模式

1. **双检 SQL 安全**：`sql_validator.py` 在 SQL 生成和 MCP 执行两端均校验，白名单仅允许 SELECT/WITH/EXPLAIN，检测多语句注入和危险关键词
2. **优雅降级**：Tavily 未配置时自动禁用联网搜索；SQL 纠错最多 3 次重试
3. **会话数据存储**：`master_agent.session_data[thread_id]` 缓存最近 SQL 结果、回答、图表配置，支撑 `analysis_only` 复分析
4. **多格式 LLM 输出处理**：统一处理 str/AIMessage/GenerationChunk，自动剥离推理模型的 `<think>` 标签
5. **事件循环兼容**：检测 httpx/openai 内部事件循环冲突，回退到 ThreadPoolExecutor

---

## 已完成功能 ✅

- **一主三从多智能体**：意图识别（6 种）、NL2SQL、数据分析、联网搜索 ✅ (v1.0 → v3.0)
- **双层记忆系统**：短期 LLM 压缩 + 长期 SQLite 持久化 ✅ (v2.0)
- **Web 前端**：Markdown 渲染、ECharts 图表、SSE 流式打字机效果 ✅ (v2.1)
- **联网搜索**：Tavily 集成、搜索+SQL 联合对比、来源 URL 展示 ✅ (v3.0)
- **数据导出**：Excel（带样式）+ PDF（自动中文检测） ✅ (v3.0)
- **SQL 安全校验**：白名单只读校验 + 21 个测试用例 ✅ (v3.0)
- **轮转日志**：5MB/文件、3 备份、自动抑制 httpx/openai 噪讯 ✅ (v3.0)

---

## 更新日志

### v3.0 (2026.03.10)
- ✨ 新增：联网搜索子智能体 `WebSearchAgent`（Tavily）
- ✨ 新增：`web_search` 和 `search_and_sql` 两种意图路由（共 6 种）
- ✨ 新增：搜索+SQL 联合对比分析模式
- ✨ 新增：搜索来源 URL 前端流式展示（`sources` SSE 事件）
- ✨ 新增：数据导出模块 `export.py`（Excel + PDF）
- ✨ 新增：SQL 安全校验器 `sql_validator.py`（双层校验）
- ✨ 新增：轮转日志模块 `logger.py`
- ✨ 新增：健康检查接口 `/api/health`、导出接口 `/api/export`
- ✨ 新增：`/api/query_stream` SSE 流式查询接口
- 🔧 全面架构升级：从"公司薪资"业务域重构为"信用卡刷卡金"业务域
- 🔧 优化：搜索智能体不可用时自动降级并友好提示

### v2.1 (2025.11.05)
- ✨ 新增：内置 Web 前端（Markdown 渲染 + 代码高亮）
- ✨ 新增：REST API（登录、查询、会话管理）
- ✨ 新增：启动脚本 `start_web.bat` / `start_web.sh`

### v2.0 (2025.10.21)
- ✨ 新增：长期记忆系统（跨会话持久化）
- ✨ 新增：短期记忆智能压缩（LLM 自动总结）
- ✨ 新增：自动记忆提取（从对话中提取偏好和知识）

### v1.0 (2025.10.16)
- 🎉 初始版本：一主两从架构、NL2SQL、数据分析、短期记忆

---

## 注意事项

- **必须**设置 `DASHSCOPE_API_KEY` 环境变量（或 `.env` 文件）
- 联网搜索需额外设置 `TAVILY_API_KEY`（不配置不影响其他功能）
- 初次运行前需执行数据库初始化脚本
- 使用相同 `user_id` 可跨会话保留个人偏好
- 长期记忆数据库建议定期备份（`data/long_term_memory.db`）
- Web 端口默认为 **5001**
