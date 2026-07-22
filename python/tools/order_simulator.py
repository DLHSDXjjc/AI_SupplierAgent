"""
供应链自动补货Agent — 模拟下单工具

功能：
1. 模拟向供应商下单的流程
2. 生成模拟订单号、预计到货时间
3. 记录订单历史（内存中）
4. 查询订单状态

该工具被注册为 LangChain Tool，供 Agent 在对话中调用。
注意：这是模拟工具，不会产生真实的采购订单。
"""

import uuid
import random
from datetime import datetime, timedelta
from typing import Optional
from langchain_core.tools import tool

# ==================== 内存订单存储 ====================
# 【_orders_db 是什么？】
# 就是一个Python普通字典变量（全局变量），和 a=1, my_list=[] 没区别
# 不是Redis、不是缓存、不是数据库，就是程序运行时内存里的一块空间
#
# 【和库存数据的区别】
# 库存数据 → CSV文件存在磁盘上，重启后 pd.read_csv() 重新读，数据还在
# 订单数据 → _orders_db 字典在内存中，服务重启就没了
#
# 【多线程下是否安全？】
# Python全局变量 ≈ Java的static变量，所有线程共享同一个，能读到
# 但并发修改不安全（读+写两步操作中间可能被打断）
# 真实系统应改用数据库（MySQL/Redis），天然支持并发
#
# 【Python的global关键字】
# 读取全局变量：直接用就行
# 修改字典内容：直接改就行（不用global）
# 重新赋值整个变量：必须用 global _orders_db 声明
#   _orders_db["key"] = value  ✅ 不用global
#   _orders_db = {"new": "value"}  ❌ 不用global会变成局部变量
_orders_db = {}


def _generate_order_id() -> str:
    """
    生成模拟订单号
    格式: PO-年月日-6位随机数，例如 PO-20260613-A3F8K2
    """
    date_str = datetime.now().strftime("%Y%m%d")
    random_str = uuid.uuid4().hex[:6].upper()
    return f"PO-{date_str}-{random_str}"


def _calc_eta(lead_time_days: int) -> str:
    """
    计算预计到货日期

    参数:
        lead_time_days: 采购提前期（天）
    返回:
        预计到货日期字符串，格式 YYYY-MM-DD
    """
    eta_date = datetime.now() + timedelta(days=lead_time_days)
    return eta_date.strftime("%Y-%m-%d")


# ==================== LangChain Tool 定义 ====================

@tool
def place_order(sku_id: str, quantity: int, supplier_id: str) -> str:
    """
    模拟下单工具。向指定供应商下达采购订单。
    该工具为模拟功能，不会产生真实订单。下单前需确认用户已同意。

    参数:
        sku_id: SKU编号，例如"SKU001"
        quantity: 订货数量（件），必须大于0
        supplier_id: 供应商编号，例如"SUP001"
    """
    if quantity <= 0:
        return "❌ 订货数量必须大于0，请确认后重新下单。"

    order_id = _generate_order_id()
    order_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 模拟不同供应商的提前期
    lead_time_map = {
        "SUP001": 7, "SUP002": 5, "SUP003": 14,
        "SUP004": 7, "SUP005": 5, "SUP006": 5,
        "SUP007": 7, "SUP008": 10, "SUP009": 7
    }
    lead_time = lead_time_map.get(supplier_id, 7)
    eta = _calc_eta(lead_time)

    # 模拟订单状态（90%概率成功，10%概率待确认）
    if random.random() < 0.9:
        status = "已确认"
    else:
        status = "待确认"

    # ---- 存储订单记录 ----
    # 写入 _orders_db 字典，query_order 和 list_orders 可以从这里读取
    # place_order 写入，query_order 读取，共用同一个 _orders_db
    order_record = {
        "order_id": order_id,
        "sku_id": sku_id,
        "quantity": quantity,
        "supplier_id": supplier_id,
        "order_time": order_time,
        "lead_time_days": lead_time,
        "eta": eta,
        "status": status
    }
    _orders_db[order_id] = order_record

    result = (
        f"📋 模拟下单结果\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"订单号: {order_id}\n"
        f"SKU编号: {sku_id}\n"
        f"订货数量: {quantity}件\n"
        f"供应商: {supplier_id}\n"
        f"下单时间: {order_time}\n"
        f"采购提前期: {lead_time}天\n"
        f"预计到货: {eta}\n"
        f"订单状态: {status}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ 注意：这是模拟订单，不会产生真实采购。"
    )

    return result


@tool
def query_order(order_id: str) -> str:
    """
    订单查询工具。根据订单号查询订单状态和详情。

    【数据从哪来？】
    从 _orders_db 字典读取，这个字典是 place_order 写入的
    所以必须先下单（place_order），才能查到订单（query_order）
    服务重启后 _orders_db 清空，之前的订单全没了

    参数:
        order_id: 订单号，例如"PO-20260613-A3F8K2"
    """
    if order_id not in _orders_db:
        return f"❌ 未找到订单号 {order_id}。请确认订单号是否正确。"

    order = _orders_db[order_id]

    # 模拟订单状态流转（下单时间距今超过提前期则已到货）
    order_time = datetime.strptime(order["order_time"], "%Y-%m-%d %H:%M:%S")
    eta_time = order_time + timedelta(days=order["lead_time_days"])

    if datetime.now() >= eta_time:
        delivery_status = "已到货"
    else:
        remaining_days = (eta_time - datetime.now()).days
        delivery_status = f"运输中（预计{remaining_days}天后到货）"

    result = (
        f"📋 订单详情\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"订单号: {order['order_id']}\n"
        f"SKU编号: {order['sku_id']}\n"
        f"订货数量: {order['quantity']}件\n"
        f"供应商: {order['supplier_id']}\n"
        f"下单时间: {order['order_time']}\n"
        f"预计到货: {order['eta']}\n"
        f"确认状态: {order['status']}\n"
        f"物流状态: {delivery_status}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )

    return result


@tool
def list_orders() -> str:
    """
    订单列表查询工具。返回所有历史订单的摘要信息。
    """
    if not _orders_db:
        return "📭 当前无任何订单记录。"

    lines = [f"📋 历史订单列表（共 {len(_orders_db)} 笔）：\n"]

    for order_id, order in _orders_db.items():
        lines.append(
            f"• {order_id} | {order['sku_id']} × {order['quantity']}件 | "
            f"供应商:{order['supplier_id']} | 状态:{order['status']} | "
            f"预计到货:{order['eta']}"
        )

    return "\n".join(lines)
