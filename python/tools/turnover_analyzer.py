"""
供应链自动补货Agent — 库存周转率分析工具

周转率 = 年需求量 / 平均库存
周转天数 = 365 / 周转率
平均库存 = (当前库存 + 安全库存) / 2
"""

import os
import sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from langchain_core.tools import tool
from tools.inventory_query import _load_inventory  # 复用已有的数据加载


def calc_turnover(daily_demand: float, current_stock: int, safety_stock: int) -> dict:
    """计算周转率和周转天数"""
    annual_demand = daily_demand * 365

    # 用平均库存
    avg_stock = (current_stock + safety_stock) / 2

    if avg_stock <= 0:
        return {"turnover_rate": 0, "turnover_days": 0, "risk": "⚠️ 无法计算"}

    turnover_rate = annual_demand / avg_stock
    turnover_days = 365 / turnover_rate

    # 风险判断
    if turnover_days <= 3:
        risk = "🔴 严重偏低 — 库存几乎耗尽，立即补货！"
    elif turnover_days <= 7:
        risk = "🟡 库存偏低 — 周转过快，建议尽快补货"
    elif turnover_days <= 45:
        risk = "🟢 健康 — 库存流转正常"
    elif turnover_days <= 90:
        risk = "🟡 需关注 — 周转偏慢，建议减少订货量或促销"
    else:
        risk = "🔴 呆滞风险 — 库存积压严重，资金长期占用，考虑退货或报废"

    return {
        "turnover_rate": round(turnover_rate, 1),
        "turnover_days": round(turnover_days, 1),
        "avg_stock": round(avg_stock, 1),
        "risk": risk
    }

"""
df 是什么形式？
df = _load_inventory() 返回的是 DataFrame（二维表）：


     sku_id   sku_name   category   current_stock  safety_stock  daily_demand  ...
0    SKU001   A4复印纸    办公用品        50            200          30.5      ...
1    SKU002   A3复印纸    办公用品       180            150          12.0      ...
2    SKU003   签字笔      办公用品       500            300          45.0      ...
...
29   SKU030   连接器USB-C  电子元器件      35            100           9.0      ...

有行有列 = 二维，30行 × 10列
result_row 是什么形式？

result_row = df[df["sku_id"] == "SKU001"]
# 还是二维DataFrame，但只有1行：
#
#    sku_id   sku_name  current_stock  safety_stock  daily_demand  ...
# 0  SKU001   A4复印纸        50            200          30.5       ...
#
# 注意：还是二维！不能用 row["daily_demand"] 取值（会报错）
row 是什么形式？

row = result_row.iloc[0]
# 取第0行，变成 Series（一维）：
#
# sku_id          "SKU001"
# sku_name        "A4复印纸"
# current_stock    50
# safety_stock     200
# daily_demand     30.5
# ...
#
# 一维了！可以用 row["daily_demand"] 取值 → 30.5
三步合起来

result_row = df[df["sku_id"] == "SKU001"]   # DataFrame，1行×10列
row = result_row.iloc[0]                     # Series，像一维数组
row["daily_demand"]                          # 30.5，像字典取值
直接看着代码敲完单个SKU的分支，敲完告诉我。
"""

@tool
def turnover_analyzer(sku_id: str = None) -> str:
    """
    库存周转率分析工具。根据SKU编号分析库存周转效率和呆滞风险。
    当用户询问某个SKU的周转率、库存效率、是否存在积压时，使用此工具。

    参数:
    sku_id: SKU编号，例如"SKU001"。不提供时分析所有SKU的周转率概况。
    """

    df = _load_inventory()
    
    if sku_id:
        #从df中筛选sku_id
        result_row = df[df["sku_id"] == sku_id.upper()]
        if result_row.empty:
            return f"未找到SKU编号为 {sku_id} 的商品。"
        
        row = result_row.iloc[0]

        r = calc_turnover(row["daily_demand"],row["current_stock"],row["safety_stock"])
        # 格式化返回
        return (
            f"📊 {row['sku_name']}（{sku_id.upper()}）周转率分析\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"日均需求: {row['daily_demand']}件/天 | 年需求: {row['daily_demand'] * 365:.0f}件\n"
            f"当前库存: {row['current_stock']}件 | 安全库存: {row['safety_stock']}件\n"
            f"平均库存: {r['avg_stock']}件\n"
            f"周转率: {r['turnover_rate']}次/年 | 周转天数: {r['turnover_days']}天\n"
            f"风险评级: {r['risk']}"
        )
    else:
         # 不指定sku_id，分析所有SKU的周转率概况
        results = []
        for _, row in df.iterrows():
            r = calc_turnover(row["daily_demand"], row["current_stock"], row["safety_stock"])
            results.append({
                "sku_id": row["sku_id"],
                "sku_name": row["sku_name"],
                "turnover_days": r["turnover_days"],
                "risk": r["risk"]
            })

        # 按周转天数从小到大排序（最快的在最前面）
        results.sort(key=lambda x: x["turnover_days"])

        lines = [f"📊 全品周转率概况（共{len(results)}个SKU）：\n"]
        for item in results:
            lines.append(
                f"• {item['sku_id']} {item['sku_name']} | "
                f"周转{item['turnover_days']}天 | {item['risk']}"
            )

        return "\n".join(lines)
