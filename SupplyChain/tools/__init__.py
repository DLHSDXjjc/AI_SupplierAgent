"""
供应链自动补货Agent — 工具包初始化模块

统一导出所有Agent可用的工具，方便在Agent核心模块中引用。
使用方式: from tools import knowledge_search, inventory_query, ...
类的构造函数    → SupplyChainAgent() 时执行 → 初始化对象
包的构造函数    → import tools 时执行     → 初始化包（导入子模块、生成 ALL_TOOLS）

"""

from tools.knowledge_search import knowledge_search
from tools.inventory_query import inventory_query, inventory_alert, supplier_query
from tools.reorder_calc import reorder_calculator
from tools.order_simulator import place_order, query_order, list_orders
from tools.turnover_analyzer import turnover_analyzer

# 所有工具的列表，供 Agent 注册使用
ALL_TOOLS = [
    knowledge_search,       # 供应链知识库检索
    inventory_query,        # 库存查询
    inventory_alert,        # 库存预警查询
    supplier_query,         # 供应商查询
    reorder_calculator,     # 补货计算
    place_order,            # 模拟下单
    query_order,            # 订单查询
    list_orders,            # 订单列表
    turnover_analyzer,      # 库存周转率分析
]
