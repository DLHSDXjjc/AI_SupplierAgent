# cart-rag-example · Spring Cloud 侧调用示例

本目录展示如何在 Spring Cloud 微服务里，通过 **OpenFeign + Nacos** 调用 `python/` 目录下的
供应链 RAG 微服务（`supplychain-rag`）。

代码抽自 `hmall/cart-service`，保留了原包名 `com.hmall.cart.*`。你可以直接把这四个文件
拷进你自己的 Spring Cloud 项目里使用。

## 📁 文件说明

```
cart-api/                                              # 对外可复用的 Feign 客户端
└── src/main/java/com/hmall/cart/api/
    ├── client/RagClient.java                          # Feign 客户端，服务名 supplychain-rag
    └── dto/
        ├── RagAskDTO.java                             # 请求体 { query: string }
        └── RagAnswerVO.java                           # 响应体 { success, query, answer, toolsUsed, sources }

cart-impl/                                             # 业务模块，向前端暴露 REST 接口
└── src/main/java/com/hmall/cart/controller/
    └── RagController.java                             # POST /rag/query → RagClient.query()
```

## 🔧 前置条件

1. **Spring Boot 2.7.x** + **Spring Cloud 2021.0.x** + **Spring Cloud Alibaba 2021.0.4.x**
2. 项目已引入下列依赖（`cart-api/pom.xml`）：
   - `spring-cloud-starter-openfeign`
   - `spring-cloud-starter-loadbalancer`
   - `swagger-annotations`
3. 启动类上开启 Feign：
   ```java
   @EnableFeignClients(basePackages = "com.hmall.cart.api.client")
   ```
4. `bootstrap.yaml` 已经指到同一个 Nacos，例如：
   ```yaml
   spring:
     cloud:
       nacos:
         server-addr: 192.168.203.129:8848
   ```

## 🚀 使用方式

Python 端启动后（见根 `README.md`），Java 端只要 Feign 能扫描到 `RagClient`，就能像调用本地 Bean 一样直接用：

```java
@RestController
@RequiredArgsConstructor
public class DemoController {
    private final RagClient ragClient;

    @GetMapping("/demo")
    public RagAnswerVO demo() {
        RagAskDTO req = new RagAskDTO();
        req.setQuery("SKU001 库存够不够？要不要补货？");
        return ragClient.query(req);
    }
}
```

或者通过 `RagController` 直接对外暴露：

```bash
curl -X POST http://<gateway>/cart/rag/query \
     -H "Content-Type: application/json" \
     -d '{"query":"SKU001 库存够不够？要不要补货？"}'
```

返回：

```json
{
  "success": true,
  "query": "SKU001 库存够不够？要不要补货？",
  "answer": "根据当前库存……",
  "toolsUsed": ["inventory_query", "knowledge_search"],
  "sources": ["安全库存政策.md", "紧急补货流程.md"]
}
```

## ⚠️ 注意事项

- **服务名必须一致**：Java 侧 `@FeignClient(name = "supplychain-rag")` 与 Python 侧
  `config/modelConfig.yaml` 里的 `nacos.service_name` 保持完全一致，否则找不到实例
- **超时**：RAG 涉及向量检索 + LLM 推理，建议把 Feign / Ribbon 的超时调高到 60 秒以上：
  ```yaml
  feign:
    client:
      config:
        supplychain-rag:
          connect-timeout: 5000
          read-timeout: 60000
  ```
- **熔断兜底**：`RagClient` 目前没有配 fallback，如果开了 Sentinel 且希望 RAG 不可用时不拖挂主链路，
  建议再加一个 `RagClientFallback` 实现类
