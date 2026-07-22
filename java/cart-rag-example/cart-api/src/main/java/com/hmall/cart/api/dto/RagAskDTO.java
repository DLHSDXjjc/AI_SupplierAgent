package com.hmall.cart.api.dto;

import io.swagger.annotations.ApiModel;
import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

@Data
@ApiModel(description = "RAG 问答请求实体")
public class RagAskDTO {
    @ApiModelProperty(value = "用户提问的自然语言问题", required = true, example = "SKU001库存够不够？要不要补货？")
    private String query;
}
