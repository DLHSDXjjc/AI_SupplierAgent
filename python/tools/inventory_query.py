"""
供应链自动补货Agent — 库存查询工具

功能：
1. 加载模拟库存数据（CSV）和供应商数据（CSV）
2. 支持按SKU编号、品类、库存状态等维度查询库存
3. 支持查询预警/紧急状态的SKU列表
4. 支持查询供应商信息

该工具被注册为 LangChain Tool，供 Agent 在对话中调用。

【数据查询 vs 知识检索 vs 补货计算】
inventory_query   → 精确查询（条件筛选），查CSV+pandas，适合"SKU001库存多少"
knowledge_search  → 语义检索（模糊匹配），查ChromaDB向量库，适合"安全库存怎么算"
reorder_calculator → 纯计算（数学公式），不查数据，适合"补多少货"
"""

import os
import pandas as pd
# 【pandas是什么？】
# Python最流行的数据分析包，专门处理表格数据
# 核心数据类型：DataFrame（二维表，类似Excel）和 Series（一列数据）
# pd.read_csv() 一行代码加载CSV文件，自动推断列名和数据类型
# 筛选用 df[df["列"] == 值]，统计用 df["列"].value_counts()
# 底层用C/Fortran实现，比Python原生for循环快几百倍
from typing import Optional
from langchain_core.tools import tool

# ==================== 导入配置 ====================
import sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# ==================== 数据文件路径 ====================
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
INVENTORY_CSV = os.path.join(DATA_DIR, "mock_inventory.csv")
SUPPLIERS_CSV = os.path.join(DATA_DIR, "mock_suppliers.csv")

# ==================== 全局变量（延迟加载） ====================
# 【为什么延迟加载？】
# CSV是静态文件，数据不会变，读一次就够了，所以缓存没问题
# 真实系统如果对接数据库，库存是实时变化的，就不能缓存
# 应该每次都查数据库：df = pd.read_sql("SELECT * FROM inventory", conn)
# 当前Demo用缓存就够了，迁移到真实系统只需改这一行
_inventory_df = None    # 库存数据 DataFrame
_suppliers_df = None    # 供应商数据 DataFrame


def _load_inventory():
    """
    延迟加载库存CSV数据
    仅在首次调用时读取文件，后续调用直接复用

    【pd.read_csv()做了什么？】
    自动完成：打开文件 → 读取内容 → 解析逗号分隔 → 第一行当列名
    → 自动推断数据类型(int/float/str) → 创建DataFrame对象
    一行代码干了Java里至少20行的文件读取+解析代码
    """
    global _inventory_df
    if _inventory_df is None:
        _inventory_df = pd.read_csv(INVENTORY_CSV)
        _inventory_df["current_stock"] = _inventory_df["current_stock"].astype(int)
        _inventory_df["safety_stock"] = _inventory_df["safety_stock"].astype(int)
    return _inventory_df


def _load_suppliers():
    """
    延迟加载供应商CSV数据
    仅在首次调用时读取文件，后续调用直接复用
    """
    global _suppliers_df
    if _suppliers_df is None:
        _suppliers_df = pd.read_csv(SUPPLIERS_CSV)
    return _suppliers_df


def _format_inventory_row(row) -> str:
    """
    将一行库存数据格式化为可读的文本

    参数:
        row: DataFrame 的一行（Series类型，一维数据）
    """
    return (
        f"SKU编号: {row['sku_id']}\n"
        f"商品名称: {row['sku_name']}\n"
        f"品类: {row['category']}\n"
        f"当前库存: {row['current_stock']}件\n"
        f"安全库存: {row['safety_stock']}件\n"
        f"日均需求: {row['daily_demand']}件/天\n"
        f"采购提前期: {row['lead_time_days']}天\n"
        f"单位成本: ¥{row['unit_cost']}\n"
        f"默认供应商: {row['supplier_id']}\n"
        f"库存状态: {row['status']}"
    )


# ==================== LangChain Tool 定义 ====================

@tool
def inventory_query(sku_id: Optional[str] = None, category: Optional[str] = None) -> str:
    """
    库存查询工具。根据SKU编号或品类查询库存信息。
    当用户询问某个商品的库存情况时，使用此工具。

    参数:
        sku_id: SKU编号，例如"SKU001"。提供时查询指定商品。
        category: 品类名称，例如"办公用品"、"电子元器件"、"包装材料"、"五金配件"、"化工原料"。
                  提供时查询该品类下所有商品。
        注意：sku_id 和 category 至少提供一个，优先使用 sku_id。
    """
    df = _load_inventory()

    if sku_id:
        # 【pandas布尔索引原理】
        # 第1步：df["sku_id"] == "SKU001" → 生成一列True/False（掩码）
        #   0     True    ← SKU001，命中
        #   1     False   ← SKU002，不命中
        #   ...
        # 第2步：df[True/False列] → 只保留True的行，返回新的DataFrame
        # 等价于SQL: SELECT * FROM inventory WHERE sku_id = 'SKU001'
        result = df[df["sku_id"] == sku_id.upper()]
        if result.empty:
            return f"未找到SKU编号为 {sku_id} 的商品。请检查编号是否正确。"
        # 【iloc[0] 按位置取第0行（Python从0开始计数）】
        # 把二维DataFrame变成一维Series，就能用row["列名"]取值
        row = result.iloc[0]
        return _format_inventory_row(row)

    # 按品类查询
    if category:
        result = df[df["category"] == category]
        if result.empty:
            available = df["category"].unique().tolist()
            return f"未找到品类 \"{category}\" 的商品。可用品类: {', '.join(available)}"

        lines = [f"品类 [{category}] 共有 {len(result)} 个商品：\n"]
        for _, row in result.iterrows():
            lines.append(
                f"• {row['sku_id']} {row['sku_name']} | "
                f"库存:{row['current_stock']}件 安全库存:{row['safety_stock']}件 | "
                f"状态:{row['status']}"
            )
        return "\n".join(lines)

    return "请提供 sku_id（SKU编号）或 category（品类名称）进行查询。"


@tool
def inventory_alert() -> str:
    """
    库存预警查询工具。返回所有处于"预警"和"紧急"状态的SKU列表。
    当用户询问哪些商品库存不足、需要关注或补货时，使用此工具。

    【库存状态是谁设的？】
    状态是在CSV文件里写死的，没有任何地方会动态修改。
    用户下单后库存数据不变（place_order只是模拟，没改CSV），
    所以SKU001永远显示"紧急"。
    真实系统应该在下单成功后更新库存数据并重新计算预警状态。
    """
    df = _load_inventory()

    # 【isin() 相当于SQL的 IN】
    # df[df["status"].isin(["预警", "紧急"])] 等价于
    # SELECT * FROM inventory WHERE status IN ('预警', '紧急')
    alert_df = df[df["status"].isin(["预警", "紧急"])]

    if alert_df.empty:
        return "当前所有商品库存正常，无预警信息。"

    urgent_count = len(alert_df[alert_df["status"] == "紧急"])
    warning_count = len(alert_df[alert_df["status"] == "预警"])

    lines = [
        f"⚠️ 库存预警汇总：紧急 {urgent_count} 个，预警 {warning_count} 个\n"
    ]

    for status in ["紧急", "预警"]:
        status_df = alert_df[alert_df["status"] == status]
        if not status_df.empty:
            emoji = "🔴" if status == "紧急" else "🟡"
            lines.append(f"\n{emoji} {status}状态：")
            for _, row in status_df.iterrows():
                gap = row["safety_stock"] - row["current_stock"]
                days_left = round(row["current_stock"] / row["daily_demand"], 1) if row["daily_demand"] > 0 else 0
                lines.append(
                    f"  • {row['sku_id']} {row['sku_name']} | "
                    f"当前:{row['current_stock']}件 安全库存:{row['safety_stock']}件 | "
                    f"缺口:{gap}件 仅够{days_left}天"
                )

    return "\n".join(lines)


@tool
def supplier_query(supplier_id: Optional[str] = None, category: Optional[str] = None) -> str:
    """
    供应商查询工具。根据供应商编号或供应品类查询供应商信息。
    当用户需要了解供应商详情、选择供应商时，使用此工具。

    参数:
        supplier_id: 供应商编号，例如"SUP001"。提供时查询指定供应商。
        category: 品类名称，查询该品类的所有供应商。
        注意：supplier_id 和 category 至少提供一个，优先使用 supplier_id。
    """
    df = _load_suppliers()

    if supplier_id:
        result = df[df["supplier_id"] == supplier_id.upper()]
        if result.empty:
            return f"未找到供应商编号为 {supplier_id} 的记录。"
        row = result.iloc[0]
        return (
            f"供应商编号: {row['supplier_id']}\n"
            f"供应商名称: {row['supplier_name']}\n"
            f"供应品类: {row['category']}\n"
            f"标准交期: {row['lead_time_days']}天\n"
            f"最小起订量: {row['min_order_qty']}件\n"
            f"评分: {row['rating']}/5.0\n"
            f"价格等级: {row['price_tier']}"
        )

    if category:
        result = df[df["category"] == category]
        if result.empty:
            available = df["category"].unique().tolist()
            return f"未找到品类 \"{category}\" 的供应商。可用品类: {', '.join(available)}"

        lines = [f"品类 [{category}] 的供应商共 {len(result)} 家：\n"]
        for _, row in result.iterrows():
            lines.append(
                f"• {row['supplier_id']} {row['supplier_name']} | "
                f"交期:{row['lead_time_days']}天 起订量:{row['min_order_qty']}件 | "
                f"评分:{row['rating']} 价格:{row['price_tier']}"
            )
        return "\n".join(lines)

    return "请提供 supplier_id（供应商编号）或 category（品类名称）进行查询。"
