"""
_is_cacheable 纯函数单元测试。
跟 L1 规则一致:success ∧ answer非空 ∧ tools_used ⊆ {knowledge_search}。
"""
from agent.agent_core import SupplyChainAgent


class TestIsCacheable:
    def test_empty_response_not_cacheable(self):
        """空 answer 不缓存"""
        assert SupplyChainAgent._is_cacheable({"answer": "", "tools_used": [], "sources": []}) is False

    def test_missing_answer_field_not_cacheable(self):
        """answer 字段缺失不缓存"""
        assert SupplyChainAgent._is_cacheable({"tools_used": []}) is False

    def test_no_tools_used_is_cacheable(self):
        """空 tools_used(LLM 直答)算子集,可缓存"""
        assert SupplyChainAgent._is_cacheable({"answer": "答", "tools_used": [], "sources": []}) is True

    def test_only_knowledge_search_is_cacheable(self):
        """只有 knowledge_search 可缓存"""
        assert SupplyChainAgent._is_cacheable({"answer": "答", "tools_used": ["knowledge_search"], "sources": []}) is True

    def test_inventory_query_not_cacheable(self):
        """inventory_query(实时数据)不可缓存"""
        assert SupplyChainAgent._is_cacheable({"answer": "答", "tools_used": ["inventory_query"], "sources": []}) is False

    def test_mixed_tools_not_cacheable(self):
        """多工具混合不可缓存"""
        assert SupplyChainAgent._is_cacheable({"answer": "答", "tools_used": ["knowledge_search", "inventory_query"], "sources": []}) is False

    def test_order_simulator_not_cacheable(self):
        """place_order(操作类)不可缓存"""
        assert SupplyChainAgent._is_cacheable({"answer": "答", "tools_used": ["place_order"], "sources": []}) is False

    def test_success_false_not_cacheable(self):
        """success=False 不可缓存"""
        assert SupplyChainAgent._is_cacheable({"answer": "答", "tools_used": [], "sources": [], "success": False}) is False

    def test_whitespace_only_answer_not_cacheable(self):
        """只有空白的 answer 不缓存"""
        assert SupplyChainAgent._is_cacheable({"answer": "   ", "tools_used": [], "sources": []}) is False
