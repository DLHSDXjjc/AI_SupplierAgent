# 供应链自动补货Agent — Docker容器定义
# 基于python:3.11-slim，包含所有依赖和项目文件

# ==================== 基础镜像 ====================
FROM python:3.11-slim

# ==================== 配置阿里云镜像源 ====================
# 使用阿里云镜像加速apt和pip下载（中国网络优化）
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/

# ==================== 安装系统依赖 ====================
# sqlite3和libsqlite3-dev是ChromaDB的必需依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    sqlite3 \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

# ==================== 设置工作目录 ====================
WORKDIR /app

# ==================== 安装Python依赖 ====================
# 先复制requirements.txt，利用Docker缓存层加速构建
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ==================== 复制项目文件 ====================
# 复制所有项目文件到容器中
COPY config/ ./config/
COPY data/ ./data/
COPY tools/ ./tools/
COPY agent/ ./agent/
COPY create_vector_db.py .
COPY rag_api.py .
COPY app.py .

# ==================== 构建向量数据库 ====================
# 在容器启动前先构建向量数据库（避免运行时首次加载慢）
RUN python create_vector_db.py

# ==================== 暴露端口 ====================
# 8001: FastAPI服务端口
EXPOSE 8001

# ==================== 启动命令 ====================
# 使用uvicorn启动FastAPI服务
CMD ["uvicorn", "rag_api:app", "--host", "0.0.0.0", "--port", "8001"]
