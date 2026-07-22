"""
供应链自动补货Agent — 核心模块

功能：
1. 初始化 LangChain ReAct Agent
2. 管理工具注册和Prompt配置
3. 提供对话接口，支持流式和非流式输出
4. 记录工具调用过程，供前端展示

【我们没写调度逻辑，调度是 LangChain 框架做的】
我们只负责3件事：
1. 选LLM（DeepSeek）
2. 注册工具（8个@tool函数）
3. 写Prompt（System Prompt + ReAct模板）

调度是 LLM 自己推理的：读工具描述 → 判断调哪个 → 传参数 → 看结果 → 继续或回答

使用方式:
    from agent.agent_core import SupplyChainAgent
    agent = SupplyChainAgent()           # __init__自动执行，加载LLM+工具
    result = agent.chat("SKU001的库存够不够？")  # 调用Agent

【SupplyChainAgent 在哪里被创建？】
只在 FastAPI 后端（rag_api.py）的 lifespan 函数中创建一次
服务启动时创建，所有用户请求共用这一个对象
Streamlit 前端不创建Agent，通过HTTP调FastAPI的/ask接口
"""

import os
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.prompts import PromptTemplate

# ==================== 导入配置 ====================
import sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config.config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    DEEPSEEK_TEMPERATURE, DEEPSEEK_MAX_TOKENS
)

# ==================== 导入工具和Prompt ====================
# ALL_TOOLS 包含8个@tool函数，在 tools/__init__.py 中汇总导出
from tools import ALL_TOOLS
from agent.prompts import SYSTEM_PROMPT, REACT_TEMPLATE


class SupplyChainAgent:
    """
    供应链自动补货Agent核心类

    【__init__ 是Python的构造函数】
    当 SupplyChainAgent() 被调用时自动执行，不需要手动调
    相当于 Java 的构造函数，在 new 的时候自动执行
    """

    def __init__(self, verbose: bool = True):
        """
        初始化Agent

        【__init__什么时候需要定义？】
        当对象创建时需要做初始化工作的时候
        我们这里需要加载LLM、注册工具、创建Agent执行器，所以必须写__init__

        参数:
            verbose: 是否打印Agent的推理过程（默认True，方便调试）
        """
        self.verbose = verbose
        self._tools_used = []

        # ---- 1. 初始化LLM ----
        # 使用 LangChain 的 ChatOpenAI，兼容所有 OpenAI 格式的 API
        # 换模型只需改 config/modelConfig.yaml 里的 base_url 和 model
        print("[Agent] 正在初始化LLM...")
        self.llm = ChatOpenAI(
            model=DEEPSEEK_MODEL,
            base_url=DEEPSEEK_BASE_URL,
            api_key=DEEPSEEK_API_KEY,
            temperature=DEEPSEEK_TEMPERATURE,
            max_tokens=DEEPSEEK_MAX_TOKENS,
        )
        print(f"[Agent] LLM初始化完成: {DEEPSEEK_MODEL}")

        # ---- 2. 创建Prompt模板 ----
        self.prompt = self._create_prompt()

        # ---- 3. 创建ReAct Agent ----
        # 【create_react_agent 做了什么？】
        # 把 LLM + 工具 + Prompt 组装成一个Agent对象
        # 内部自动从 ALL_TOOLS 提取每个工具的名称、描述、参数
        # 拼成文本填入 Prompt 模板的 {tools} 和 {tool_names} 位置
        # 返回的Agent对象知道怎么调用LLM和工具
        print("[Agent] 正在创建ReAct Agent...")
        self.agent = create_react_agent(
            llm=self.llm,
            tools=ALL_TOOLS,
            prompt=self.prompt
        )

        # ---- 4. 创建Agent执行器 ----
        # 【AgentExecutor 内部的核心循环（不是我们写的，框架自动执行）】
        # while 迭代次数 < max_iterations:
        #     1. 把工具列表+历史+用户问题发给LLM
        #     2. 解析LLM输出，判断是调工具还是给最终回答
        #     3. 如果是调工具：执行工具，把结果加入历史，继续循环
        #     4. 如果是Final Answer：返回最终回答
        #     5. 如果格式不对：调用 _handle_parsing_error 给纠正提示
        print("[Agent] 正在创建Agent执行器...")
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=ALL_TOOLS,
            verbose=self.verbose,
            max_iterations=20,           # 最大推理轮数
            max_execution_time=120,      # 最大执行时间120秒
            handle_parsing_errors=self._handle_parsing_error,
            return_intermediate_steps=True  # 返回中间步骤（工具调用记录）
        )
        print(f"[Agent] Agent创建完成，已注册 {len(ALL_TOOLS)} 个工具")

    def _create_prompt(self) -> PromptTemplate:
        """
        创建ReAct Agent使用的Prompt模板

        【Prompt模板的填充顺序】
        1. partial() 启动时填 {system_prompt}  → 固定不变的人设
        2. create_react_agent() 启动时填 {tools} {tool_names}  → 工具信息
        3. invoke({"input": query}) 用户提问时填 {input}  → 用户问题
        4. AgentExecutor 每轮推理自动填 {agent_scratchpad}  → 推理历史
           每轮推理后追加上一轮的 Thought/Action/Observation，让LLM记住之前干了什么
        """
        prompt = PromptTemplate.from_template(REACT_TEMPLATE)
        # 先填固定不变的部分（system_prompt），剩下的后面再填
        prompt = prompt.partial(system_prompt=SYSTEM_PROMPT)
        return prompt

    @staticmethod
    def _handle_parsing_error(error) -> str:
        """
        自定义解析错误处理

        【LLM有时不按ReAct格式输出，例如】
        ✅ 正确：Thought: 需要查库存 → Action: inventory_query → Action Input: {"sku_id":"SKU001"}
        ❌ 错误：我觉得应该查一下SKU001的库存（没按格式写）
        ❌ 错误：Action: query_inventory（工具名写错了，应该是inventory_query）

        【有没有这个函数的区别】
        没有：返回一大段英文报错给LLM，LLM看了更懵，可能继续格式错误
        有：返回简洁的中文纠正提示，LLM一看就知道该怎么改
        """
        return (
            "格式错误，请严格按以下格式回复：\n"
            "Thought: 你的思考\n"
            "Action: 工具名称\n"
            "Action Input: JSON参数\n"
            "或者直接：\n"
            "Thought: 我已知道答案\n"
            "Final Answer: 回答内容"
        )

    def chat(self, query: str) -> dict:
        """
        与Agent对话的主接口

        【完整调用链路】
        用户请求 → FastAPI /ask → agent.chat() → agent_executor.invoke()
        → 把 input 填入 Prompt 模板 → 发给 LLM 推理 → 调工具 → 循环 → 返回最终回答

        参数:
            query: 用户的自然语言问题
        返回:
            包含回答、工具调用记录、来源信息的字典
        """
        self._tools_used = []

        try:
            # agent_executor.invoke() 做了什么？
            # 1. 把用户问题填入 Prompt 的 {input}
            # 2. 把 AgentExecutor 自动填 {agent_scratchpad}
            # 3. 发给 LLM 推理
            # 4. LLM自己决定调哪个工具、传什么参数（靠读@tool的docstring描述）
            # 5. 框架解析LLM输出，调用对应的@tool函数
            # 6. 把工具结果加入历史，继续循环
            # 7. 直到LLM给出 Final Answer
            result = self.agent_executor.invoke({"input": query})

            # 从原始结果中提取3样东西，方便前端分别展示：
            # 1. answer → 显示在对话区
            # 2. tools_used → 显示工具标签 🔧 inventory_query | reorder_calculator
            # 3. sources → 显示来源标签 📚 补货策略
            intermediate_steps = result.get("intermediate_steps", [])
            tools_used = []
            sources = []

            for step in intermediate_steps:
                # step 是 (AgentAction, observation) 的元组
                # action = LLM决定调什么工具（工具名+参数）
                # observation = 工具执行后返回的结果文本
                action, observation = step
                tool_name = action.tool
                if tool_name not in tools_used:
                    tools_used.append(tool_name)

                # 从knowledge_search的观察结果中提取来源
                if tool_name == "knowledge_search" and "来源:" in observation:
                    import re
                    source_matches = re.findall(r"来源: ([^|]+)", observation)
                    for s in source_matches:
                        if s.strip() not in sources:
                            sources.append(s.strip())

            return {
                "answer": result.get("output", ""),
                "tools_used": tools_used,
                "sources": sources
            }

        except Exception as e:
            error_msg = str(e)
            print(f"[Agent] 对话出错: {error_msg}")
            return {
                "answer": f"抱歉，处理您的问题时出现了错误：{error_msg}。请稍后重试或换一种方式提问。",
                "tools_used": [],
                "sources": []
            }

    def chat_stream(self, query: str):
        """
        流式对话接口

        【和 chat() 的区别】
        chat()        → 等全部生成完才返回（用户等10秒，一次性看到完整回答）
        chat_stream() → 边生成边返回（像ChatGPT那样逐字显示，用户体验更好）

        当前项目未使用，预留接口，以后对接流式输出时用
        """
        try:
            for chunk in self.agent_executor.stream({"input": query}):
                yield chunk
        except Exception as e:
            yield {"error": str(e)}

    def get_tools_info(self) -> list:
        """
        获取所有已注册工具的信息
        用于前端展示Agent的能力列表
        """
        return [
            {
                "name": tool.name,
                "description": tool.description.split("\n")[0]
            }
            for tool in ALL_TOOLS
        ]
