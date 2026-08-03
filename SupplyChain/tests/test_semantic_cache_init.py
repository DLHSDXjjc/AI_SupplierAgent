"""
SemanticCache 基础集成测试。
vectorset 不需要建索引,只测"创建对象 + enabled 开关"。
"""
import pytest
from cache.semantic_cache import SemanticCache
from config.config import (
    SEMANTIC_CACHE_TTL, SEMANTIC_CACHE_THRESHOLD,
    SEMANTIC_CACHE_KEY_PREFIX, SEMANTIC_CACHE_VECTOR_KEY,
    SEMANTIC_CACHE_EMBEDDING_DIM,
)


@pytest.mark.integration
class TestSemanticCacheInit:
    async def test_constructs_without_error(self, redis_client, embedding_model):
        """构造 SemanticCache 不抛错"""
        cache = SemanticCache(
            redis_client=redis_client, embedding_model=embedding_model,
            threshold=SEMANTIC_CACHE_THRESHOLD, ttl=SEMANTIC_CACHE_TTL,
            key_prefix=SEMANTIC_CACHE_KEY_PREFIX, vector_key=SEMANTIC_CACHE_VECTOR_KEY,
            embedding_dim=SEMANTIC_CACHE_EMBEDDING_DIM,
        )
        assert cache.threshold == SEMANTIC_CACHE_THRESHOLD
        assert cache.vector_key == SEMANTIC_CACHE_VECTOR_KEY
        assert cache._enabled is True

    async def test_disabled_cache_returns_none(self, redis_client, embedding_model):
        """_enabled=False 时 get 直接返回 None,不需要 Redis"""
        cache = SemanticCache(
            redis_client=redis_client, embedding_model=embedding_model,
            threshold=SEMANTIC_CACHE_THRESHOLD, ttl=SEMANTIC_CACHE_TTL,
            key_prefix=SEMANTIC_CACHE_KEY_PREFIX, vector_key=SEMANTIC_CACHE_VECTOR_KEY,
            embedding_dim=SEMANTIC_CACHE_EMBEDDING_DIM,
        )
        cache._enabled = False
        result = await cache.get("随便问")
        assert result is None

    async def test_disabled_cache_put_noop(self, redis_client, embedding_model):
        """_enabled=False 时 put 是 no-op,不写 Redis"""
        cache = SemanticCache(
            redis_client=redis_client, embedding_model=embedding_model,
            threshold=SEMANTIC_CACHE_THRESHOLD, ttl=SEMANTIC_CACHE_TTL,
            key_prefix=SEMANTIC_CACHE_KEY_PREFIX, vector_key=SEMANTIC_CACHE_VECTOR_KEY,
            embedding_dim=SEMANTIC_CACHE_EMBEDDING_DIM,
        )
        cache._enabled = False
        await cache.put("采购流程", {"answer": "A", "tools_used": [], "sources": []})
        # 验证 vectorset 不存在(没创建)
        exists = await redis_client.exists(SEMANTIC_CACHE_VECTOR_KEY)
        assert exists == 0
