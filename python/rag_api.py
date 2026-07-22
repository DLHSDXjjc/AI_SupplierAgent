"""
供应链自动补货Agent — FastAPI API服务

功能：
1. 提供 /ask 接口：Agent主入口，接收自然语言问题，返回补货建议
2. 提供 /inventory 接口：直接查询库存数据
3. 提供 /inventory/alert 接口：查询预警SKU列表
4. 提供 /order 接口：模拟下单
5. 提供 /health 接口：健康检查
6. Nacos服务注册与心跳保活

启动方式：
    uvicorn rag_api:app --host 0.0.0.0 --port 8001
"""

import os
import asyncio
import chromadb
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ==================== 导入配置 ====================
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config.config import (
    CHROMA_PERSIST_DIR, CHROMA_COLLECTION,
    NACOS_SERVER, NACOS_SERVICE, NACOS_IP, NACOS_PORT,
    NACOS_NAMESPACE, NACOS_GROUP, NACOS_CLUSTER, NACOS_HEARTBEAT
)

# ==================== 导入Agent核心 ====================
from agent.agent_core import SupplyChainAgent

# ==================== 导入工具函数（用于直接API调用） ====================
from tools.inventory_query import inventory_query as _inventory_query_tool
from tools.inventory_query import inventory_alert as _inventory_alert_tool
from tools.inventory_query import supplier_query as _supplier_query_tool
from tools.inventory_query import _load_inventory
from tools.order_simulator import place_order as _place_order_tool


# ==================== 请求/响应模型定义 ====================

class AskRequest(BaseModel):
    """Agent问答请求模型"""
    query: str  # 用户的自然语言问题


class AskResponse(BaseModel):
    """Agent问答响应模型"""
    success: bool              # 是否成功
    query: str                 # 用户的问题
    answer: str                # Agent的回答
    tools_used: list = []      # 使用的工具列表
    sources: list = []         # 知识库来源列表


class OrderRequest(BaseModel):
    """模拟下单请求模型"""
    sku_id: str                # SKU编号
    quantity: int              # 订货数量
    supplier_id: str           # 供应商编号


class OrderResponse(BaseModel):
    """模拟下单响应模型"""
    success: bool              # 是否成功
    message: str               # 下单结果信息


class HealthResponse(BaseModel):
    """健康检查响应模型"""
    status: str                # 服务状态
    total_passages: int        # 知识库文档总数


# ==================== 全局变量 ====================
agent: Optional[SupplyChainAgent] = None   # Agent实例（在启动时初始化）
nacos_client = None                         # Nacos客户端实例
heartbeat_task = None                       # 心跳任务


# ==================== Nacos服务注册 ====================

async def register_nacos():
    """
    向Nacos注册服务
    使Java网关等其他服务可以发现和调用本服务
    """
    global nacos_client, heartbeat_task

    try:
        # 导入Nacos客户端
        from nacos import NacosClient

        # 创建Nacos客户端
        nacos_client = NacosClient(
            NACOS_SERVER,
            namespace=NACOS_NAMESPACE
        )

        # 注册服务实例
        nacos_client.add_naming_instance(
            NACOS_SERVICE,
            NACOS_IP,
            NACOS_PORT,
            cluster_name=NACOS_CLUSTER,
            group_name=NACOS_GROUP,
            weight=1.0,
            ephemeral=True
        )
        print(f"[Nacos] 服务注册成功: {NACOS_SERVICE} @ {NACOS_IP}:{NACOS_PORT}")

        # 启动心跳保活任务
        async def heartbeat_loop():
            """定期发送心跳，保持服务在线"""
            while True:
                try:
                    await asyncio.sleep(NACOS_HEARTBEAT)
                    nacos_client.send_heartbeat(
                        NACOS_SERVICE,
                        NACOS_IP,
                        NACOS_PORT,
                        cluster_name=NACOS_CLUSTER,
                        group_name=NACOS_GROUP,
                        ephemeral=True
                    )
                except Exception as e:
                    print(f"[Nacos] 心跳发送失败: {e}")

        heartbeat_task = asyncio.create_task(heartbeat_loop())

    except ImportError:
        print("[Nacos] nacos 模块未安装，跳过Nacos注册")
    except Exception as e:
        print(f"[Nacos] 服务注册失败: {e}，服务仍可本地使用")


async def deregister_nacos():
    """
    从Nacos注销服务
    在服务关闭时调用，确保Nacos不再将流量路由到本实例
    """
    global nacos_client, heartbeat_task

    if heartbeat_task:
        heartbeat_task.cancel()  # 取消心跳任务

    if nacos_client:
        try:
            nacos_client.remove_naming_instance(
                NACOS_SERVICE,
                NACOS_IP,
                NACOS_PORT,
                cluster_name=NACOS_CLUSTER,
                group_name=NACOS_GROUP,
                ephemeral=True
            )
            print(f"[Nacos] 服务注销成功: {NACOS_SERVICE}")
        except Exception as e:
            print(f"[Nacos] 服务注销失败: {e}")


# ==================== 应用生命周期管理 ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI应用生命周期管理
    在启动时初始化Agent和Nacos，在关闭时清理资源
    """
    # ---- 启动时执行 ----
    print("=" * 60)
    print("  供应链自动补货Agent — 服务启动中...")
    print("=" * 60)

    # 初始化Agent（加载模型、向量库、工具等）
    global agent
    agent = SupplyChainAgent(verbose=True)
    print("[启动] Agent初始化完成")

    # 注册Nacos服务
    await register_nacos()

    print("=" * 60)
    print("  ✅ 服务启动完成！")
    print("=" * 60)

    yield  # 应用运行中...

    # ---- 关闭时执行 ----
    print("[关闭] 正在清理资源...")
    await deregister_nacos()
    print("[关闭] 资源清理完成")


# ==================== 创建FastAPI应用 ====================

app = FastAPI(
    title="供应链自动补货Agent API",
    description="基于RAG+Agent的供应链自动补货顾问服务",
    version="1.0.0",
    lifespan=lifespan
)

# 添加CORS中间件，允许跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # 允许所有来源（生产环境应限制）
    allow_credentials=True,
    allow_methods=["*"],        # 允许所有HTTP方法
    allow_headers=["*"],        # 允许所有请求头
)


# ==================== API路由 ====================

@app.post("/ask", response_model=AskResponse, summary="Agent问答接口")
async def ask(request: AskRequest):
    """
    Agent主入口。接收用户的自然语言问题，Agent自动决定调用哪些工具，
    返回综合性的补货建议。

    请求示例:
        POST /ask
        {"query": "SKU001的库存够不够？要不要补货？"}
    """
    if not agent:
        raise HTTPException(status_code=503, detail="Agent未初始化，请稍后重试")

    if not request.query.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    # 调用Agent获取回答
    result = agent.chat(request.query)

    return AskResponse(
        success=True,
        query=request.query,
        answer=result["answer"],
        tools_used=result["tools_used"],
        sources=result["sources"]
    )


@app.get("/inventory", summary="库存查询接口")
async def query_inventory(
    sku_id: Optional[str] = None,
    category: Optional[str] = None
):
    """
    直接查询库存数据（不经过Agent推理）。
    提供sku_id或category参数进行查询。

    请求示例:
        GET /inventory?sku_id=SKU001
        GET /inventory?category=办公用品
    """
    if not sku_id and not category:
        raise HTTPException(status_code=400, detail="请提供 sku_id 或 category 参数")

    # 直接调用工具函数
    result = _inventory_query_tool.invoke({"sku_id": sku_id, "category": category})
    return {"success": True, "data": result}


@app.get("/inventory/alert", summary="库存预警接口")
async def get_inventory_alerts():
    """
    获取所有预警和紧急状态的SKU列表。

    请求示例:
        GET /inventory/alert
    """
    result = _inventory_alert_tool.invoke({})
    return {"success": True, "alerts": result}


@app.get("/supplier", summary="供应商查询接口")
async def query_supplier(
    supplier_id: Optional[str] = None,
    category: Optional[str] = None
):
    """
    查询供应商信息。

    请求示例:
        GET /supplier?supplier_id=SUP001
        GET /supplier?category=办公用品
    """
    if not supplier_id and not category:
        raise HTTPException(status_code=400, detail="请提供 supplier_id 或 category 参数")

    result = _supplier_query_tool.invoke({"supplier_id": supplier_id, "category": category})
    return {"success": True, "data": result}


@app.post("/order", response_model=OrderResponse, summary="模拟下单接口")
async def create_order(request: OrderRequest):
    """
    模拟下单。向指定供应商下达采购订单。

    请求示例:
        POST /order
        {"sku_id": "SKU001", "quantity": 350, "supplier_id": "SUP001"}
    """
    if request.quantity <= 0:
        raise HTTPException(status_code=400, detail="订货数量必须大于0")

    # 调用模拟下单工具
    result = _place_order_tool.invoke({
        "sku_id": request.sku_id,
        "quantity": request.quantity,
        "supplier_id": request.supplier_id
    })
    return OrderResponse(success=True, message=result)


@app.get("/health", response_model=HealthResponse, summary="健康检查接口")
async def health_check():
    """
    健康检查接口，返回服务状态和知识库文档总数。
    用于监控和负载均衡健康探测。
    """
    try:
        # 查询ChromaDB中的文档总数
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        collection = client.get_collection(name=CHROMA_COLLECTION)
        total = collection.count()
    except Exception:
        total = 0  # 数据库未初始化时返回0

    return HealthResponse(status="ok", total_passages=total)


# ==================== 启动入口 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=NACOS_PORT  # 使用配置文件中的端口
    )
