"""
pytest 共享 fixture。
- `redis_client`:连接到 192.168.203.129:6379 db=3,测试结束自动清理
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
    SEMANTIC_CACHE_KEY_PREFIX, SEMANTIC_CACHE_VECTOR_KEY,
    EMBEDDING_MODEL, EMBEDDING_DEVICE,
)
from sentence_transformers import SentenceTransformer


@pytest.fixture
async def redis_client():
    """异步 Redis 客户端,测试结束清理所有 ragcache:* key 和 vectorset"""
    client = redis_async.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, password=REDIS_PASSWORD,
        decode_responses=False,
        protocol=2,  # redis-py 8 默认 RESP3,但 vectorset VADD/VSIM 在 RESP3 下有兼容问题,强制 RESP2
    )
    # 测试前清理
    await _cleanup(client, SEMANTIC_CACHE_KEY_PREFIX, SEMANTIC_CACHE_VECTOR_KEY)
    yield client
    # 测试后清理
    await _cleanup(client, SEMANTIC_CACHE_KEY_PREFIX, SEMANTIC_CACHE_VECTOR_KEY)
    await client.aclose()


@pytest.fixture(scope="session")
def embedding_model():
    """m3e-base 较慢,session 级别只加载一次"""
    return SentenceTransformer(EMBEDDING_MODEL, device=EMBEDDING_DEVICE)


async def _cleanup(client, prefix: str, vector_key: str):
    """删除测试遗留的 metadata HASH key 和 vectorset"""
    async for key in client.scan_iter(match=f"{prefix}*"):
        await client.delete(key)
    # 删除 vectorset
    await client.delete(vector_key)
