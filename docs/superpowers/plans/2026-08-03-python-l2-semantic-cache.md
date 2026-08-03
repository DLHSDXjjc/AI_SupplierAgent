# Python 端 L2 语义匹配缓存 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Python 端 (`SupplyChain/`) 实现 L2 语义匹配缓存,作为 L1 (Java 端) 的下一级 —— 相同/相近语义的 query 通过 embedding + RediSearch KNN 命中,直接返回缓存响应,不再调 LLM。

**Architecture:**
- 新建独立 `cache/semantic_cache.py`,`SemanticCache` 类负责全部 L2 读/写,失败一律 fail-open
- `agent_core.py::chat()` 入口查缓存、出口写缓存(`_is_cacheable` 判定)
- `AskResponse` 加 `cache_hit` 字段,Java 端 `RagAnswerVO` 同步加 `cacheHit`,Feign 反序列化时透传
- L2 跟 L1 完全独立:共享 Redis db=3 但 key 空间隔离 (`ragcache:` vs `hmall:rag:cache:`)

**Tech Stack:** Python 3.12 / FastAPI / LangChain / Redis 5+ (redis-py 异步) / RediSearch HNSW / sentence-transformers (moka-ai/m3e-base) / pytest

**Spec:** `docs/superpowers/specs/2026-08-03-python-l2-semantic-cache-design.md`

**前置条件(开工前确认):**
- Redis `192.168.203.129:6379` db=3 已就绪(含 RediSearch / vectorset 模块)
- `pip install -r requirements.txt` 已成功
- 已存在 `modelConfig.yaml`(本地,不入 git),`api_key` 已填

---

## 文件结构

| 路径 | 状态 | 职责 |
|------|------|------|
| `SupplyChain/cache/__init__.py` | 新建 | 空文件,让 `cache` 是 package |
| `SupplyChain/cache/semantic_cache.py` | 新建 | `SemanticCache` 类 |
| `SupplyChain/tests/__init__.py` | 新建 | 空文件 |
| `SupplyChain/tests/conftest.py` | 新建 | pytest fixture(共享 Redis 连接 + embedding) |
| `SupplyChain/tests/test_is_cacheable.py` | 新建 | `_is_cacheable` 纯函数测试 |
| `SupplyChain/tests/test_semantic_cache_init.py` | 新建 | `SemanticCache` 初始化集成测试 |
| `SupplyChain/tests/test_semantic_cache_e2e.py` | 新建 | `SemanticCache` 端到端测试(put/get 命中) |
| `SupplyChain/tests/test_chat_cache_hook.py` | 新建 | `chat()` 缓存钩子测试(mock LLM) |
| `SupplyChain/pytest.ini` | 新建 | pytest 配置 |
| `SupplyChain/requirements.txt` | 改 | 加 `redis>=5.0.0` + `pytest>=8.0.0` |
| `SupplyChain/config/modelConfig.yaml` | 改 | 加 `redis:` 和 `semantic_cache:` 段(本地,有 key) |
| `SupplyChain/config/modelConfig.example.yaml` | 改 | 同上,模板(无 key) |
| `SupplyChain/config/config.py` | 改 | 加 `REDIS_*` 和 `SEMANTIC_CACHE_*` 全局变量 |
| `SupplyChain/agent/agent_core.py` | 改 | `__init__` 加载 embedding + 实例化 `self.semantic_cache`,`chat()` 改 async + 加缓存钩子,加 `_is_cacheable` |
| `SupplyChain/rag_api.py` | 改 | `AskResponse` 加 `cache_hit` 字段,`/ask` 路由 await chat + 透传 success/cache_hit |
| `hmall/cart-service/.../vo/RagAnswerVO.java` | 改 | 加 `Boolean cacheHit` 字段 + `@JsonProperty("cache_hit")` |
| `hmall/cart-service/.../service/impl/RagQueryServiceImpl.java` | 改 | L1 命中时填 cacheHit=true;Feign 拿到 Python 响应后透传 |

---

## 阶段 0:基础设施

### Task 0.1:加 redis 依赖

**Files:**
- Modify: `SupplyChain/requirements.txt:36`(末尾追加)

- [ ] **Step 1:追加依赖**

在 `requirements.txt` 末尾追加两行(空行隔开):

```text
# ==================== RAG 缓存 ====================
redis>=5.0.0                            # 异步 Redis 客户端(L2 语义缓存用)
```

(开发依赖 pytest 在 Task 0.2 单独追加,避免污染生产 requirements)

- [ ] **Step 2:安装**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && pip install "redis>=5.0.0"`
Expected: Successfully installed redis-x.y.z

- [ ] **Step 3:验证 import**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && python -c "import redis; import redis.asyncio; print(redis.__version__)"`
Expected: 输出形如 `5.0.x` 且无报错

- [ ] **Step 4:Commit**

```bash
cd D:/python/pythonProject/zhinangyixia-api/ZNYX
git add SupplyChain/requirements.txt
git commit -m "chore(deps): add redis>=5.0.0 for L2 semantic cache"
```

---

### Task 0.2:建 cache/ 和 tests/ 目录 + pytest 配置

**Files:**
- Create: `SupplyChain/cache/__init__.py`
- Create: `SupplyChain/tests/__init__.py`
- Create: `SupplyChain/pytest.ini`

- [ ] **Step 1:建 cache 包**

文件 `SupplyChain/cache/__init__.py`(空文件):

```python
```

- [ ] **Step 2:建 tests 包**

文件 `SupplyChain/tests/__init__.py`(空文件):

```python
```

- [ ] **Step 3:写 pytest 配置**

文件 `SupplyChain/pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_functions = test_*
addopts = -v --tb=short
markers =
    integration: 需要真实 Redis/ChromaDB 的集成测试
```

- [ ] **Step 4:加 pytest 到 requirements**

在 `requirements.txt` 的 "RAG 缓存" 段下方追加:

```text

# ==================== 开发依赖(可选) ====================
pytest>=8.0.0                          # 测试框架(L2 缓存用)
```

- [ ] **Step 5:安装 pytest 并验证**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && pip install "pytest>=8.0.0" && python -m pytest --collect-only`
Expected: `no tests ran` 或类似(因为还没写测试),但 exit code 0,无 import 错误

- [ ] **Step 6:Commit**

```bash
cd D:/python/pythonProject/zhinangyixia-api/ZNYX
git add SupplyChain/cache/ SupplyChain/tests/ SupplyChain/pytest.ini SupplyChain/requirements.txt
git commit -m "chore(test): scaffold cache package, tests dir, pytest config"
```

---

### Task 0.3:加 Redis + semantic_cache 配置段

**Files:**
- Modify: `SupplyChain/config/modelConfig.example.yaml`(末尾追加)
- Modify: `SupplyChain/config/modelConfig.yaml`(本地文件,用户手动)

- [ ] **Step 1:改 modelConfig.example.yaml**

在文件末尾(`nacos:` 段后)追加:

```yaml

# ==================== Redis 配置(L2 缓存用) ====================
redis:
  host: "192.168.203.129"
  port: 6379
  db: 3                                  # 跟 L1 共享 db=3
  # password: ""                          # 暂无密码,如需启用去掉注释

# ==================== 语义缓存配置(L2) ====================
semantic_cache:
  enabled: true                          # 一键开关
  ttl: 21600                             # 6h,跟 L1 对齐
  threshold: 0.88                        # cosine ≥ 这个数才算命中
  key_prefix: "ragcache:"
  index_name: "rag_semantic_cache"
  embedding_dim: 768                     # 跟现有 m3e-base 一致
```

- [ ] **Step 2:同步改 modelConfig.yaml(用户手动)**

**重要**:用户需要手动执行这一步(本地文件,不入 git),把同样的段加到 `SupplyChain/config/modelConfig.yaml`。

打开 `SupplyChain/config/modelConfig.yaml`,在 `nacos:` 段后粘贴上面同样的两段。

- [ ] **Step 3:验证 yaml 解析**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && python -c "import yaml; cfg = yaml.safe_load(open('config/modelConfig.yaml', encoding='utf-8')); print('redis.host:', cfg['redis']['host']); print('semantic_cache.threshold:', cfg['semantic_cache']['threshold']); print('embedding.model_name:', cfg['embedding']['model_name'])"`
Expected:
```
redis.host: 192.168.203.129
semantic_cache.threshold: 0.88
embedding.model_name: moka-ai/m3e-base
```

- [ ] **Step 4:Commit(只 commit example.yaml)**

```bash
cd D:/python/pythonProject/zhinangyixia-api/ZNYX
git add SupplyChain/config/modelConfig.example.yaml
git commit -m "feat(config): add redis and semantic_cache config sections to example"
```

---

### Task 0.4:改 config.py 加载新配置

**Files:**
- Modify: `SupplyChain/config/config.py:63`(`NACOS_HEARTBEAT` 行后追加)

- [ ] **Step 1:在 config.py 末尾追加**

在 `NACOS_HEARTBEAT = _config["nacos"]["heartbeat_interval"]` 那行后追加:

```python

# ==================== Redis配置 ====================
REDIS_HOST = _config["redis"]["host"]                           # Redis 地址
REDIS_PORT = _config["redis"]["port"]                           # Redis 端口
REDIS_DB = _config["redis"]["db"]                               # 数据库编号
REDIS_PASSWORD = _config["redis"].get("password") or None       # 密码(无则 None)

# ==================== 语义缓存配置 ====================
SEMANTIC_CACHE_ENABLED = _config["semantic_cache"]["enabled"]    # 开关
SEMANTIC_CACHE_TTL = _config["semantic_cache"]["ttl"]            # 过期时间(秒)
SEMANTIC_CACHE_THRESHOLD = _config["semantic_cache"]["threshold"]  # cosine 阈值
SEMANTIC_CACHE_KEY_PREFIX = _config["semantic_cache"]["key_prefix"]  # key 前缀
SEMANTIC_CACHE_INDEX_NAME = _config["semantic_cache"]["index_name"]  # 索引名
SEMANTIC_CACHE_EMBEDDING_DIM = _config["semantic_cache"]["embedding_dim"]  # 向量维度
```

- [ ] **Step 2:验证 import**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && python -c "from config.config import REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD, SEMANTIC_CACHE_ENABLED, SEMANTIC_CACHE_TTL, SEMANTIC_CACHE_THRESHOLD, SEMANTIC_CACHE_KEY_PREFIX, SEMANTIC_CACHE_INDEX_NAME, SEMANTIC_CACHE_EMBEDDING_DIM; print('REDIS:', REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD); print('CACHE:', SEMANTIC_CACHE_ENABLED, SEMANTIC_CACHE_TTL, SEMANTIC_CACHE_THRESHOLD, SEMANTIC_CACHE_KEY_PREFIX, SEMANTIC_CACHE_INDEX_NAME, SEMANTIC_CACHE_EMBEDDING_DIM)"`
Expected:
```
REDIS: 192.168.203.129 6379 3 None
CACHE: True 21600 0.88 ragcache: rag_semantic_cache 768
```

- [ ] **Step 3:Commit**

```bash
cd D:/python/pythonProject/zhinangyixia-api/ZNYX
git add SupplyChain/config/config.py
git commit -m "feat(config): load redis and semantic_cache globals"
```

---

## 阶段 1:SemanticCache 类

### Task 1.1:_is_cacheable 工具函数(纯函数,完全 TDD)

**Files:**
- Create: `SupplyChain/tests/test_is_cacheable.py`
- Modify: `SupplyChain/agent/agent_core.py`

- [ ] **Step 1:写失败测试**

文件 `SupplyChain/tests/test_is_cacheable.py`:

```python
"""
_is_cacheable 纯函数单元测试。
跟 L1 规则一致:success ∧ answer非空 ∧ tools_used ⊆ {knowledge_search}。
"""
import pytest
from agent.agent_core import SupplyChainAgent


class TestIsCacheable:
    def test_empty_response_not_cacheable(self):
        """空 answer 不缓存"""
        assert SupplyChainAgent._is_cacheable({"answer": "", "tools_used": [], "sources": []}) is False

    def test_missing_answer_field_not_cacheable(self):
        """answer 字段缺失不缓存"""
        assert SupplyChainAgent._is_cacheable({"tools_used": []}) is False

    def test_no_tools_used_is_cacheable(self):
        """空 tools_used(LLM 直答)算子集,可缓存"""
        assert SupplyChainAgent._is_cacheable({"answer": "答", "tools_used": [], "sources": []}) is True

    def test_only_knowledge_search_is_cacheable(self):
        """只有 knowledge_search 可缓存"""
        assert SupplyChainAgent._is_cacheable({"answer": "答", "tools_used": ["knowledge_search"], "sources": []}) is True

    def test_inventory_query_not_cacheable(self):
        """inventory_query(实时数据)不可缓存"""
        assert SupplyChainAgent._is_cacheable({"answer": "答", "tools_used": ["inventory_query"], "sources": []}) is False

    def test_mixed_tools_not_cacheable(self):
        """多工具混合不可缓存"""
        assert SupplyChainAgent._is_cacheable({"answer": "答", "tools_used": ["knowledge_search", "inventory_query"], "sources": []}) is False

    def test_order_simulator_not_cacheable(self):
        """place_order(操作类)不可缓存"""
        assert SupplyChainAgent._is_cacheable({"answer": "答", "tools_used": ["place_order"], "sources": []}) is False

    def test_success_false_not_cacheable(self):
        """success=False 不可缓存"""
        assert SupplyChainAgent._is_cacheable({"answer": "答", "tools_used": [], "sources": [], "success": False}) is False

    def test_whitespace_only_answer_not_cacheable(self):
        """只有空白的 answer 不缓存"""
        assert SupplyChainAgent._is_cacheable({"answer": "   ", "tools_used": [], "sources": []}) is False
```

- [ ] **Step 2:跑测试确认失败**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && python -m pytest tests/test_is_cacheable.py`
Expected: 9 个测试全 FAIL,错误形如 `AttributeError: type object 'SupplyChainAgent' has no attribute '_is_cacheable'`

- [ ] **Step 3:在 agent_core.py 加 _is_cacheable**

在 `SupplyChainAgent` 类定义内,**在 `chat()` 方法前**插入:

```python
    @staticmethod
    def _is_cacheable(response: dict) -> bool:
        """
        判断 LLM 响应是否可写入 L2 缓存。
        跟 L1 规则一致:success ∧ answer非空 ∧ tools_used ⊆ {knowledge_search}。
        """
        if not response.get("success", True):
            return False
        answer = response.get("answer", "")
        if not answer or not answer.strip():
            return False
        tools = set(response.get("tools_used", []))
        return tools.issubset({"knowledge_search"})
```

> **注意**:`@staticmethod` 因为这个方法不依赖 `self`,且测试中用 `SupplyChainAgent._is_cacheable({...})` 调用。

- [ ] **Step 4:跑测试确认通过**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && python -m pytest tests/test_is_cacheable.py`
Expected: 9 passed

- [ ] **Step 5:Commit**

```bash
cd D:/python/pythonProject/zhinangyixia-api/ZNYX
git add SupplyChain/tests/test_is_cacheable.py SupplyChain/agent/agent_core.py
git commit -m "feat(agent): add _is_cacheable static method for L2 cache eligibility"
```

---

### Task 1.2:SemanticCache 类(conftest fixture + init 集成测试 + 完整类实现)

**Files:**
- Create: `SupplyChain/tests/conftest.py`
- Create: `SupplyChain/cache/semantic_cache.py`
- Create: `SupplyChain/tests/test_semantic_cache_init.py`

> **设计决策**:`SemanticCache` 类的 `__init__` / `get` / `put` / `_ensure_index` 紧密耦合,在一个 task 里一起交付比拆 2-3 个 task 然后重构更高效。本 task 包含 4 个步骤:fixture → 测试 → 实现 → 验证。

- [ ] **Step 1:写 conftest.py(Redis + embedding fixture)**

文件 `SupplyChain/tests/conftest.py`:

```python
"""
pytest 共享 fixture。
- `redis_client`:连接到 192.168.203.129:6379 db=3,测试结束自动清理 key
- `embedding_model`:m3e-base 加载较慢(5-10s),session 级别复用
"""
import os
import sys

import pytest
import redis.asyncio as redis_async

# 路径配置(同项目里其他模块)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# HuggingFace 镜像(避免下载失败)
if not os.environ.get("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from config.config import (
    REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD,
    SEMANTIC_CACHE_KEY_PREFIX, SEMANTIC_CACHE_INDEX_NAME,
    EMBEDDING_MODEL, EMBEDDING_DEVICE,
)
from sentence_transformers import SentenceTransformer


@pytest.fixture
async def redis_client():
    """异步 Redis 客户端,测试结束清理所有 ragcache:* key 和索引"""
    client = redis_async.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, password=REDIS_PASSWORD,
        decode_responses=False,
    )
    # 测试前清理
    await _cleanup(client, SEMANTIC_CACHE_KEY_PREFIX, SEMANTIC_CACHE_INDEX_NAME)
    yield client
    # 测试后清理
    await _cleanup(client, SEMANTIC_CACHE_KEY_PREFIX, SEMANTIC_CACHE_INDEX_NAME)
    await client.aclose()


@pytest.fixture(scope="session")
def embedding_model():
    """m3e-base 较慢,session 级别只加载一次"""
    return SentenceTransformer(EMBEDDING_MODEL, device=EMBEDDING_DEVICE)


async def _cleanup(client, prefix: str, index_name: str):
    """删除测试遗留的 key 和索引"""
    try:
        await client.execute_command("FT.DROPINDEX", index_name, "DD")
    except Exception:
        pass
    async for key in client.scan_iter(match=f"{prefix}*"):
        await client.delete(key)
```

- [ ] **Step 2:写失败测试(init 集成)**

文件 `SupplyChain/tests/test_semantic_cache_init.py`:

```python
"""
SemanticCache 初始化集成测试。
需要真实 Redis(192.168.203.129:6379 db=3)。
"""
import pytest
from cache.semantic_cache import SemanticCache
from config.config import (
    SEMANTIC_CACHE_TTL, SEMANTIC_CACHE_THRESHOLD,
    SEMANTIC_CACHE_KEY_PREFIX, SEMANTIC_CACHE_INDEX_NAME,
    SEMANTIC_CACHE_EMBEDDING_DIM,
)


@pytest.mark.integration
class TestSemanticCacheInit:
    async def test_ensure_index_creates_hnsw_index(self, redis_client, embedding_model):
        """_ensure_index 自动创建 RediSearch HNSW 索引"""
        cache = SemanticCache(
            redis_client=redis_client, embedding_model=embedding_model,
            threshold=SEMANTIC_CACHE_THRESHOLD, ttl=SEMANTIC_CACHE_TTL,
            key_prefix=SEMANTIC_CACHE_KEY_PREFIX, index_name=SEMANTIC_CACHE_INDEX_NAME,
            embedding_dim=SEMANTIC_CACHE_EMBEDDING_DIM,
        )
        await cache._ensure_index()
        # 验证索引存在
        info = await redis_client.execute_command("FT.INFO", SEMANTIC_CACHE_INDEX_NAME)
        info_str = " ".join(s.decode("utf-8", errors="replace") if isinstance(s, bytes) else str(s) for s in info)
        assert SEMANTIC_CACHE_INDEX_NAME in info_str
        assert "VECTOR" in info_str
        assert "HNSW" in info_str

    async def test_ensure_index_idempotent(self, redis_client, embedding_model):
        """重复创建不抛错(索引已存在时忽略)"""
        cache = SemanticCache(
            redis_client=redis_client, embedding_model=embedding_model,
            threshold=SEMANTIC_CACHE_THRESHOLD, ttl=SEMANTIC_CACHE_TTL,
            key_prefix=SEMANTIC_CACHE_KEY_PREFIX, index_name=SEMANTIC_CACHE_INDEX_NAME,
            embedding_dim=SEMANTIC_CACHE_EMBEDDING_DIM,
        )
        await cache._ensure_index()
        # 第二次应该不抛错
        await cache._ensure_index()
```

- [ ] **Step 3:跑测试确认失败**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && python -m pytest tests/test_semantic_cache_init.py`
Expected: FAIL,`ModuleNotFoundError: No module named 'cache.semantic_cache'`

- [ ] **Step 4:写 SemanticCache 完整实现**

文件 `SupplyChain/cache/semantic_cache.py`:

```python
"""
L2 语义匹配缓存 —— 基于 Redis + RediSearch HNSW。

【职责】
- 启动时创建 RediSearch 索引(若已存在则忽略)
- 读:query → embedding → KNN top-1 → 相似度 ≥ 阈值返回缓存
- 写:query + response → embedding + 序列化 → 写入 Redis
- 失败一律 fail-open(异常 → log.warn → 跳过)

【Redis 存储结构】
key:   {prefix}{md5(query)}            # 例如 ragcache:abc123...
value: HASH {
    "query": "原始 query 文本",
    "answer": "...",
    "tools_used": "JSON 列表字符串",
    "sources": "JSON 列表字符串",
    "embedding": "768 维 float32 字节",
    "created_at": "ISO 8601 时间戳"
}
index: HNSW (cosine, M=16, EF=200)
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import redis.asyncio as redis_async
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class SemanticCache:
    """L2 语义匹配缓存,失败一律 fail-open"""

    def __init__(
        self,
        redis_client: redis_async.Redis,
        embedding_model: SentenceTransformer,
        threshold: float,
        ttl: int,
        key_prefix: str,
        index_name: str,
        embedding_dim: int,
    ):
        self.redis = redis_client
        self.embedding = embedding_model
        self.threshold = threshold
        self.ttl = ttl
        self.key_prefix = key_prefix
        self.index_name = index_name
        self.embedding_dim = embedding_dim
        self._enabled = True

    async def _ensure_index(self):
        """创建 RediSearch 索引(若已存在忽略)"""
        try:
            await self.redis.execute_command(
                "FT.CREATE", self.index_name,
                "ON", "HASH",
                "PREFIX", "1", self.key_prefix,
                "SCHEMA",
                "query", "TEXT",
                "answer", "TEXT",
                "tools_used", "TEXT",
                "sources", "TEXT",
                "created_at", "TEXT",
                "embedding", "VECTOR", "HNSW", "6",
                "TYPE", "FLOAT32",
                "DIM", str(self.embedding_dim),
                "DISTANCE_METRIC", "COSINE",
            )
        except Exception as e:
            err_msg = str(e)
            # 索引已存在是正常情况,忽略
            if "Index already exists" in err_msg or "already exists" in err_msg.lower():
                logger.info(f"[L2] 索引 {self.index_name} 已存在,跳过创建")
            else:
                raise

    async def _embed(self, query: str) -> Optional[np.ndarray]:
        """把 query 转成 768 维向量,失败返回 None"""
        try:
            vec = self.embedding.encode(query, normalize_embeddings=True)
            return vec.astype(np.float32)
        except Exception as e:
            logger.warning(f"[L2] embedding 失败: {e}")
            return None

    async def get(self, query: str) -> Optional[dict]:
        """语义查 L2,命中且相似度 ≥ 阈值返回 {answer, tools_used, sources},否则 None"""
        if not self._enabled:
            return None
        try:
            vec = await self._embed(query)
            if vec is None:
                return None
            query_bytes = vec.tobytes()
            results = await self.redis.execute_command(
                "FT.SEARCH", self.index_name,
                "*=>[KNN 1 @embedding $vec AS score]",
                "PARAMS", "2", "vec", query_bytes,
                "SORTBY", "score",
                "LIMIT", "0", "1",
                "RETURN", "4", "answer", "tools_used", "sources", "score",
            )
            if not results or results[0] == 0:
                logger.info(f'[L2] MISS query="{query}"')
                return None
            fields = _parse_search_result(results)
            score = float(fields.get("score", 1.0))
            similarity = 1.0 - score  # cosine distance → similarity
            if similarity < self.threshold:
                logger.info(f'[L2] MISS query="{query}" sim={similarity:.3f} < {self.threshold}')
                return None
            logger.info(f'[L2] HIT  query="{query}" sim={similarity:.3f}')
            return {
                "answer": fields.get("answer", ""),
                "tools_used": json.loads(fields.get("tools_used", "[]")),
                "sources": json.loads(fields.get("sources", "[]")),
            }
        except Exception as e:
            logger.warning(f"[L2] get 异常: {e}")
            return None

    async def put(self, query: str, response: dict) -> None:
        """写 L2(query 向量 + response JSON)"""
        if not self._enabled:
            return
        try:
            vec = await self._embed(query)
            if vec is None:
                return
            key = self.key_prefix + hashlib.md5(query.encode("utf-8")).hexdigest()
            await self.redis.hset(
                key,
                mapping={
                    "query": query,
                    "answer": response.get("answer", ""),
                    "tools_used": json.dumps(response.get("tools_used", []), ensure_ascii=False),
                    "sources": json.dumps(response.get("sources", []), ensure_ascii=False),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "embedding": vec.tobytes(),
                },
            )
            await self.redis.expire(key, self.ttl)
        except Exception as e:
            logger.warning(f"[L2] put 异常: {e}")


def _parse_search_result(results: list) -> dict:
    """FT.SEARCH 返回 list,转成 {field: value} dict"""
    if len(results) < 3:
        return {}
    fields_list = results[2]
    if not isinstance(fields_list, list):
        return {}
    d = {}
    for i in range(0, len(fields_list), 2):
        k = fields_list[i]
        v = fields_list[i + 1] if i + 1 < len(fields_list) else b""
        if isinstance(k, bytes):
            k = k.decode("utf-8", errors="replace")
        if isinstance(v, bytes):
            v = v.decode("utf-8", errors="replace")
        d[k] = v
    return d
```

- [ ] **Step 5:跑测试确认通过**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && python -m pytest tests/test_semantic_cache_init.py -v`
Expected: 2 passed

- [ ] **Step 6:Commit**

```bash
cd D:/python/pythonProject/zhinangyixia-api/ZNYX
git add SupplyChain/cache/semantic_cache.py SupplyChain/tests/conftest.py SupplyChain/tests/test_semantic_cache_init.py
git commit -m "feat(cache): SemanticCache class with init/get/put + integration tests"
```

---

### Task 1.3:SemanticCache 端到端测试(put + get 命中/不命中)

**Files:**
- Create: `SupplyChain/tests/test_semantic_cache_e2e.py`

- [ ] **Step 1:写集成测试**

文件 `SupplyChain/tests/test_semantic_cache_e2e.py`:

```python
"""
SemanticCache 端到端测试:put 一条,get 同 query 命中,get 远义 query 不命中。
需要真实 Redis + 真实 embedding(慢,~5-10s 加载)。
"""
import pytest
from cache.semantic_cache import SemanticCache
from config.config import (
    SEMANTIC_CACHE_TTL, SEMANTIC_CACHE_THRESHOLD,
    SEMANTIC_CACHE_KEY_PREFIX, SEMANTIC_CACHE_INDEX_NAME,
    SEMANTIC_CACHE_EMBEDDING_DIM,
)


@pytest.mark.integration
class TestSemanticCacheE2E:
    async def test_put_then_get_same_query(self, redis_client, embedding_model):
        """put 后 get 相同 query 应该命中"""
        cache = _make_cache(redis_client, embedding_model)
        await cache._ensure_index()
        await cache.put("采购流程是什么", {"answer": "A", "tools_used": ["knowledge_search"], "sources": []})
        result = await cache.get("采购流程是什么")
        assert result is not None
        assert result["answer"] == "A"
        assert result["tools_used"] == ["knowledge_search"]

    async def test_get_paraphrase_query(self, redis_client, embedding_model):
        """put 后 get 近义 query 应该命中(语义匹配)"""
        cache = _make_cache(redis_client, embedding_model)
        await cache._ensure_index()
        await cache.put("采购流程是什么", {"answer": "A", "tools_used": ["knowledge_search"], "sources": []})
        result = await cache.get("采购的流程是怎样的")
        assert result is not None, "近义 query 应该命中"
        assert result["answer"] == "A"

    async def test_get_unrelated_query_miss(self, redis_client, embedding_model):
        """put 后 get 完全无关 query 应该 miss"""
        cache = _make_cache(redis_client, embedding_model)
        await cache._ensure_index()
        await cache.put("采购流程是什么", {"answer": "A", "tools_used": ["knowledge_search"], "sources": []})
        result = await cache.get("今天北京天气怎么样")
        assert result is None, "无关 query 应该 miss"

    async def test_get_empty_cache(self, redis_client, embedding_model):
        """空缓存 get 应该返回 None(不抛错)"""
        cache = _make_cache(redis_client, embedding_model)
        await cache._ensure_index()
        result = await cache.get("随便问问")
        assert result is None

    async def test_get_disabled_returns_none(self, redis_client, embedding_model):
        """_enabled=False 时 get 直接返回 None"""
        cache = _make_cache(redis_client, embedding_model)
        cache._enabled = False
        result = await cache.get("采购流程是什么")
        assert result is None

    async def test_put_disabled_noop(self, redis_client, embedding_model):
        """_enabled=False 时 put 是 no-op"""
        cache = _make_cache(redis_client, embedding_model)
        cache._enabled = False
        await cache.put("采购流程", {"answer": "A", "tools_used": [], "sources": []})
        async for _ in redis_client.scan_iter(match=f"{SEMANTIC_CACHE_KEY_PREFIX}*"):
            pytest.fail("put 不应该写 key")

    async def test_put_respects_ttl(self, redis_client, embedding_model):
        """put 后 key 有 TTL"""
        cache = _make_cache(redis_client, embedding_model)
        await cache._ensure_index()
        await cache.put("采购流程", {"answer": "A", "tools_used": [], "sources": []})
        found = False
        async for key in redis_client.scan_iter(match=f"{SEMANTIC_CACHE_KEY_PREFIX}*"):
            ttl = await redis_client.ttl(key)
            assert 0 < ttl <= SEMANTIC_CACHE_TTL
            found = True
            break
        assert found, "应该有 key 被创建"


def _make_cache(redis_client, embedding_model) -> SemanticCache:
    return SemanticCache(
        redis_client=redis_client,
        embedding_model=embedding_model,
        threshold=SEMANTIC_CACHE_THRESHOLD,
        ttl=SEMANTIC_CACHE_TTL,
        key_prefix=SEMANTIC_CACHE_KEY_PREFIX,
        index_name=SEMANTIC_CACHE_INDEX_NAME,
        embedding_dim=SEMANTIC_CACHE_EMBEDDING_DIM,
    )
```

- [ ] **Step 2:跑测试**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && python -m pytest tests/test_semantic_cache_e2e.py -v -s`
Expected: 7 passed(注意 -s 看到日志)

- [ ] **Step 3:Commit**

```bash
cd D:/python/pythonProject/zhinangyixia-api/ZNYX
git add SupplyChain/tests/test_semantic_cache_e2e.py
git commit -m "test(cache): e2e tests for SemanticCache put/get/threshold/ttl"
```

---

## 阶段 2:Agent 集成

### Task 2.1:SupplyChainAgent.__init__ 加载 embedding + 实例化 cache

**Files:**
- Modify: `SupplyChain/agent/agent_core.py`(顶部 import + `__init__` 末尾)

- [ ] **Step 1:加 import**

在 `agent_core.py` 顶部 import 块后追加:

```python
from sentence_transformers import SentenceTransformer
from config.config import (
    EMBEDDING_MODEL, EMBEDDING_DEVICE,
    REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD,
    SEMANTIC_CACHE_ENABLED, SEMANTIC_CACHE_TTL, SEMANTIC_CACHE_THRESHOLD,
    SEMANTIC_CACHE_KEY_PREFIX, SEMANTIC_CACHE_INDEX_NAME, SEMANTIC_CACHE_EMBEDDING_DIM,
)
import redis.asyncio as redis_async
from cache.semantic_cache import SemanticCache
```

- [ ] **Step 2:在 __init__ 末尾加 embedding + cache 初始化**

在 `print(f"[Agent] Agent创建完成,...")` 那行(`agent_core.py:119`)前插入:

```python
        # ---- 5. 加载 L2 embedding 模型(显式加载,不依赖 ChromaDB 懒加载) ----
        if SEMANTIC_CACHE_ENABLED:
            print("[Agent] 正在加载 L2 embedding 模型...")
            self.embedding_model = SentenceTransformer(EMBEDDING_MODEL, device=EMBEDDING_DEVICE)
            print(f"[Agent] L2 embedding 加载完成: {EMBEDDING_MODEL}")

            # ---- 6. 初始化 L2 语义缓存(对象创建) ----
            print("[Agent] 正在初始化 L2 语义缓存...")
            self.semantic_cache = SemanticCache(
                redis_client=redis_async.Redis(
                    host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, password=REDIS_PASSWORD,
                ),
                embedding_model=self.embedding_model,
                threshold=SEMANTIC_CACHE_THRESHOLD,
                ttl=SEMANTIC_CACHE_TTL,
                key_prefix=SEMANTIC_CACHE_KEY_PREFIX,
                index_name=SEMANTIC_CACHE_INDEX_NAME,
                embedding_dim=SEMANTIC_CACHE_EMBEDDING_DIM,
            )
            print("[Agent] L2 语义缓存对象已创建(_ensure_index 由 rag_api.py 的 lifespan 调用)")
        else:
            print("[Agent] L2 语义缓存已禁用(配置开关)")
            self.semantic_cache = None
```

> **为什么不在 __init__ 里 await _ensure_index**:`__init__` 是同步方法,FastAPI 的 `lifespan` 是 async。`await` 在同步方法里不可用,`asyncio.run` 会嵌套 event loop 报错。改 __init__ 为 async 又会破坏现有调用链。**最干净:__init__ 只创建对象,index 在 lifespan 里 await**。后续 Task 2.3 改 rag_api.py 时一起处理。

- [ ] **Step 3:在 rag_api.py 的 lifespan 里 await _ensure_index**

修改 `SupplyChain/rag_api.py:181-184`:

```python
    # 初始化Agent(加载模型、向量库、工具等)
    global agent
    agent = SupplyChainAgent(verbose=True)
    print("[启动] Agent初始化完成")
```

改为:

```python
    # 初始化Agent(加载模型、向量库、工具等)
    global agent
    agent = SupplyChainAgent(verbose=True)
    # 启动 L2 RediSearch 索引(如果开启了)
    if agent.semantic_cache is not None:
        await agent.semantic_cache._ensure_index()
    print("[启动] Agent初始化完成")
```

- [ ] **Step 4:跑 _is_cacheable 测试,确保没破坏**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && python -m pytest tests/test_is_cacheable.py -v`
Expected: 9 passed

- [ ] **Step 5:验证 import 不报错**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && python -c "from agent.agent_core import SupplyChainAgent; print('import ok')"`
Expected: `import ok`

- [ ] **Step 6:Commit**

```bash
cd D:/python/pythonProject/zhinangyixia-api/ZNYX
git add SupplyChain/agent/agent_core.py SupplyChain/rag_api.py
git commit -m "feat(agent): load embedding and instantiate SemanticCache in __init__"
```

---

### Task 2.2:chat() 加缓存钩子(入口查 + 出口写)

**Files:**
- Modify: `SupplyChain/agent/agent_core.py:161-225`(`chat()` 方法)
- Create: `SupplyChain/tests/test_chat_cache_hook.py`

- [ ] **Step 1:写失败测试(mock SemanticCache)**

文件 `SupplyChain/tests/test_chat_cache_hook.py`:

```python
"""
chat() 缓存钩子测试。用 mock 替换真实的 LLM 调用和 SemanticCache,验证:
- 入口:SemanticCache.get 命中时直接返回 cache_hit=True
- 入口:get miss 时正常调 LLM
- 出口:_is_cacheable=True 时写 SemanticCache
- 出口:_is_cacheable=False 时不写
- LLM 抛错时不写,cache_hit=False
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_semantic_cache():
    """mock SemanticCache 实例"""
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.put = AsyncMock()
    return cache


class TestChatCacheHook:
    async def test_l2_hit_returns_immediately_without_llm(self, mock_semantic_cache):
        """L2 命中时直接返回,不调 LLM"""
        mock_semantic_cache.get.return_value = {
            "answer": "cached answer",
            "tools_used": ["knowledge_search"],
            "sources": [],
        }
        from agent.agent_core import SupplyChainAgent
        agent = SupplyChainAgent.__new__(SupplyChainAgent)
        agent.semantic_cache = mock_semantic_cache
        agent._tools_used = []
        agent.verbose = False
        agent.agent_executor = MagicMock()
        agent.agent_executor.invoke = MagicMock()

        result = await agent.chat("采购流程是什么")

        assert result["answer"] == "cached answer"
        assert result["cache_hit"] is True
        assert result["success"] is True
        agent.agent_executor.invoke.assert_not_called()
        mock_semantic_cache.put.assert_not_called()

    async def test_l2_miss_then_cacheable_writes(self, mock_semantic_cache):
        """L2 miss + 可缓存时,调 LLM 后写 L2"""
        mock_semantic_cache.get.return_value = None
        from agent.agent_core import SupplyChainAgent
        agent = SupplyChainAgent.__new__(SupplyChainAgent)
        agent.semantic_cache = mock_semantic_cache
        agent._tools_used = []
        agent.verbose = False
        agent.agent_executor = MagicMock()
        agent.agent_executor.invoke = MagicMock(return_value={
            "output": "LLM answer",
            "intermediate_steps": [],
        })

        result = await agent.chat("采购流程是什么")

        assert result["answer"] == "LLM answer"
        assert result["cache_hit"] is False
        assert result["success"] is True
        mock_semantic_cache.put.assert_called_once()
        call_args = mock_semantic_cache.put.call_args
        assert call_args[0][0] == "采购流程是什么"
        assert call_args[0][1]["answer"] == "LLM answer"

    async def test_l2_miss_then_not_cacheable_does_not_write(self, mock_semantic_cache):
        """L2 miss + 不可缓存时(inventory_query),不写 L2"""
        mock_semantic_cache.get.return_value = None
        from agent.agent_core import SupplyChainAgent
        from langchain_core.agents import AgentAction
        agent = SupplyChainAgent.__new__(SupplyChainAgent)
        agent.semantic_cache = mock_semantic_cache
        agent._tools_used = []
        agent.verbose = False
        step = (AgentAction(tool="inventory_query", tool_input={"sku_id": "SKU001"}, log=""), "obs")
        agent.agent_executor = MagicMock()
        agent.agent_executor.invoke = MagicMock(return_value={
            "output": "库存查询结果",
            "intermediate_steps": [step],
        })

        result = await agent.chat("SKU001库存多少")

        assert result["cache_hit"] is False
        assert result["tools_used"] == ["inventory_query"]
        mock_semantic_cache.put.assert_not_called()

    async def test_llm_error_does_not_write(self, mock_semantic_cache):
        """LLM 抛错时,写 graceful error,不写 L2,success=False"""
        mock_semantic_cache.get.return_value = None
        from agent.agent_core import SupplyChainAgent
        agent = SupplyChainAgent.__new__(SupplyChainAgent)
        agent.semantic_cache = mock_semantic_cache
        agent._tools_used = []
        agent.verbose = False
        agent.agent_executor = MagicMock()
        agent.agent_executor.invoke = MagicMock(side_effect=Exception("LLM炸了"))

        result = await agent.chat("随便问")

        assert result["success"] is False
        assert result["cache_hit"] is False
        assert "抱歉" in result["answer"]
        mock_semantic_cache.put.assert_not_called()
```

- [ ] **Step 2:跑测试确认失败**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && python -m pytest tests/test_chat_cache_hook.py -v`
Expected: 4 FAIL(因为 `chat()` 还是同步的,也没调 cache)

- [ ] **Step 3:重写 chat() 为 async + 加缓存钩子**

替换 `agent_core.py:161-225` 整个 `chat()` 方法:

```python
    async def chat(self, query: str) -> dict:
        """
        与Agent对话的主接口(async,因 L2 缓存是异步)。

        完整调用链路:
        1. 查 L2 缓存(SemanticCache.get)
        2. 命中 → 直接返回 cache_hit=True
        3. 未命中 → 调 LLM(原有逻辑)
        4. LLM 成功 + _is_cacheable → 写 L2
        5. LLM 失败 → 返回 graceful error,不写 L2

        返回 dict 始终包含 5 字段:
            success, answer, tools_used, sources, cache_hit
        """
        # 1. 入口:查 L2
        if self.semantic_cache is not None:
            cached = await self.semantic_cache.get(query)
            if cached:
                return {
                    "success": True,
                    "answer": cached["answer"],
                    "tools_used": cached["tools_used"],
                    "sources": cached["sources"],
                    "cache_hit": True,
                }

        # 2. 原有 LLM 调用逻辑
        self._tools_used = []

        try:
            result = self.agent_executor.invoke({"input": query})

            intermediate_steps = result.get("intermediate_steps", [])
            tools_used = []
            sources = []

            for step in intermediate_steps:
                action, observation = step
                tool_name = action.tool
                if tool_name not in tools_used:
                    tools_used.append(tool_name)
                if tool_name == "knowledge_search" and "来源:" in observation:
                    import re
                    source_matches = re.findall(r"来源: ([^|]+)", observation)
                    for s in source_matches:
                        if s.strip() not in sources:
                            sources.append(s.strip())

            response = {
                "answer": result.get("output", ""),
                "tools_used": tools_used,
                "sources": sources,
            }

            # 3. 出口:写 L2(仅当可缓存)
            if self.semantic_cache is not None and self._is_cacheable(response):
                await self.semantic_cache.put(query, response)

            return {**response, "success": True, "cache_hit": False}

        except Exception as e:
            error_msg = str(e)
            print(f"[Agent] 对话出错: {error_msg}")
            return {
                "success": False,
                "answer": f"抱歉,处理您的问题时出现了错误:{error_msg}。请稍后重试或换一种方式提问。",
                "tools_used": [],
                "sources": [],
                "cache_hit": False,
            }
```

> **关键变更**:
> - 方法签名 `chat()` → `async def chat()`
> - 入口加 `if self.semantic_cache: cached = await get()`
> - 出口加 `if cacheable: await put()`
> - 返回 dict 加 `success` 和 `cache_hit` 字段

- [ ] **Step 4:验证 chat 是 async,chat_stream 不受影响**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && python -c "import inspect; from agent.agent_core import SupplyChainAgent; print('chat is coroutine:', inspect.iscoroutinefunction(SupplyChainAgent.chat)); print('chat_stream is coroutine:', inspect.iscoroutinefunction(SupplyChainAgent.chat_stream))"`
Expected: `chat is coroutine: True` / `chat_stream is coroutine: False`

- [ ] **Step 5:跑所有测试**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && python -m pytest tests/ -v`
Expected: 9 (test_is_cacheable) + 2 (init) + 7 (e2e) + 4 (chat_hook) = 22 passed

- [ ] **Step 6:Commit**

```bash
cd D:/python/pythonProject/zhinangyixia-api/ZNYX
git add SupplyChain/agent/agent_core.py SupplyChain/tests/test_chat_cache_hook.py
git commit -m "feat(agent): chat() async + L2 cache hooks (read/write)"
```

---

### Task 2.3:rag_api.py 适配 + AskResponse 加 cache_hit

**Files:**
- Modify: `SupplyChain/rag_api.py:53-59`(`AskResponse` 类)
- Modify: `SupplyChain/rag_api.py:223-247`(`/ask` 路由)

- [ ] **Step 1:改 AskResponse**

替换 `rag_api.py:53-59`:

```python
class AskResponse(BaseModel):
    """Agent问答响应模型"""
    success: bool              # 是否成功
    query: str                 # 用户的问题
    answer: str                # Agent的回答
    tools_used: list = []      # 使用的工具列表
    sources: list = []         # 知识库来源列表
    cache_hit: bool = False    # L2 语义缓存是否命中(新)
```

- [ ] **Step 2:改 /ask 路由 await chat**

替换 `rag_api.py:223-247` 的 `ask` 函数:

```python
@app.post("/ask", response_model=AskResponse, summary="Agent问答接口")
async def ask(request: AskRequest):
    """
    Agent主入口。接收用户的自然语言问题,Agent自动决定调用哪些工具,
    返回综合性的补货建议。

    请求示例:
        POST /ask
        {"query": "SKU001的库存够不够?要不要补货?"}
    """
    if not agent:
        raise HTTPException(status_code=503, detail="Agent未初始化,请稍后重试")

    if not request.query.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    # 调用Agent获取回答(chat 现在是 async)
    result = await agent.chat(request.query)

    return AskResponse(
        success=result["success"],
        query=request.query,
        answer=result["answer"],
        tools_used=result["tools_used"],
        sources=result["sources"],
        cache_hit=result["cache_hit"],
    )
```

- [ ] **Step 3:验证 import + 路由可达**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && python -c "from rag_api import app, AskResponse; print('routes:', [r.path for r in app.routes if hasattr(r, 'path')])"`
Expected: 输出包含 `/ask`、`/inventory`、`/health` 等路由,无 ImportError

- [ ] **Step 4:跑现有所有测试**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && python -m pytest tests/ -v`
Expected: 22 passed(没破坏任何东西)

- [ ] **Step 5:Commit**

```bash
cd D:/python/pythonProject/zhinangyixia-api/ZNYX
git add SupplyChain/rag_api.py
git commit -m "feat(api): AskResponse adds cache_hit; /ask awaits async chat"
```

---

## 阶段 3:跨语言同步(Java 端连带变更)

### Task 3.1:Java RagAnswerVO 加 cacheHit 字段

**Files:**
- Modify: `D:/BaiduNetdiskDownload/SpringCloud微服务—资料/day02-Docker/资料/hmall/cart-service/cart-api/src/main/java/com/hmall/cart/api/vo/RagAnswerVO.java`

> **重要**:Java 端代码路径以实际为准,Task 3.1 第一步是 Read 确认。

- [ ] **Step 1:读现有 RagAnswerVO 确认路径和字段**

用 Read 工具读文件,确认:
- 类在 `com.hmall.cart.api.vo` 包
- 现有 5 个字段:`success`, `query`, `answer`, `tools_used`, `sources`
- 用 `@Data` 或手写 getter/setter

- [ ] **Step 2:加 cacheHit 字段**

在 RagAnswerVO 类的字段列表末尾加:

```java
    @JsonProperty("cache_hit")
    private Boolean cacheHit = false;
```

如果用了 Lombok `@Data`,getter/setter 自动生成;如果手写,需要补 `getCacheHit()` / `setCacheHit()`。

**关于 `@JsonProperty("cache_hit")`**:Python 端 Pydantic 默认输出 `cache_hit`(snake_case)。Jackson 序列化时默认按 Java 字段名(`cacheHit`)。注解明确告诉 Jackson "序列化/反序列化时用 cache_hit 这个 JSON 名",这样双向一致。

- [ ] **Step 3:验证编译**

Run: `cd D:/BaiduNetdiskDownload/SpringCloud微服务—资料/day02-Docker/资料/hmall && mvn -pl cart-api -am compile -DskipTests`
Expected: BUILD SUCCESS

- [ ] **Step 4:Commit(Java 端 Git)**

```bash
cd D:/BaiduNetdiskDownload/SpringCloud微服务—资料/day02-Docker/资料/hmall
git add cart-api/src/main/java/com/hmall/cart/api/vo/RagAnswerVO.java
git commit -m "feat(vo): RagAnswerVO adds cacheHit field with @JsonProperty mapping"
```

---

### Task 3.2:Java RagQueryServiceImpl 透传 cacheHit

**Files:**
- Modify: `D:/BaiduNetdiskDownload/SpringCloud微服务—资料/day02-Docker/资料/hmall/cart-service/cart-impl/src/main/java/com/hmall/cart/service/impl/RagQueryServiceImpl.java`

- [ ] **Step 1:读现有 RagQueryServiceImpl 确认结构**

用 Read 工具读文件,找到:
- L1 命中分支(从 Redis 取到非 null 的位置)
- L1 miss 调 Feign 的位置(类似 `ragClient.ask(...)`)
- return RagAnswerVO 的位置

- [ ] **Step 2:L1 命中时填 cacheHit=true**

L1 命中分支里,在 return RagAnswerVO 前,设置:

```java
        vo.setCacheHit(true);
```

- [ ] **Step 3:L1 miss → Feign 拿到响应后透传**

L1 miss 调 Feign 后(类似 `RagAnswerVO vo = ragClient.ask(...)`),Python 已经填了 cacheHit(可能为 true 或 false)。**不需要再 setCacheHit,直接用 vo 即可**。

如果担心 Python 旧版本不填 cacheHit,加防御:

```java
        if (vo.getCacheHit() == null) {
            vo.setCacheHit(false);
        }
```

- [ ] **Step 4:验证编译**

Run: `cd D:/BaiduNetdiskDownload/SpringCloud微服务—资料/day02-Docker/资料/hmall && mvn -pl cart-impl -am compile -DskipTests`
Expected: BUILD SUCCESS

- [ ] **Step 5:Commit(Java 端 Git)**

```bash
cd D:/BaiduNetdiskDownload/SpringCloud微服务—资料/day02-Docker/资料/hmall
git add cart-impl/src/main/java/com/hmall/cart/service/impl/RagQueryServiceImpl.java
git commit -m "feat(service): RagQueryServiceImpl sets/transparently passes cacheHit"
```

---

## 阶段 4:端到端验证

### Task 4.1:启动 supplychain-rag,观察启动日志

- [ ] **Step 1:跑全测试,确认没破坏**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && python -m pytest tests/ -v`
Expected: 22 passed

- [ ] **Step 2:启动服务**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && uvicorn rag_api:app --host 0.0.0.0 --port 8001`
Expected: 启动日志按顺序包含:
```
[Agent] 正在加载 L2 embedding 模型...
[Agent] L2 embedding 加载完成: moka-ai/m3e-base
[Agent] 正在初始化 L2 语义缓存...
[Agent] L2 语义缓存对象已创建(_ensure_index 由 rag_api.py 的 lifespan 调用)
[启动] Agent初始化完成
✅ 服务启动完成!
```

- [ ] **Step 3:健康检查**

Run: `curl http://localhost:8001/health`
Expected: `{"status":"ok","total_passages":N}`

- [ ] **Step 4:关掉服务**

Ctrl+C 关闭 uvicorn。

---

### Task 4.2:冷启动 MISS + 第二次 HIT 验证

- [ ] **Step 1:启动服务**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && uvicorn rag_api:app --host 0.0.0.0 --port 8001`
Expected: 启动成功(同 4.1)

- [ ] **Step 2:第一次问(冷启动,L2 miss)**

Run:
```bash
curl -X POST http://localhost:8001/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"采购流程是什么"}'
```
Expected:
- HTTP 200
- 响应体 `cache_hit: false`
- 服务端日志: `[L2] MISS query="采购流程是什么"`

- [ ] **Step 3:验证 Redis 里有 key**

Run: `redis-cli -h 192.168.203.129 -p 6379 -n 3 KEYS "ragcache:*"`
Expected: 1 个 key(形如 `ragcache:abc123...`)

- [ ] **Step 4:近义 query 再问(L2 hit)**

Run:
```bash
curl -X POST http://localhost:8001/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"采购的流程是怎样的"}'
```
Expected:
- HTTP 200
- 响应体 `cache_hit: true`
- 服务端日志: `[L2] HIT  query="采购的流程是怎样的" sim=0.XX`(XX ≥ 0.88)

- [ ] **Step 5:无关 query(L2 miss)**

Run:
```bash
curl -X POST http://localhost:8001/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"今天北京天气怎么样"}'
```
Expected:
- `cache_hit: false`
- 日志: `[L2] MISS ... sim=0.XX`(XX < 0.88,通常是 0.3-0.5)

- [ ] **Step 6:关掉服务**

Ctrl+C 关闭。

---

### Task 4.3:降级验证(Redis 不可达时 fail-open)

- [ ] **Step 1:临时把 redis host 改成错误地址**

用编辑器打开 `SupplyChain/config/modelConfig.yaml`,把 `redis.host` 改成 `"127.0.0.9999"`(错误地址,让连接超时)。

- [ ] **Step 2:启动服务**

Run: `cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain && uvicorn rag_api:app --host 0.0.0.0 --port 8001`
Expected: 启动**可能**失败(因为 `_ensure_index` 启动时阻塞等 Redis)。

> **实际情况待实施时确认**。如果 fail-fast(启动失败),降级验证改用:服务启动后临时把 redis kill/重 host。如果 fail-open(只 warn),L2 不可用,LLM 正常,降级就自然验证了。

- [ ] **Step 3:验证 L2 异常时 LLM 仍正常**

Run:
```bash
curl -X POST http://localhost:8001/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"采购流程是什么"}'
```
Expected:
- HTTP 200(不是 5xx)
- `cache_hit: false`
- 日志中有 `[L2] get 异常: ...` 之类的 warn

- [ ] **Step 4:恢复 redis host**

把 `modelConfig.yaml` 的 `redis.host` 改回 `"192.168.203.129"`。

---

## 总结

| 阶段 | Task 数 | Commit 数 | 关键产出 |
|------|---------|-----------|---------|
| 0 基础设施 | 4 | 4 | redis 依赖、pytest、配置加载 |
| 1 SemanticCache | 3 | 3 | L2 缓存类(类+init+e2e 测试) |
| 2 Agent 集成 | 3 | 3 | chat() 加钩子、AskResponse 加字段 |
| 3 Java 端 | 2 | 2 | cacheHit 字段 + 透传 |
| 4 验证 | 3 | 0(纯验证) | 启动 + MISS/HIT + 降级 |
| **合计** | **15** | **12** | |

**关键不变量(实施时守住)**:
- L2 跟 L1 完全独立:Python 不管 L1,Java 不管 L2
- 启动 fail-fast(Redis/embedding 加载失败服务不启动)
- 运行时 fail-open(任何 L2 异常 → log.warn → 跳过)
- `chat()` 始终返回 `{success, answer, tools_used, sources, cache_hit}` 5 字段
- Java 端 `RagAnswerVO.cacheHit` 必须加,否则 L2 命中对用户不可见

**风险点(实施时盯住)**:
- m3e-base 加载慢(5-10s)和 400MB 内存 — 已写进 spec 风险清单
- Java 端代码路径要核对实际文件位置 — Task 3.1/3.2 第一步是 Read 确认
- 启动时 `_ensure_index` 阻塞 event loop — 当前实现 OK,后续可优化为后台任务
- `__init__` 同步方法不能 await,`_ensure_index` 移到 lifespan — 已处理(Task 2.1)
- 降级验证(Task 4.3)的具体行为取决于实现细节,先做,失败再调整
