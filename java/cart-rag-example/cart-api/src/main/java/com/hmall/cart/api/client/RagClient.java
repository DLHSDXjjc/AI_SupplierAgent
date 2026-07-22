package com.hmall.cart.api.client;


import com.hmall.cart.api.dto.RagAnswerVO;
import com.hmall.cart.api.dto.RagAskDTO;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.*;

/**
 * 外部 Python RAG 微服务（供应链自动补货 Agent）
 * <p>Python 端 Nacos 注册名：supplychain-rag，端口 8001，实现见 rag_api.py</p>
 */
@FeignClient(name = "supplychain-rag")
public interface RagClient {

    /**
     * 调用 Agent /ask 接口，传入自然语言问题，返回结构化答案
     */
    @PostMapping("/ask")
    RagAnswerVO query(@RequestBody RagAskDTO request);

}
