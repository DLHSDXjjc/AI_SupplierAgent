# Python 端 L2 语义匹配缓存 — 设计

- **作者**: 设计与用户协作产出
- **日期**: 2026-08-03
- **状态**: 待用户 review

## 1. 背景与目标

L1(Java 端 md5 精确缓存)已写完,等启动验证。L1 的局限是**精确匹配**——同义改写、补词、近义词替换都 miss,依然会调 Python。L2 补这一段:**用 embedding + RediSearch KNN 做语义级匹配**,相同/相近语义的 query 直接返回缓存响应,不再调 LLM。

目标:
- 减少 DeepSeek 调用,降低 LLM 成本
- 缩短相似问法的响应延迟(从 4-8s 降到 60-220ms)
- L1 + L2 形成完整二级缓存:精确→语义→LLM

非目标(本 spec 不做):
- Java 端 L1 启动验证(另一条线)
- 跨用户/跨租户的个性化缓存策略
- 缓存预热脚本(冷启动靠 LLM 自然写入)
- 替换现有 ChromaDB 检索路径(语义缓存与知识库检索是两件事)

## 2. 7 个关键决策

| # | 决策点 | 选择 |
|---|--------|------|
| 1 | 缓存读写位置 | `agent.chat()` 入口/出口 |
| 2 | embedding 模型 | 复用现有 `sentence-transformers` 加载的 `m3e-base` |
| 3 | 可缓存规则 | 跟 L1 一致:`success ∧ answer非空 ∧ tools_used ⊆ {knowledge_search}`(空集合算子集) |
| 4 | cosine 阈值 | **0.88**(比 memory 原 0.92 宽松,中文同义改写容错更高) |
| 5 | cache 标记 | `AskResponse` 加 `cache_hit: bool = False` |
| 6 | 降级策略 | fail-open(任何 L2 异常 → log.warn → 跳过 L2 走 LLM) |
| 7 | L2 hit 写回 | 不写回(只读,L2 增长只来自"miss → LLM → 可缓存 → 写 L2"这一条) |

实现路径:**方案 2 — 独立 `SupplyChain/cache/semantic_cache.py`,`agent_core.py` 在 `__init__` 实例化,`chat()` 入口/出口调 `self.cache.get/put`**。

## 3. 文件改动清单

| 路径 | 操作 | 说明 |
|------|------|------|
| `SupplyChain/cache/__init__.py` | 新建 | 空文件,让 `cache` 是个 package |
| `SupplyChain/cache/semantic_cache.py` | 新建 | `SemanticCache` 类,负责 L2 全部读/写 |
| `SupplyChain/modelConfig.yaml` | 改 | 加 `redis:` 和 `semantic_cache:` 段(**本地文件,有 DeepSeek key,不入 git**) |
| `SupplyChain/modelConfig.example.yaml` | 新建 | 模板,不含 `api_key`(`modelConfig.yaml` 在 `.gitignore` 里) |
| `SupplyChain/config/config.py` | 改 | 加 `REDIS_*` 和 `SEMANTIC_CACHE_*` 全局变量 |
| `SupplyChain/agent/agent_core.py` | 改 | `__init__` 实例化 `self.semantic_cache`,`chat()` 入口/出口嵌入缓存钩子,加私有 `_is_cacheable(result)` 方法 |
| `SupplyChain/rag_api.py` | 改 | `AskResponse` 加 `cache_hit: bool = False` 字段;修复 `success` 写死 True 的 bug |
| `SupplyChain/requirements.txt` | 改 | 加 `redis>=5.0.0` |
| `hmall/cart-service/.../vo/RagAnswerVO.java` | **改(连带)** | 加 `cacheHit: Boolean` 字段 + getter/setter,Jackson 默认忽略未匹配字段,**必须加**否则 Java 端永远拿不到 |
| `hmall/cart-service/.../service/impl/RagQueryServiceImpl.java` | **改(连带)** | L1 命中时填 `cacheHit=true`;Feign 拿到 Python 响应后,把 Python 的 `cacheHit` 透传(只覆盖 L1 miss 分支) |

> **连带变更必须做**。如果 Java 端不改 `RagAnswerVO`,Jackson 反序列化 Python 响应时会静默忽略 `cache_hit` 字段,Java 端 cacheHit 永远为 null,等于"用户看不见 L2 命中"。

## 4. 组件职责

### 4.1 `SemanticCache`(新)

```python
class SemanticCache:
    def __init__(self, redis_client, embedding_model, threshold, ttl, key_prefix, index_name):
        # 启动时:redis_client / embedding_model 已经准备好
        # 启动时:FT.CREATE 创建 RediSearch 索引(若已存在则忽略)
        ...

    async def get(self, query: str) -> Optional[dict]:
        """返回 {answer, tools_used, sources, cache_hit=True} 或 None"""

    async def put(self, query: str, response: dict) -> None:
        """写 Redis:query 向量 + response JSON"""
```

**全部异常 fail-open**:`get/put` 内部 try/except,任何异常 log.warn,`get` 返回 None,`put` 静默丢弃。

### 4.2 `SupplyChainAgent`(改)

```python
def __init__(self, verbose=True):
    ...
    # L2 启动时显式加载 embedding(不复用 ChromaDB 的懒加载,避免冷启动首次查询时阻塞)
    self.embedding_model = SentenceTransformer(EMBEDDING_MODEL, device=EMBEDDING_DEVICE)
    self.semantic_cache = SemanticCache(
        redis_client=redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, password=REDIS_PASSWORD),
        embedding_model=self.embedding_model,
        threshold=SEMANTIC_CACHE_THRESHOLD,
        ttl=SEMANTIC_CACHE_TTL,
        key_prefix=SEMANTIC_CACHE_KEY_PREFIX,
        index_name=SEMANTIC_CACHE_INDEX_NAME,
    )
    ...

def chat(self, query: str) -> dict:
    # 1. 入口:查 L2
    cached = await self.semantic_cache.get(query)
    if cached:
        return {**cached, "success": True, "cache_hit": True}

    # 2. 原有 LLM 调用逻辑(保持不变)
    self._tools_used = []
    try:
        result = self.agent_executor.invoke({"input": query})
        ...
        response = {"answer": ..., "tools_used": ..., "sources": ...}

        # 3. 出口:写 L2(仅当可缓存)
        if self._is_cacheable(response):
            await self.semantic_cache.put(query, response)
        return {**response, "success": True, "cache_hit": False}

    except Exception as e:
        return {"answer": f"抱歉...{e}", "tools_used": [], "sources": [], "success": False, "cache_hit": False}

def _is_cacheable(self, response: dict) -> bool:
    """跟 L1 一致:success ∧ answer非空 ∧ tools_used ⊆ {knowledge_search}"""
    if not response.get("success"):
        return False
    if not response.get("answer"):
        return False
    tools = set(response.get("tools_used", []))
    return tools.issubset({"knowledge_search"})
```

> **设计意图**:`chat()` 始终返回 5 字段 dict `{success, answer, tools_used, sources, cache_hit}`,`success` 和 `cache_hit` 始终是 bool(不是 None)。这样 `AskResponse` 直接透传,不再有写死 `success=True` 的 bug。

### 4.3 `AskResponse`(改)

```python
class AskResponse(BaseModel):
    success: bool
    query: str
    answer: str
    tools_used: list = []
    sources: list = []
    cache_hit: bool = False  # 新增
```

**`/ask` 路由直接透传 `chat()` 返回值**:
```python
return AskResponse(
    success=result["success"],          # chat() 显式声明,不再写死 True
    query=request.query,
    answer=result["answer"],
    tools_used=result["tools_used"],
    sources=result["sources"],
    cache_hit=result["cache_hit"],
)
```
这样同时修了 `success` 写死 True 的 bug:L2 hit / LLM 成功 → `success=True`;LLM 异常 → `success=False`。

## 5. 配置

### `modelConfig.yaml` 新增段(本地,不入 git)

```yaml
redis:
  host: "192.168.203.129"
  port: 6379
  db: 3                # 跟 L1 共享 db=3
  # password: ""       # 暂无密码

semantic_cache:
  enabled: true        # 一键开关,关闭时 semantic_cache 退化为 no-op
  ttl: 21600           # 6h,跟 L1 对齐
  threshold: 0.88      # cosine 阈值
  key_prefix: "ragcache:"
  index_name: "rag_semantic_cache"
  embedding_dim: 768   # 跟现有 m3e-base 一致
```

### `modelConfig.example.yaml`(新建,入 git)

跟 `modelConfig.yaml` 结构相同,但 `deepseek.api_key` 写 `""` 或注释说明,确保 git 提交时不会泄漏。

### `config.py` 新增全局变量

```python
REDIS_HOST = _config["redis"]["host"]
REDIS_PORT = _config["redis"]["port"]
REDIS_DB = _config["redis"]["db"]
REDIS_PASSWORD = _config["redis"].get("password") or None

SEMANTIC_CACHE_ENABLED = _config["semantic_cache"]["enabled"]
SEMANTIC_CACHE_TTL = _config["semantic_cache"]["ttl"]
SEMANTIC_CACHE_THRESHOLD = _config["semantic_cache"]["threshold"]
SEMANTIC_CACHE_KEY_PREFIX = _config["semantic_cache"]["key_prefix"]
SEMANTIC_CACHE_INDEX_NAME = _config["semantic_cache"]["index_name"]
SEMANTIC_CACHE_EMBEDDING_DIM = _config["semantic_cache"]["embedding_dim"]
```

## 6. 数据流

### 6.1 读路径(L2 hit)

```
[Feign] POST /ask { query }
   ↓
[rag_api.py] AskRequest(query)
   ↓
[agent.chat(query)]
   ↓
[SemanticCache.get(query)]
   ├─ embed(query) → 768 维向量
   ├─ RediSearch KNN top-1
   ├─ 相似度 ≥ 0.88 → 返回 {answer, tools_used, sources}
   └─ 否则返回 None
   ↓
hit → chat() 早返 {..., "cache_hit": True}
   ↓
[rag_api.py] AskResponse(success=True, cache_hit=True, ...)
   ↓
[Java Feign] RagAnswerVO
   ↓
[Java RagQueryServiceImpl] 此时 L1 已经 miss(否则不会走到 Feign);按 L1 白名单决定是否回写 L1
   ├─ tools_used ⊆ {knowledge_search} → 用本 query 算 md5 写 L1
   └─ 否则不写 L1
   ↓
返回前端
```

### 6.2 读路径(L2 miss → LLM → 写 L2)

```
L2 miss → agent_executor.invoke() → LLM + 工具
   ↓
result = {answer, tools_used, sources}
   ↓
_is_cacheable(result)?
   ├─ YES → await self.semantic_cache.put(query, result)
   └─ NO  → 跳过
   ↓
返回 {..., "cache_hit": False}
```

### 6.3 异常路径(降级)

| 异常点 | 行为 | 上层感知 |
|--------|------|---------|
| 启动时 Redis ping 失败 | 抛 RuntimeError,服务**不启动** | 用户看启动日志 |
| 启动时 embedding 模型加载失败 | 抛 RuntimeError,服务**不启动** | 同上 |
| 启动时 RediSearch 索引不存在 | `FT.CREATE` 自动创建 | 首次冷启动 INFO |
| 运行时 `get()` 任何异常 | log.warn,返回 None | 走 LLM,正常返回 |
| 运行时 `put()` 任何异常 | log.warn,静默丢弃 | 正常返回 |
| LLM 抛错 | 现有 try/except,graceful error | `cache_hit=False`,不写 L2 |

启动 fail-fast 是**故意的** —— 启动时 embedding 都没加载,意味着 L2 配置坏了,服务还跑没意义。

## 7. 接口契约(跨语言 cache_hit 字段约定)

**Python 端 (`AskResponse`)**:
- `cache_hit: bool = False`
- `True` = 本次响应是 L2 语义缓存命中,没调 LLM
- `False` = 本次响应是 LLM 实时生成(或 LLM 失败后的 graceful error)

**Java 端 (`RagAnswerVO`)** 必须同步加 `cacheHit: Boolean` 字段:
- L1 命中时:Java 自己填 `cacheHit = true`(已是 L1 命中)
- L1 miss + L2 hit(Feign 拿到 Python 响应,`cacheHit=true`):Java 透传
- L1 miss + L2 miss + LLM(Feign 拿到 Python 响应,`cacheHit=false`):Java 透传
- 透传位置:`RagQueryServiceImpl` 在 L1 miss 走 Feign 的分支,return 前用 Python 响应的 `cacheHit` 覆盖

> **不修改 Java 端 RagAnswerVO = L2 命中对用户不可见**。这是强制连带变更。

## 8. 测试策略

### 8.1 单元测试(脱离 Redis,快)

| 测试 | 覆盖点 |
|------|--------|
| `test_embed_query.py` | m3e-base 输出 768 维向量,值在合理范围 |
| `test_is_cacheable.py` | 8 种情况:有/无 knowledge_search、多工具混合、空 tools_used、answer 空、success=False 等 |
| `test_semantic_cache_failopen.py` | mock redis 抛 `ConnectionError`,验证 `get` 返回 None、`put` 不抛 |

### 8.2 集成测试(需本地 Redis)

| 测试 | 验证点 |
|------|--------|
| `test_semantic_cache_e2e.py` | put {query:"采购流程", answer:"..."},get 近义 query "采购的流程是怎样的?" 验证命中 |
| `test_threshold_filter.py` | put "采购流程",get "今天天气如何",验证不命中 |
| `test_ttl_expiry.py` | put 一条,等 TTL 过后 get,验证 None |

### 8.3 冒烟测试(用现有 supplychain-rag)

见第 9 节。

## 9. 验证步骤(从 0 到 L2 跑通)

```bash
# 0. 准备
cd D:/python/pythonProject/zhinangyixia-api/ZNYX/SupplyChain
pip install -r requirements.txt          # 新增 redis>=5.0.0
# Java 端按第 7 节改 RagAnswerVO + RagQueryServiceImpl,重启 cart-service

# 1. 启动 supplychain-rag,观察启动日志
uvicorn rag_api:app --host 0.0.0.0 --port 8001
# 期望看到(顺序):
#   [Cache] 正在初始化 SemanticCache...
#   [Cache] Redis 连接成功: 192.168.203.129:6379/3
#   [Cache] RediSearch 索引 rag_semantic_cache 已就绪
#   [Cache] embedding 模型加载完成: moka-ai/m3e-base
#   [Cache] SemanticCache 初始化完成

# 2. 冷启动:第一次问,L2 miss,走 LLM
curl -X POST http://localhost:8001/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"采购流程是什么"}'
# 期望:
#   响应里 cache_hit: false
#   日志: [L2] MISS query="采购流程是什么"
#   redis-cli -h 192.168.203.129 -n 3 KEYS "ragcache:*"  →  1 个新 key

# 3. 改个近义问法,L2 应命中
curl -X POST http://localhost:8001/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"采购的流程是怎样的"}'
# 期望:
#   响应里 cache_hit: true  ← L2 命中
#   日志: [L2] HIT  query="采购的流程是怎样的" sim=0.91
#   没有新的 LLM 调用

# 4. Java 端 Feign 验证
# 走 Nacos 调到 supplychain-rag,期望 Java 端 RagAnswerVO.cacheHit=true 被透传

# 5. 降级验证
# 临时把 config 里的 redis.host 改成错误地址(或 iptables 阻断)→ 重启 service
# → curl /ask 仍正常返回(cache_hit=false),日志 [L2] 异常 warn
```

## 10. 资源 / 性能

- m3e-base 加载到内存约 **400MB**,启动 +5~10s
- 每次 query embedding:50-200ms(CPU)/ 10-30ms(GPU)
- RediSearch KNN top-1:5-20ms
- L2 命中总延迟:**60-220ms**(比 LLM 4-8s 快 20-100 倍)
- L2 miss 时多一次 embedding 开销(可接受)

## 11. 风险清单

| 风险 | 缓解 |
|------|------|
| ChromaDB embedding 与 L2 embedding 加载时互相争内存(虽然 ChromaDB 是懒加载) | 监控启动期内存,400MB 峰值;不够时把 L2 改 lazy-load |
| RediSearch 索引随时间变大,KNN 变慢 | 6h TTL 自然淘汰;Redis maxmemory-policy 建议 `allkeys-lru` |
| 用户 query 灌入胡话导致 L2 被污染 | `_is_cacheable` 已经过滤,只缓存语义匹配的有效回答;胡话 query 因为没有命中已有缓存,会调 LLM 拿响应,只要响应本身可缓存就会写 |
| Java 端忘了改 cache_hit 字段 | spec 第 7 节明确连带变更,plan 阶段会写 step;不上 git hook 强校验 |
| 0.88 阈值可能误判 | 上线后看 HIT 样本,人工 spot check 5-10 条;误判多再调到 0.92 |
| m3e-base 在某些边缘 query 上 embedding 质量不高 | 同上,看 log 调阈值或换模型 |

## 12. 后续(本 spec 不做)

- [ ] L2 命中率的 Grafana 指标(L2 HIT/MISS 计数器)
- [ ] 阈值自适应(根据最近 100 次 HIT 的相似度分布自动调)
- [ ] L2 内容运营后台(看缓存里有什么 query、能不能手动 invalidate)
- [ ] Java 端 L1 启动验证(独立任务)

## 13. 关联

- [[rag-double-cache-plan]] — L1 + L2 整体进度
- L1 spec 待补充
- L1 Java 代码: `D:/BaiduNetdiskDownload/SpringCloud微服务—资料/day02-Docker/资料/hmall/cart-service/...`

---

## 14. 修订记录

### 2026-08-03 实施中发现的两处 spec 偏差

实施时跑通测试发现两处与原 spec 不符的地方,已修正:

#### 14.1 Redis db: 3 → 0 → 不限(改用 vectorset 后回 3)
- **原 spec**:`redis.db: 3`(跟 L1 共享)
- **首次修正**:RediSearch 限制索引只能在 db=0,改成 `db: 0`,L1 在 Java 端独立 db=3
- **二次修正**:改用 Redis 8 vectorset 后(见 14.2),db 不再受限制,**回 db=3**(跟 L1 共享,key 前缀隔离)
- 现状:`modelConfig.yaml` 的 `redis.db: 3`

#### 14.2 向量存储: RediSearch HNSW → Redis 8 vectorset
- **原 spec**:用 RediSearch HNSW 索引做 KNN
- **问题**:RediSearch 8.6 KNN 语法 `*=>[KNN 1 @embedding $vec AS score]` 在当前环境(redis 8.6.2 + RediSearch 80600 + redis-py 8.1)报 `Syntax error at offset 1 near >[`,试了 5 个变体(去掉 AS score、用 VECTOR_RANGE、改用 RESP2、改用高层 SearchIndex API)都不工作
- **替代方案**:Redis 8 原生 `vectorset`(ver=1)
  - 写:`VADD key VALUES dim v1 v2 ... element`
  - 读:`VSIM key VALUES dim v1 v2 ... WITHSCORES`
  - 实测:5 个 query 测,同义改写 "采购流程" vs "采购的流程" similarity=0.9956,远超 0.88 阈值
  - 优点:不用建索引、不用 db=0 限制、不受 RESP 协议影响
- **现状实现**:
  - 删了 `_ensure_index` 方法(不再需要建索引)
  - `get()` 用 `VSIM WITHSCORES` 查 top-1,score 是 cosine similarity(0-1)
  - `put()` 用 `VADD` 写向量 + 单独 HASH(`{vector_key}:meta` 后缀)存 query/answer/tools_used/sources
- **spec 影响**:
  - 第 5 节配置 `index_name` 字段作废,改 `vector_key`(vectorset 的 key)
  - 第 4.1 节 `_ensure_index` 方法描述作废
  - 第 6 节 score 语义从"cosine distance(越小越近)"改为"cosine similarity(越大越近)"
  - 第 7 节 Java 端 cacheHit 字段**不变**(语义都是"是否来自缓存")

### 这次变更没动:
- 7 个关键决策(位置/embedding/规则/阈值/cache_hit/降级/L2 hit 不写回)
- L1 ↔ L2 独立性原则
- 跨语言 cache_hit 字段约定
