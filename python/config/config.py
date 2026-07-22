"""
供应链自动补货Agent — 配置加载模块

从 modelConfig.yaml 中读取所有配置项，以全局变量的形式供其他模块使用。
使用方式: from config.config import EMBEDDING_MODEL, DEEPSEEK_API_KEY, ...
"""

import yaml
import os

# ==================== 定位配置文件路径 ====================
# 当前文件所在目录
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# 配置文件的完整路径
CONFIG_PATH = os.path.join(CURRENT_DIR, "modelConfig.yaml")


def _load_config():
    """
    加载YAML配置文件，返回配置字典。
    如果文件不存在或解析失败，抛出异常。
    """
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"配置文件不存在: {CONFIG_PATH}")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config


# ==================== 加载配置 ====================
_config = _load_config()

# ==================== Embedding模型配置 ====================
EMBEDDING_MODEL = _config["embedding"]["model_name"]       # 向量模型名称
EMBEDDING_DEVICE = _config["embedding"]["device"]           # 推理设备

# ==================== DeepSeek LLM配置 ====================
DEEPSEEK_API_KEY = _config["deepseek"]["api_key"]           # API密钥
DEEPSEEK_BASE_URL = _config["deepseek"]["base_url"]         # API基础地址
DEEPSEEK_MODEL = _config["deepseek"]["model"]               # 模型名称
DEEPSEEK_TEMPERATURE = _config["deepseek"]["temperature"]   # 生成温度
DEEPSEEK_MAX_TOKENS = _config["deepseek"]["max_tokens"]     # 最大token数

# ==================== ChromaDB配置 ====================
CHROMA_PERSIST_DIR = _config["chromadb"]["persist_directory"]       # 持久化路径
CHROMA_COLLECTION = _config["chromadb"]["collection_name"]          # 集合名称

# ==================== 文本分块配置 ====================
CHUNK_SIZE = _config["text_splitter"]["chunk_size"]                 # 分块大小
CHUNK_OVERLAP = _config["text_splitter"]["chunk_overlap"]           # 重叠大小
CHUNK_SEPARATORS = _config["text_splitter"]["separators"]           # 分隔符列表

# ==================== Nacos配置 ====================
NACOS_SERVER = _config["nacos"]["server_address"]                   # Nacos地址
NACOS_SERVICE = _config["nacos"]["service_name"]                    # 服务名
NACOS_IP = _config["nacos"]["ip"]                                   # 本机IP
NACOS_PORT = _config["nacos"]["port"]                               # 端口
NACOS_NAMESPACE = _config["nacos"]["namespace"]                     # 命名空间
NACOS_GROUP = _config["nacos"]["group"]                             # 分组
NACOS_CLUSTER = _config["nacos"]["cluster_name"]                    # 集群
NACOS_HEARTBEAT = _config["nacos"]["heartbeat_interval"]            # 心跳间隔
