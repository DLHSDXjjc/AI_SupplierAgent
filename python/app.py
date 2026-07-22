"""
供应链自动补货Agent — Streamlit可视化界面（纯前端版）

功能：
1. 左侧对话区：用户自然语言提问，显示Agent回答和工具调用过程
2. 右侧看板区：库存统计、预警列表、补货建议
3. 交互式补货操作：查看建议后可直接模拟下单

本版本为纯前端，所有Agent调用走FastAPI后端API，不直接创建Agent对象。
需要先启动FastAPI：uvicorn rag_api:app --host 0.0.0.0 --port 8001

启动方式：
    streamlit run app.py
"""

import os
import sys

# ==================== HuggingFace镜像源配置 ====================
# 国内网络环境下，设置镜像源加速模型下载（必须在import streamlit等库之前设置）
if not os.environ.get("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import streamlit as st
import pandas as pd
import requests

# ==================== 路径设置 ====================
# 将项目根目录加入Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ==================== 导入工具函数（仅用于看板数据展示） ====================
from tools.inventory_query import _load_inventory, _load_suppliers

# ==================== FastAPI后端地址 ====================
# 所有Agent对话请求都发给FastAPI，Streamlit只做展示
API_BASE_URL = "http://localhost:8001"


# ==================== 页面配置 ====================
st.set_page_config(
    page_title="供应链自动补货顾问",
    page_icon="🏭",
    layout="wide",                    # 使用宽屏布局
    initial_sidebar_state="expanded"   # 侧边栏默认展开
)

# ==================== 自定义CSS样式 ====================
st.markdown("""
<style>
    /* 主标题样式 */
    .main-title {
        font-size: 28px;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 20px;
    }
    /* 工具调用标签样式 */
    .tool-tag {
        display: inline-block;
        background-color: #e8f4fd;
        color: #1f77b4;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 12px;
        margin: 2px;
    }
    /* 来源标签样式 */
    .source-tag {
        display: inline-block;
        background-color: #f0f7e8;
        color: #2e7d32;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 12px;
        margin: 2px;
    }
    /* 预警卡片样式 */
    .alert-card {
        padding: 10px;
        border-radius: 8px;
        margin: 5px 0;
    }
    .alert-urgent {
        background-color: #ffebee;
        border-left: 4px solid #f44336;
    }
    .alert-warning {
        background-color: #fff8e1;
        border-left: 4px solid #ff9800;
    }
</style>
""", unsafe_allow_html=True)


# ==================== API调用函数 ====================
# Streamlit作为纯前端，所有Agent请求都通过HTTP调FastAPI

def call_agent_api(query: str) -> dict:
    """
    调用FastAPI的/ask接口，获取Agent回答
    Streamlit不创建Agent对象，只发HTTP请求

    参数:
        query: 用户的自然语言问题
    返回:
        包含answer、tools_used、sources的字典
    """
    try:
        response = requests.post(
            f"{API_BASE_URL}/ask",
            json={"query": query},
            timeout=120  # Agent推理可能需要较长时间
        )
        if response.status_code == 200:
            data = response.json()
            return {
                "answer": data.get("answer", ""),
                "tools_used": data.get("tools_used", []),
                "sources": data.get("sources", [])
            }
        else:
            return {
                "answer": f"❌ 后端服务返回错误（状态码{response.status_code}），请检查FastAPI是否正常运行。",
                "tools_used": [],
                "sources": []
            }
    except requests.exceptions.ConnectionError:
        return {
            "answer": "❌ 无法连接后端服务，请先启动FastAPI：\n`uvicorn rag_api:app --host 0.0.0.0 --port 8001`",
            "tools_used": [],
            "sources": []
        }
    except Exception as e:
        return {
            "answer": f"❌ 请求出错：{str(e)}",
            "tools_used": [],
            "sources": []
        }


def call_order_api(sku_id: str, quantity: int, supplier_id: str) -> str:
    """
    调用FastAPI的/order接口，模拟下单
    """
    try:
        response = requests.post(
            f"{API_BASE_URL}/order",
            json={"sku_id": sku_id, "quantity": quantity, "supplier_id": supplier_id},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get("message", "下单成功")
        else:
            return f"下单失败（状态码{response.status_code}）"
    except Exception as e:
        return f"下单请求出错：{str(e)}"


def check_backend_health() -> bool:
    """
    检查FastAPI后端是否可用
    """
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=3)
        return response.status_code == 200
    except:
        return False


# ==================== Session State 初始化 ====================

def init_session_state():
    """初始化会话状态变量"""
    if "chat_history" not in st.session_state:
        # 对话历史记录
        st.session_state.chat_history = []

    if "inventory_df" not in st.session_state:
        # 加载库存数据到session（看板展示用，直接读本地CSV即可）
        st.session_state.inventory_df = _load_inventory()

    if "suppliers_df" not in st.session_state:
        # 加载供应商数据到session
        st.session_state.suppliers_df = _load_suppliers()


# ==================== 主界面渲染 ====================

def render_header():
    """渲染页面顶部标题"""
    st.markdown('<div class="main-title">🏭 供应链自动补货顾问</div>', unsafe_allow_html=True)
    # 检查后端连接状态
    if check_backend_health():
        st.success("✅ 后端服务已连接")
    else:
        st.error("❌ 后端服务未连接，请先启动FastAPI：`uvicorn rag_api:app --host 0.0.0.0 --port 8001`")
    st.markdown("---")


def render_chat_area():
    """
    渲染左侧对话区域
    对话请求全部走FastAPI后端API
    """
    st.subheader("💬 智能对话")

    # ---- 显示对话历史 ----
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.write(msg["content"])
        else:
            with st.chat_message("assistant"):
                st.write(msg["content"])
                if msg.get("tools_used"):
                    tools_html = "🔧 使用工具: " + " ".join(
                        [f'<span class="tool-tag">{t}</span>' for t in msg["tools_used"]]
                    )
                    st.markdown(tools_html, unsafe_allow_html=True)
                if msg.get("sources"):
                    sources_html = "📚 知识来源: " + " ".join(
                        [f'<span class="source-tag">{s}</span>' for s in msg["sources"]]
                    )
                    st.markdown(sources_html, unsafe_allow_html=True)

    # ---- 用户输入区 ----
    if prompt := st.chat_input("请输入您的问题，例如：SKU001库存够不够？需要补货吗？"):
        st.session_state.chat_history.append({
            "role": "user",
            "content": prompt
        })

        with st.chat_message("user"):
            st.write(prompt)

        # 调用FastAPI后端获取Agent回答（不再直接调Agent）
        with st.chat_message("assistant"):
            with st.spinner("🤔 正在思考中..."):
                result = call_agent_api(prompt)   # ← 唯一改动：走API

            st.write(result["answer"])
            if result["tools_used"]:
                tools_html = "🔧 使用工具: " + " ".join(
                    [f'<span class="tool-tag">{t}</span>' for t in result["tools_used"]]
                )
                st.markdown(tools_html, unsafe_allow_html=True)
            if result["sources"]:
                sources_html = "📚 知识来源: " + " ".join(
                    [f'<span class="source-tag">{s}</span>' for s in result["sources"]]
                )
                st.markdown(sources_html, unsafe_allow_html=True)

        st.session_state.chat_history.append({
            "role": "assistant",
            "content": result["answer"],
            "tools_used": result["tools_used"],
            "sources": result["sources"]
        })


def render_inventory_dashboard():
    """渲染右上方的库存看板"""
    st.subheader("📊 库存看板")
    df = st.session_state.inventory_df

    col1, col2, col3 = st.columns(3)
    status_counts = df["status"].value_counts()
    normal_count = status_counts.get("正常", 0)
    warning_count = status_counts.get("预警", 0)
    urgent_count = status_counts.get("紧急", 0)

    with col1:
        st.metric("🟢 正常", f"{normal_count} 个SKU")
    with col2:
        st.metric("🟡 预警", f"{warning_count} 个SKU", delta=f"-{warning_count}", delta_color="inverse")
    with col3:
        st.metric("🔴 紧急", f"{urgent_count} 个SKU", delta=f"-{urgent_count}", delta_color="inverse")

    st.markdown("---")
    st.write("**各品类库存状态分布**")
    category_status = df.groupby(["category", "status"]).size().unstack(fill_value=0)
    for col in ["正常", "预警", "紧急"]:
        if col not in category_status.columns:
            category_status[col] = 0
    st.dataframe(category_status[["正常", "预警", "紧急"]], use_container_width=True)


def render_alert_list():
    """渲染右中方的预警SKU列表"""
    st.subheader("⚠️ 预警列表")
    df = st.session_state.inventory_df
    alert_df = df[df["status"].isin(["预警", "紧急"])].copy()

    if alert_df.empty:
        st.info("✅ 当前无预警信息，所有商品库存正常。")
        return

    alert_df = alert_df.sort_values("status", key=lambda x: x.map({"紧急": 0, "预警": 1}))

    for _, row in alert_df.iterrows():
        gap = row["safety_stock"] - row["current_stock"]
        days_left = round(row["current_stock"] / row["daily_demand"], 1) if row["daily_demand"] > 0 else 0

        if row["status"] == "紧急":
            css_class = "alert-urgent"
            emoji = "🔴"
        else:
            css_class = "alert-warning"
            emoji = "🟡"

        st.markdown(f"""
        <div class="alert-card {css_class}">
            {emoji} <b>{row['sku_id']}</b> {row['sku_name']}<br>
            当前: <b>{row['current_stock']}</b>件 | 安全库存: {row['safety_stock']}件 |
            缺口: <b>{gap}</b>件 | 仅够 <b>{days_left}</b>天
        </div>
        """, unsafe_allow_html=True)


def render_reorder_suggestions():
    """渲染右下方的补货建议列表"""
    st.subheader("📝 快捷补货")
    df = st.session_state.inventory_df
    alert_df = df[df["status"].isin(["预警", "紧急"])].copy()

    if alert_df.empty:
        st.info("✅ 暂无需补货的SKU。")
        return

    for _, row in alert_df.iterrows():
        gap = row["safety_stock"] - row["current_stock"]
        suggested_qty = gap + int(row["daily_demand"] * row["lead_time_days"])

        with st.expander(
            f"{'🔴' if row['status'] == '紧急' else '🟡'} "
            f"{row['sku_id']} {row['sku_name']} — 建议补货 {suggested_qty} 件"
        ):
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**当前库存**: {row['current_stock']}件")
                st.write(f"**安全库存**: {row['safety_stock']}件")
                st.write(f"**日均需求**: {row['daily_demand']}件/天")
            with col2:
                st.write(f"**采购提前期**: {row['lead_time_days']}天")
                st.write(f"**单位成本**: ¥{row['unit_cost']}")
                st.write(f"**默认供应商**: {row['supplier_id']}")

            order_qty = st.number_input("订货数量", min_value=1, value=suggested_qty, key=f"qty_{row['sku_id']}")
            supplier_id = st.text_input("供应商编号", value=row['supplier_id'], key=f"sup_{row['sku_id']}")

            if st.button(f"📦 下单 {row['sku_id']}", key=f"order_{row['sku_id']}"):
                # 调用FastAPI后端下单接口（不再直接调工具）
                result = call_order_api(row['sku_id'], order_qty, supplier_id)   # ← 走API
                st.success(f"下单成功！\n{result}")


def render_quick_questions():
    """渲染快捷问题按钮"""
    st.subheader("💡 快捷提问")

    quick_questions = [
        "有哪些商品库存不足？",
        "SKU001的库存情况怎么样？",
        "电子元器件品类有哪些预警？",
        "安全库存应该怎么设置？",
        "紧急补货流程是什么？",
        "帮我看看办公用品的库存"
    ]

    cols = st.columns(2)
    for idx, question in enumerate(quick_questions):
        with cols[idx % 2]:
            if st.button(question, key=f"quick_{idx}"):
                st.session_state.chat_history.append({
                    "role": "user",
                    "content": question
                })
                with st.spinner("🤔 正在思考中..."):
                    result = call_agent_api(question)   # ← 走API
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": result["answer"],
                    "tools_used": result["tools_used"],
                    "sources": result["sources"]
                })
                st.rerun()


# ==================== 主程序入口 ====================

def main():
    """主函数：渲染整个Streamlit页面"""
    init_session_state()
    render_header()

    col_chat, col_dashboard = st.columns([3, 2])

    with col_chat:
        render_chat_area()
        st.markdown("---")
        render_quick_questions()

    with col_dashboard:
        render_inventory_dashboard()
        st.markdown("---")
        render_alert_list()
        st.markdown("---")
        render_reorder_suggestions()


if __name__ == "__main__":
    main()
