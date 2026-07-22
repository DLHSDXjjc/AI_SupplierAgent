"""
供应链自动补货Agent — 向量数据库构建脚本

功能：
1. 加载 m3e-base 中文向量模型
2. 读取供应链知识库文档（补货策略、库存政策、供应商指南）
3. 使用 LangChain RecursiveCharacterTextSplitter 进行文本分块
4. 将分块文本向量化并存入 ChromaDB 持久化数据库
5. 运行测试查询验证检索效果

使用方式：
    python create_vector_db.py
"""

import os

# ==================== HuggingFace镜像源配置 ====================
# 国内网络环境下，设置镜像源加速模型下载
# 优先使用环境变量 HF_ENDPOINT，如未设置则默认使用国内镜像
# 已经通过 setx 命令设置为系统永久环境变量，重启终端后自动生效
# 这里是保底措施：即使环境变量没设，代码里也自动设置，保证始终可用
if not os.environ.get("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
import shutil
import hashlib
from langchain_text_splitters import RecursiveCharacterTextSplitter
import chromadb
# chromadb 使用自带的 SentenceTransformerEmbeddingFunction
from chromadb.utils import embedding_functions

# ==================== 导入配置 ====================
import sys
# 将项目根目录加入Python路径，以便导入config模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config.config import (
    EMBEDDING_MODEL, EMBEDDING_DEVICE,
    CHROMA_PERSIST_DIR, CHROMA_COLLECTION,
    CHUNK_SIZE, CHUNK_OVERLAP, CHUNK_SEPARATORS
)


def load_embedding_model():
    """
    加载 ChromaDB 兼容的 embedding 函数
    使用 chromadb 自带的 SentenceTransformerEmbeddingFunction
    它内部会自动加载 m3e-base 模型，我们不需要单独加载

    【为什么不用 SentenceTransformer 直接加载？】
    因为 ChromaDB 提供了封装好的 embed_fn，我们在 collection.add() 和
    collection.query() 时只需要传文本，ChromaDB 内部会自动调 embed_fn
    把文本转成768维浮点向量，不需要我们手动调 model.encode()

    没有 embed_fn 的写法（手动管理向量，麻烦）：
        model = SentenceTransformer('moka-ai/m3e-base')
        vector = model.encode("安全库存的计算公式")   # 手动转向量
        collection.add(embeddings=[vector])           # 手动传向量

    有 embed_fn 的写法（全自动，简洁）：
        embed_fn = SentenceTransformerEmbeddingFunction(model_name='moka-ai/m3e-base')
        collection.add(documents=["安全库存的计算公式"])  # 只传文本，ChromaDB自动调embed_fn

    返回: ChromaDB embedding 函数
    """
    print(f"[1/5] 正在初始化embedding函数: {EMBEDDING_MODEL} ...")

    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL,
        device=EMBEDDING_DEVICE
    )
    print(f"      embedding函数初始化完成: {EMBEDDING_MODEL}")
    return embed_fn


def load_and_split_documents():
    """
    加载所有知识库文档并进行文本分块

    【为什么分3个文件而不是合成1个？】
    不是为了"让相同业务的向量离得更近"——向量检索没有物理距离的概念。
    而是为了：
    1. 主题聚焦：每个文件只讲一个主题，分块时不会把不同主题的内容揉进同一段
       （合文件可能导致"补货策略的尾巴+库存政策的开头"被切成同一段，语义模糊）
    2. 来源可追溯：Agent回答时能说"根据《补货策略》"，靠metadata里的book字段
    3. 维护方便：以后想更新某个主题，只替换对应文件即可

    【分块后，每段文本会产生什么？】
    向量化 → 768维浮点向量（用于语义检索，机器用来算距离找相似段落）
    元数据 → {"book":"补货策略", "index":0}（用于标注来源，人用来追溯出处）
    向量和元数据是两个独立的东西，向量≠元数据

    返回:
        all_chunks: 所有文档分块的文本列表
        all_metadata: 每个分块对应的元数据列表（包含文档来源和索引）
    """
    print("[2/5] 正在加载和分块知识库文档...")

    # 知识库文档目录
    knowledge_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "data", "supply_chain_knowledge"
    )

    # 定义要处理的文档列表：文件名 → 文档名称（用于元数据标注）
    doc_files = {
        "reorder_strategy.txt": "补货策略",
        "inventory_policy.txt": "库存管理政策",
        "supplier_guide.txt": "供应商管理指南"
    }

    # 创建文本分割器，使用配置文件中的参数
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,           # 每个分块的最大字符数（300字）
        chunk_overlap=CHUNK_OVERLAP,     # 相邻分块的重叠字符数（40字）

        # 【separators 分隔符优先级】
        # 先尝试用大分隔符切，切不动再降级用小分隔符：
        # \n\n（段落）→ \n（换行）→ 。（句号）→ ；（分号）→ ，（逗号）→ 空格 → 硬切
        # 尽量在"语义断点"处切割，万不得已才在字符中间硬切
        # 这样每段文本语义尽量完整，LLM拿到后能理解
        separators=CHUNK_SEPARATORS,

        # 【length_function=len】
        # 用Python内置的len()按字符数计算长度，chunk_size=300就是300个字符
        length_function=len
    )

    all_chunks = []      # 所有分块文本
    all_metadata = []    # 所有分块元数据

    for filename, doc_name in doc_files.items():
        filepath = os.path.join(knowledge_dir, filename)

        if not os.path.exists(filepath):
            print(f"      ⚠️ 文件不存在，跳过: {filepath}")
            continue

        # 读取文档内容
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()

        # 执行文本分块
        chunks = text_splitter.split_text(text)

        print(f"      📄 {doc_name} ({filename}): 原文{len(text)}字 → 分块{len(chunks)}段")

        # 【为每个分块生成元数据】
        # enumerate(chunks) 是Python内置函数，给列表元素编号
        # enumerate 不是"向量化"，只是给每个分块编个序号(idx=0,1,2...)
        # 这个idx用于标记"这段话是原文的第几段"，方便溯源
        for idx, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            all_metadata.append({
                "book": doc_name,       # 文档来源名称，Agent回答时能说"根据《补货策略》"
                "index": idx            # 分块在原文中的序号
            })

    print(f"      ✅ 共加载 {len(all_chunks)} 个文本分块")
    return all_chunks, all_metadata


def generate_ids(all_metadata):
    """
    为每个文本分块生成唯一ID
    使用 MD5 哈希确保ID的唯一性和可复现性

    参数:
        all_metadata: 元数据列表，每项包含 book 和 index
    返回:
        ID字符串列表
    """
    ids = []
    for meta in all_metadata:
        raw_key = f"{meta['book']}_{meta['index']}"
        doc_id = hashlib.md5(raw_key.encode("utf-8")).hexdigest()
        ids.append(doc_id)
    return ids


def create_vector_db(embed_fn, all_chunks, all_metadata, ids):
    """
    创建 ChromaDB 向量数据库并插入文档

    【ChromaDB里一条记录的完整结构】
    一条记录有4个字段，我们传3个，ChromaDB自动补1个：
    ┌──────────┬──────────────────┬──────────────────────────┬─────────────────────────┐
    │ id       │ document         │ embedding                │ metadata                │
    │ "a1b2.." │ "安全库存是为了…" │ [0.023,-0.156,...768个]  │ {"book":"补货策略",...}  │
    └──────────┴──────────────────┴──────────────────────────┴─────────────────────────┘
      我们传的↑     我们传的↑        ChromaDB自动生成的↑        我们传的↑

    embedding字段：ChromaDB在add()时自动调embed_fn，把文本转成768维浮点向量
    我们永远不需要手动传向量，只传文本就够了

    参数:
        embed_fn: ChromaDB兼容的embedding函数
        all_chunks: 文本分块列表
        all_metadata: 元数据列表
        ids: 唯一ID列表
    """
    print("[3/5] 正在创建向量数据库...")

    # 如果已存在旧的向量数据库，先删除
    if os.path.exists(CHROMA_PERSIST_DIR):
        print(f"      🗑️ 删除旧数据库: {CHROMA_PERSIST_DIR}")
        shutil.rmtree(CHROMA_PERSIST_DIR)

    # 创建 ChromaDB 持久化客户端
    # 数据保存到磁盘，重启不丢（不像内存字典_orders_db那样重启就没）
    client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)

    # 创建集合
    collection = client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        embedding_function=embed_fn
    )

    print(f"      📦 集合名称: {CHROMA_COLLECTION}")

    # ==================== 批量插入文档 ====================
    print("[4/5] 正在向量化并插入文档（批量处理）...")
    batch_size = 100

    for i in range(0, len(all_chunks), batch_size):
        end_idx = min(i + batch_size, len(all_chunks))
        # collection.add() 内部自动做两件事：
        # 1. 调 embed_fn 把 documents 转成768维浮点向量
        # 2. 自动创建 embedding 字段并存入向量值
        # 我们只传文本，ChromaDB自动帮我们完成向量化
        collection.add(
            documents=all_chunks[i:end_idx],       # 文本内容
            metadatas=all_metadata[i:end_idx],     # 元数据
            ids=ids[i:end_idx]                     # 唯一ID
        )
        print(f"      已插入 {end_idx}/{len(all_chunks)} 条")

    print(f"      ✅ 全部插入完成，共 {collection.count()} 条记录")


def test_query(embed_fn):
    """
    运行测试查询，验证向量检索效果

    【collection.query() 内部做了什么？】
    1. 把用户的问题也用embed_fn转成768维向量
    2. 用这个向量去和库里每条记录的embedding算L2距离（欧氏距离）
       L2距离 = √((a1-b1)² + (a2-b2)² + ... + (a768-b768)²)
    3. 按距离从小到大排序，取最近的几条（距离越小=语义越相近）
    4. 返回结果：documents(文本) + distances(距离) + metadatas(元数据)

    注意：ChromaDB底层用的是HNSW算法（近似最近邻搜索），不会和每条逐一计算
    通过图结构快速跳到邻近区域，比暴力搜索快100倍

    参数:
        embed_fn: ChromaDB兼容的embedding函数
    """
    print("[5/5] 运行测试查询...")

    client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    collection = client.get_collection(
        name=CHROMA_COLLECTION,
        embedding_function=embed_fn
    )

    # 测试查询：模拟用户提问
    test_queries = [
        "库存低于安全库存怎么办",
        "如何选择供应商",
        "EOQ经济订货量怎么计算"
    ]

    for query in test_queries:
        print(f"\n      🔍 查询: {query}")
        # query() 只需传文本，不需要手动传向量
        # ChromaDB内部自动调embed_fn把问题转成向量，再去库里找最近的
        results = collection.query(
            query_texts=[query],
            n_results=2
        )

        for idx, (doc, dist) in enumerate(zip(results["documents"][0], results["distances"][0])):
            # 【L2距离 → 相似度转换】
            # similarity = 1 / (1 + distance)
            # distance=0   → similarity=1.0  （完全相同）
            # distance=0.12 → similarity=0.89 （很相关）
            # distance=1   → similarity=0.5  （中等相关）
            # distance=10  → similarity=0.09 （基本无关）
            similarity = 1.0 / (1.0 + dist)
            source = results["metadatas"][0][idx]["book"]
            print(f"      [{idx+1}] 相似度={similarity:.4f} | 来源={source}")
            print(f"          {doc[:80]}...")


# ==================== 主函数 ====================
if __name__ == "__main__":
    print("=" * 60)
    print("  供应链自动补货Agent — 向量数据库构建工具")
    print("=" * 60)

    # Step 1: 加载embedding函数
    embed_fn = load_embedding_model()

    # Step 2: 加载并分块文档
    # 本函数只做切分，不涉及向量化（转浮点数），纯文本处理
    all_chunks, all_metadata = load_and_split_documents()

    # Step 3: 生成唯一ID
    ids = generate_ids(all_metadata)

    # Step 4: 创建向量数据库并插入
    # 向量化发生在 collection.add() 里，ChromaDB拿文本后自动调embed_fn转向量
    create_vector_db(embed_fn, all_chunks, all_metadata, ids)

    # Step 5: 测试查询
    test_query(embed_fn)

    print("\n" + "=" * 60)
    print("  ✅ 向量数据库构建完成！")
    print("=" * 60)
