# AI_SupplierAgent · 智能补货助手

供应链自动补货 Agent — 一个基于 **RAG + LangChain Agent + Nacos** 的智能问答微服务，
并提供 Spring Cloud (OpenFeign) 侧的调用示例。

## 📦 仓库结构

```
AI_SupplierAgent/
├── python/                 # RAG + Agent 微服务 (FastAPI + LangChain + ChromaDB)
│   ├── agent/              # Agent 核心 (SupplyChainAgent)
│   ├── tools/              # 工具集：库存查询 / 库存预警 / 供应商查询 / 模拟下单
│   ├── config/             # 配置加载
│   │   └── modelConfig.example.yaml   # 配置模板（拷贝为 modelConfig.yaml 后填入真实值）
│   ├── data/               # 示例数据（库存 / 供应商 CSV）
│   ├── docs/               # 知识库文档（安全库存政策、紧急补货流程 …）
│   ├── rag_api.py          # FastAPI 服务入口（对外暴露 /ask /inventory /order 等）
│   ├── app.py              # Streamlit 前端看板
│   ├── create_vector_db.py # 一次性脚本：从 docs/ 构建 ChromaDB 向量库
│   └── Dockerfile
│
└── java/
    └── cart-rag-example/   # Spring Cloud 侧调用示例（从 hmall 项目抽出的 4 个文件）
        ├── cart-api/       # Feign 客户端 + 请求/响应 DTO
        └── cart-impl/      # Controller，向前端暴露 /rag/query
```

## 🏗 架构概览

```
┌────────────┐    HTTP     ┌─────────────────┐   Feign    ┌───────────────────┐
│  前端/网关 │ ─────────▶ │ cart-service    │ ─────────▶ │ Python RAG 服务   │
│            │   /rag/query│  RagController  │  /ask       │ FastAPI + Agent   │
└────────────┘             └─────────────────┘             └───────────────────┘
                                     ▲                              │
                                     │                              │ 调用
                                     │       Nacos 服务发现          ▼
                                ┌────┴────┐                ┌───────────────────┐
                                │  Nacos  │◀───register───▶│ ChromaDB / DeepSeek│
                                └─────────┘                └───────────────────┘
```

Java 端通过 Nacos 发现 Python 端注册的 `supplychain-rag` 服务，直接以 Feign 方式调用 `/ask` 接口。

## 🚀 快速开始

### 1. 启动 Python RAG 服务

```bash
cd python

# (a) 准备配置
cp config/modelConfig.example.yaml config/modelConfig.yaml
# 编辑 config/modelConfig.yaml，填入你自己的 DeepSeek API key 和 Nacos 地址

# (b) 安装依赖
pip install -r requirements.txt

# (c) 构建向量库（首次运行时）
python create_vector_db.py

# (d) 启动服务
uvicorn rag_api:app --host 0.0.0.0 --port 8001
```

服务启动后：
- FastAPI: <http://localhost:8001/docs>
- Streamlit 看板：`streamlit run app.py` → <http://localhost:8501>

### 2. Java 侧调用

见 [`java/cart-rag-example/README.md`](java/cart-rag-example/README.md)。

## 🔑 敏感信息

- `python/config/modelConfig.yaml` 已被 `.gitignore` 忽略，**不要**把带真实 API key 的文件提交上来
- 需要的话请在你自己环境里从 `modelConfig.example.yaml` 拷贝一份

## 📄 License

MIT
