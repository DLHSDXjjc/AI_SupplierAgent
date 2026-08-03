"""
L2 语义匹配缓存 —— 基于 Redis 8 vectorset。

【职责】
- 读:query → embedding → VSIM top-1 → 相似度 ≥ 阈值返回缓存
- 写:query + response → embedding → VADD 写向量 + HSET 写 metadata
- 失败一律 fail-open(异常 → log.warn → 跳过)

【Redis 存储结构】
vectorset key: "ragcache:vectors"
  element: md5(query)
  value: 768 维 float32 向量

HASH key: "ragcache:{md5(query)}" (跟 element 同名,但作 HASH 用)
  query: 原始 query 文本
  answer: 缓存的 answer
  tools_used: JSON 列表字符串
  sources: JSON 列表字符串
  created_at: ISO 8601 时间戳
  TTL: 6h

【score 语义】
VSIM WITHSCORES 返回的是 cosine similarity(0-1,越大越近)
阈值判断:score < threshold → miss
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
        vector_key: str,
        embedding_dim: int,
    ):
        self.redis = redis_client
        self.embedding = embedding_model
        self.threshold = threshold
        self.ttl = ttl
        self.key_prefix = key_prefix
        self.vector_key = vector_key
        self.embedding_dim = embedding_dim
        self._enabled = True

    async def _embed(self, query: str) -> Optional[np.ndarray]:
        """把 query 转成 768 维向量,失败返回 None"""
        try:
            vec = self.embedding.encode(query, normalize_embeddings=True)
            return vec.astype(np.float32)
        except Exception as e:
            logger.warning(f"[L2] embedding 失败: {e}")
            return None

    def _query_md5(self, query: str) -> str:
        return hashlib.md5(query.encode("utf-8")).hexdigest()

    def _meta_key(self, md5: str) -> str:
        """metadata HASH 的 key"""
        return f"{self.key_prefix}{md5}"

    async def get(self, query: str) -> Optional[dict]:
        """语义查 L2,命中且相似度 ≥ 阈值返回 {answer, tools_used, sources},否则 None"""
        if not self._enabled:
            return None
        try:
            vec = await self._embed(query)
            if vec is None:
                return None
            # VSIM 查 top-1,带 score
            sim_result = await self.redis.execute_command(
                "VSIM", self.vector_key,
                "VALUES", str(self.embedding_dim),
                *(str(float(x)) for x in vec.tolist()),
                "WITHSCORES", "COUNT", "1",
            )
            if not sim_result or len(sim_result) < 2:
                logger.info(f'[L2] MISS query="{query}" (no results)')
                return None
            # sim_result = [element, score, element, score, ...]
            element = sim_result[0]
            if isinstance(element, bytes):
                element = element.decode("utf-8")
            score = float(sim_result[1])
            if score < self.threshold:
                logger.info(f'[L2] MISS query="{query}" sim={score:.3f} < {self.threshold}')
                return None
            # 查 metadata
            meta = await self.redis.hgetall(self._meta_key(element))
            if not meta:
                logger.warning(f'[L2] HIT 但 metadata 丢失: element={element}')
                return None
            def _d(b):
                return b.decode("utf-8") if isinstance(b, bytes) else b
            logger.info(f'[L2] HIT  query="{query}" sim={score:.3f}')
            return {
                "answer": _d(meta.get(b"answer", b"")),
                "tools_used": json.loads(_d(meta.get(b"tools_used", b"[]"))),
                "sources": json.loads(_d(meta.get(b"sources", b"[]"))),
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
            md5 = self._query_md5(query)
            meta_key = self._meta_key(md5)
            # 1. 写向量到 vectorset
            await self.redis.execute_command(
                "VADD", self.vector_key,
                "VALUES", str(self.embedding_dim),
                *(str(float(x)) for x in vec.tolist()),
                md5,
            )
            # 2. 写 metadata 到 HASH
            await self.redis.hset(
                meta_key,
                mapping={
                    "query": query,
                    "answer": response.get("answer", ""),
                    "tools_used": json.dumps(response.get("tools_used", []), ensure_ascii=False),
                    "sources": json.dumps(response.get("sources", []), ensure_ascii=False),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            await self.redis.expire(meta_key, self.ttl)
        except Exception as e:
            logger.warning(f"[L2] put 异常: {e}")
