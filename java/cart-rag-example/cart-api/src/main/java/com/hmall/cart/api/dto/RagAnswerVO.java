package com.hmall.cart.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.annotations.ApiModel;
import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

import java.util.List;

@Data
@ApiModel(description = "RAG 问答响应实体")
public class RagAnswerVO {
    @ApiModelProperty("是否成功")
    private Boolean success;

    @ApiModelProperty("回显用户问题")
    private String query;

    @ApiModelProperty("Agent 生成的回答")
    private String answer;

    @ApiModelProperty("Agent 本次调用的工具列表")
    @JsonProperty("tools_used")
    private List<String> toolsUsed;

    @ApiModelProperty("知识库检索来源列表")
    private List<String> sources;
}
