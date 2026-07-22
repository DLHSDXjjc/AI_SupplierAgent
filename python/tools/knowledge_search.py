"""
供应链自动补货Agent — RAG知识库检索工具

功能：
1. 连接 ChromaDB 向量数据库
2. 根据用户查询检索最相关的知识段落
3. 过滤低相似度结果，返回高质量知识片段

该工具被注册为 LangChain Tool，供 Agent 在对话中调用。

【知识检索 vs 库存查询的区别】
knowledge_search  → 语义检索（模糊匹配），查ChromaDB向量库，适合"安全库存怎么算"
inventory_query   → 精确查询（条件筛选），查CSV+pandas，适合"SKU001库存多少"
reorder_calculator → 纯计算（数学公式），不查数据，适合"补多少货"
place_order       → 模拟生成，不查数据，生成假订单
"""

import os

# ==================== HuggingFace镜像源配置 ====================
if not os.environ.get("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from typing import Optional
import chromadb
from chromadb.utils import embedding_functions
from langchain_core.tools import tool

# ==================== 导入配置 ====================
import sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config.config import (
    EMBEDDING_MODEL, EMBEDDING_DEVICE,
    CHROMA_PERSIST_DIR, CHROMA_COLLECTION
)


# ==================== 全局变量（延迟初始化） ====================
# 【为什么用延迟初始化？】
# 如果在文件顶部直接初始化，import时就会执行，而import可能发生在FastAPI启动时
# 那时ChromaDB可能还没建好就会报错
# 延迟初始化 = 第一次用时才连接，不用就不连
_collection = None     # ChromaDB 集合实例
_embed_fn = None       # ChromaDB embedding 函数实例


def _init_resources():
    """
    延迟初始化 ChromaDB 连接和 embedding 函数
    仅在首次调用时执行，后续调用直接复用
    """
    global _collection, _embed_fn

    if _embed_fn is None:
        _embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL,
            device=EMBEDDING_DEVICE
        )

    if _collection is None:
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        _collection = client.get_collection(
            name=CHROMA_COLLECTION,
            embedding_function=_embed_fn
        )


def search_knowledge(query: str, top_k: int = 3, score_threshold: float = 0.5) -> list:
    """
    在知识库中检索与查询最相关的文本段落

    参数:
        query: 用户查询文本
        top_k: 返回的最大结果数量（默认3条）
        score_threshold: 相似度阈值，低于此值的结果将被过滤（默认0.5）
    返回:
        符合条件的检索结果列表，每项包含 text(文本)、source(来源)、score(相似度)
    """
    _init_resources()

    results = _collection.query(
        query_texts=[query],
        n_results=top_k
    )

    matched = []
    if results["documents"] and results["documents"][0]:
        for doc, dist, meta in zip(
            results["documents"][0],
            results["distances"][0],
            results["metadatas"][0]
        ):
            similarity = 1.0 / (1.0 + dist)

            if similarity >= score_threshold:
                matched.append({
                    "text": doc,
                    "source": meta.get("book", "未知"),
                    "score": round(similarity, 4)
                })

    return matched


# ==================== LangChain Tool 定义 ====================
@tool
def knowledge_search(query: str, top_k: Optional[int] = 3) -> str:
    """
    供应链知识库检索工具。当用户询问供应链管理、补货策略、库存管理、供应商管理等
    知识性问题时，使用此工具从知识库中检索相关文档段落。

    参数:
        query: 检索关键词或问题，例如"安全库存怎么计算"、"如何选择供应商"
        top_k: 返回的最相关结果数量，默认3条
    """
    # 【@tool 装饰器的作用】
    # 把这个函数注册为LangChain工具，@tool自动提取3样信息告诉LLM：
    # 1. 工具名 → "knowledge_search"（从函数名提取）
    # 2. 参数   → query: str, top_k: int（从参数签名提取）
    # 3. 描述   → 这个docstring（从三引号注释提取，#注释LLM看不到！）
    #
    # LLM根据这些描述判断"用户问补货策略→该调knowledge_search"
    # 所以docstring写得好不好，直接决定Agent聪不聪明
    # 用 """三引号""" LLM能读到，用 # 注释 LLM读不到

    results = search_knowledge(query, top_k=top_k)

    if not results:
        return "未在知识库中找到相关内容。"

    output_parts = []
    for idx, item in enumerate(results, 1):
        output_parts.append(
            f"【来源: {item['source']} | 相似度: {item['score']}】\n{item['text']}"
        )

    return "\n\n---\n\n".join(output_parts)
