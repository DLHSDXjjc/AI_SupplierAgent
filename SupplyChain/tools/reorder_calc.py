"""
供应链自动补货Agent — 补货计算工具

功能：
1. 安全库存计算：根据需求波动和提前期计算安全库存
2. EOQ经济订货量计算：平衡订货成本和持有成本
3. 补货量建议：综合安全库存和EOQ给出补货建议
4. 紧迫度评估：根据库存与安全库存的关系判断补货紧迫程度

该工具被注册为 LangChain Tool，供 Agent 在对话中调用。
"""

import math
from typing import Optional
from langchain_core.tools import tool


def calc_safety_stock(daily_demand: float, lead_time_days: int, service_level: float = 0.95) -> dict:
    """
    计算安全库存

    简化公式：安全库存 = 日均需求 × 提前期 × 安全系数
    安全系数根据服务水平确定：
    - 90% → 1.28
    - 95% → 1.65
    - 99% → 2.33

    参数:
        daily_demand: 日均需求量（件/天）
        lead_time_days: 采购提前期（天）
        service_level: 服务水平（默认0.95）
    返回:
        包含安全库存和服务水平的字典
    """
    # 服务水平 → Z值映射
    z_values = {
        0.90: 1.28,
        0.95: 1.65,
        0.99: 2.33
    }
    # 取最接近的Z值
    z = z_values.get(service_level, 1.65)

    # 计算安全库存
    safety_stock = math.ceil(daily_demand * lead_time_days * z * 0.3)  # 0.3为需求波动系数

    return {
        "safety_stock": safety_stock,
        "service_level": service_level,
        "z_value": z,
        "formula": f"安全库存 = {daily_demand}(日均需求) × {lead_time_days}(提前期) × {z}(Z值) × 0.3(波动系数) = {safety_stock}"
    }


def calc_eoq(annual_demand: float, order_cost: float, holding_cost_rate: float, unit_cost: float) -> dict:
    """
    计算EOQ经济订货量

    公式：EOQ = √(2 × 年需求量 × 单次订货成本 / (单位成本 × 持有成本率))

    参数:
        annual_demand: 年需求量（件/年）
        order_cost: 单次订货成本（元/次）
        holding_cost_rate: 年持有成本率（默认0.25，即库存价值的25%）
        unit_cost: 单位成本（元/件）
    返回:
        包含EOQ和相关指标的字典
    """
    # 计算单位年持有成本
    unit_holding_cost = unit_cost * holding_cost_rate

    # 计算EOQ
    eoq = math.sqrt(2 * annual_demand * order_cost / unit_holding_cost)
    eoq = math.ceil(eoq)  # 向上取整

    # 计算年订货次数
    order_frequency = round(annual_demand / eoq, 1)

    # 计算总成本（订货成本 + 持有成本）
    total_order_cost = order_frequency * order_cost
    total_holding_cost = (eoq / 2) * unit_holding_cost
    total_cost = total_order_cost + total_holding_cost

    return {
        "eoq": eoq,
        "order_frequency": order_frequency,           # 年订货次数
        "total_order_cost": round(total_order_cost, 2),   # 年订货总成本
        "total_holding_cost": round(total_holding_cost, 2),  # 年持有总成本
        "total_cost": round(total_cost, 2),              # 年总成本
        "formula": (
            f"EOQ = √(2 × {annual_demand}(年需求) × {order_cost}(订货成本) "
            f"/ ({unit_cost}(单价) × {holding_cost_rate}(持有率))) = {eoq}件"
        )
    }


def assess_urgency(current_stock: int, safety_stock: int) -> str:
    """
    评估补货紧迫度

    判断标准：
    - 紧急：当前库存 ≤ 安全库存的50%
    - 较紧急：当前库存 ≤ 安全库存
    - 需关注：当前库存 ≤ 安全库存的150%
    - 正常：当前库存 > 安全库存的150%

    参数:
        current_stock: 当前库存
        safety_stock: 安全库存
    返回:
        紧迫度等级和说明
    """
    ratio = current_stock / safety_stock if safety_stock > 0 else 0

    if ratio <= 0.5:
        return "🔴 紧急 — 库存严重不足，面临断货风险，建议立即补货"
    elif ratio <= 1.0:
        return "🟠 较紧急 — 库存低于安全线，需尽快安排补货"
    elif ratio <= 1.5:
        return "🟡 需关注 — 库存偏低，建议评估是否需要提前补货"
    else:
        return "🟢 正常 — 库存充足，按常规计划补货即可"


# ==================== LangChain Tool 定义 ====================

@tool
def reorder_calculator(
    current_stock: int,
    safety_stock: int,
    daily_demand: float,
    lead_time_days: int,
    unit_cost: float,
    order_cost: float = 200.0,
    holding_cost_rate: float = 0.25,
    service_level: float = 0.95
) -> str:
    """
    补货计算工具。根据当前库存、安全库存、需求等参数，计算建议补货量和紧迫度。
    当需要为某个SKU制定补货计划时，使用此工具。

    参数:
        current_stock: 当前库存数量（件）
        safety_stock: 安全库存数量（件）
        daily_demand: 日均需求量（件/天）
        lead_time_days: 采购提前期（天）
        unit_cost: 单位成本（元/件）
        order_cost: 单次订货成本（元/次），默认200元
        holding_cost_rate: 年持有成本率，默认0.25（即库存价值的25%）
        service_level: 目标服务水平，默认0.95（95%）
    """
    # ---- 1. 评估紧迫度 ----
    urgency = assess_urgency(current_stock, safety_stock)

    # ---- 2. 计算提前期内需求 ----
    lead_time_demand = daily_demand * lead_time_days

    # ---- 3. 计算补货点（Reorder Point） ----
    # 补货点 = 提前期需求 + 安全库存
    reorder_point = math.ceil(lead_time_demand + safety_stock)

    # ---- 4. 计算建议补货量 ----
    # 如果当前库存低于补货点，则需要补货
    if current_stock < reorder_point:
        # 基础补货量 = 补货点 - 当前库存 + 提前期需求（确保到货后不立即告急）
        basic_reorder_qty = reorder_point - current_stock + math.ceil(lead_time_demand)

        # 计算EOQ作为参考
        annual_demand = daily_demand * 365
        eoq_result = calc_eoq(annual_demand, order_cost, holding_cost_rate, unit_cost)

        # 取基础补货量和EOQ中的较大值，确保经济性
        suggested_qty = max(basic_reorder_qty, eoq_result["eoq"])

        # ---- 5. 计算预计到货时间 ----
        eta_days = lead_time_days

        # ---- 6. 计算当前库存可维持天数 ----
        days_remaining = round(current_stock / daily_demand, 1) if daily_demand > 0 else 0

        result = (
            f"📊 补货计算结果\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"紧迫度: {urgency}\n"
            f"当前库存: {current_stock}件 | 安全库存: {safety_stock}件\n"
            f"日均需求: {daily_demand}件/天 | 提前期: {lead_time_days}天\n"
            f"提前期需求: {math.ceil(lead_time_demand)}件 | 补货点: {reorder_point}件\n"
            f"当前库存可维持: {days_remaining}天\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 建议补货量: {suggested_qty}件\n"
            f"   其中基础需求: {basic_reorder_qty}件\n"
            f"   EOQ经济批量: {eoq_result['eoq']}件 (取较大值)\n"
            f"   年订货次数: {eoq_result['order_frequency']}次\n"
            f"   年总成本: ¥{eoq_result['total_cost']}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ 预计到货: 下单后 {eta_days} 天\n"
            f"📝 计算依据:\n"
            f"   {eoq_result['formula']}"
        )
    else:
        # 库存充足，无需补货
        days_remaining = round(current_stock / daily_demand, 1) if daily_demand > 0 else 0
        result = (
            f"📊 补货计算结果\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"紧迫度: {urgency}\n"
            f"当前库存: {current_stock}件 | 安全库存: {safety_stock}件\n"
            f"日均需求: {daily_demand}件/天\n"
            f"当前库存可维持: {days_remaining}天\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ 当前库存高于补货点({reorder_point}件)，暂无需补货。"
        )

    return result
