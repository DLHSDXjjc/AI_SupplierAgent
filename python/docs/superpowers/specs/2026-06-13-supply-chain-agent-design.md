# 供应链自动补货Agent — 设计文档

**日期**: 2026-06-13
**状态**: 已批准

## 1. 项目定位

供应链补货顾问Agent — 用户用自然语言提问，Agent结合供应链知识库和实时库存数据，给出补货建议，人做最终决策。

## 2. 技术栈

| 组件 | 选型 |
|------|------|
| Web框架 | FastAPI + uvicorn |
| LLM | DeepSeek deepseek-chat (OpenAI兼容API) |
| Embedding | moka-ai/m3e-base (768维, 中文优化) |
| 向量数据库 | ChromaDB (PersistentClient) |
| Agent框架 | LangChain ReAct Agent |
| 数据源 | CSV模拟数据 |
| 可视化 | Streamlit |
| 服务注册 | Nacos v2 gRPC SDK |
| 容器化 | Docker, python:3.11-slim |

## 3. 项目目录结构

```
SupplyChain/
├── config/
│   ├── config.py
│   └── modelConfig.yaml
├── data/
│   ├── supply_chain_knowledge/
│   │   ├── reorder_strategy.txt
│   │   ├── inventory_policy.txt
│   │   └── supplier_guide.txt
│   ├── mock_inventory.csv
│   └── mock_suppliers.csv
├── vector_db/
├── tools/
│   ├── __init__.py
│   ├── knowledge_search.py
│   ├── inventory_query.py
│   ├── reorder_calc.py
│   └── order_simulator.py
├── agent/
│   ├── __init__.py
│   ├── agent_core.py
│   └── prompts.py
├── create_vector_db.py
├── rag_api.py
├── app.py
├── Dockerfile
└── requirements.txt
```

## 4. Agent核心设计

### Agent类型: LangChain ReAct Agent

Reasoning + Acting模式: LLM先思考需要调用什么工具 → 调用工具 → 观察结果 → 继续思考或给出最终回答。

### 工具定义 (4个LangChain Tool)

| 工具名 | 输入 | 输出 | 说明 |
|--------|------|------|------|
| knowledge_search | query: str, top_k: int | 相关知识段落文本 | RAG检索ChromaDB |
| inventory_query | sku_id: str 或 category: str | 库存数据 | 查询CSV模拟数据 |
| reorder_calculator | current_stock, safety_stock, lead_time_demand, order_cost, holding_cost | 建议补货量(EOQ)、紧迫度 | 安全库存+EOQ计算 |
| place_order | sku_id, quantity, supplier_id | 模拟订单号、预计到货时间 | 模拟下单 |

### System Prompt

```
你是一个供应链自动补货顾问。你可以查询库存数据、检索供应链知识库、
计算补货建议，并模拟下单。

工作原则：
1. 先查数据，再给建议 — 所有建议必须基于实际库存数据
2. 引用知识库 — 涉及策略问题时检索知识库，引用原文
3. 给出明确建议 — 补货量、供应商选择、紧迫程度
4. 说明依据 — 每条建议附上数据来源和计算逻辑
5. 不替用户做最终决定 — 下单前需用户确认
```

## 5. 知识库设计

### 文档规划

| 文档 | 内容 | 篇幅 |
|------|------|------|
| reorder_strategy.txt | 安全库存法、EOQ、JIT、ABC分类法、季节性备货 | ~3000字 |
| inventory_policy.txt | 周转率、盘点制度、呆滞物料、安全库存标准、缺货预警 | ~3000字 |
| supplier_guide.txt | 供应商评估、交期管理、多供应商策略、紧急采购、分级 | ~2000字 |

### 向量化参数

- Embedding: moka-ai/m3e-base
- 分块: chunk_size=300, chunk_overlap=40
- Collection: supply_chain_knowledge

## 6. 模拟数据设计

### mock_inventory.csv (20-30个SKU)

字段: sku_id, sku_name, category, current_stock, safety_stock, daily_demand, lead_time_days, unit_cost, supplier_id, status

覆盖品类: 办公用品、电子元器件、包装材料等
覆盖状态: 正常/预警/紧急

### mock_suppliers.csv (8-10个供应商)

字段: supplier_id, supplier_name, category, lead_time_days, min_order_qty, rating, price_tier

## 7. API设计

| 端点 | 方法 | 请求 | 响应 | 说明 |
|------|------|------|------|------|
| /ask | POST | {query} | {success, query, answer, tools_used, sources} | Agent主入口 |
| /inventory | GET | ?sku_id= 或 ?category= | {success, data} | 直接查库存 |
| /inventory/alert | GET | 无 | {success, alerts} | 预警SKU列表 |
| /order | POST | {sku_id, quantity, supplier_id} | {success, order_id, eta} | 模拟下单 |
| /health | GET | 无 | {status, total_passages} | 健康检查 |

## 8. Streamlit界面

- 左侧: 对话区 (自然语言提问 + Agent回答 + 工具调用过程)
- 右上: 库存看板 (正常/预警/紧急统计)
- 右中: 预警SKU列表
- 右下: 补货建议列表 (带[下单]按钮)

## 9. 实施步骤 (Agent-First)

1. 设计Agent架构 — 定义工具接口、Prompt、决策流程
2. 知识库RAG — 编写文档 + 构建向量库 + RAG工具
3. 库存查询工具 — 模拟数据 + 查询函数
4. 补货计算工具 — 安全库存/EOQ计算
5. 模拟下单工具 — 模拟API
6. Streamlit界面 — 交互Demo
