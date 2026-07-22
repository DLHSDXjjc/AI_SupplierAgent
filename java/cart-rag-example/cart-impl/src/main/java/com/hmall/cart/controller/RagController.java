package com.hmall.cart.controller;

import com.hmall.cart.api.client.RagClient;
import com.hmall.cart.api.dto.RagAnswerVO;
import com.hmall.cart.api.dto.RagAskDTO;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@Api(tags = "RAG 相关接口")
@RestController
@RequestMapping("/rag")
@RequiredArgsConstructor
public class RagController {

    private final RagClient ragClient;

    @ApiOperation("向供应链 RAG Agent 提问")
    @PostMapping("/query")
    public RagAnswerVO queryRag(@RequestBody RagAskDTO request) {
        return ragClient.query(request);
    }
}
