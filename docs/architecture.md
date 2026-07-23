# Architecture

「接住」採用 privacy-first、policy-governed 的 modular monolith。下圖描述目前已確認的
模組責任與資料流；虛線節點代表 trial 或尚待技術驗證的選項，不是最終部署承諾。

## 系統架構圖

[![接住系統架構圖](architecture-overview.svg)](architecture-overview.svg)

可直接開啟 [SVG](architecture-overview.svg) 或 [PNG](architecture-overview.png) 查看原始尺寸。

## 單次請求流程

```mermaid
sequenceDiagram
    actor User as 使用者
    participant UI as React UI
    participant Privacy as Client Privacy Layer
    participant API as FastAPI
    participant Flow as State Machine
    participant Agent as AgentRunner / Strands
    participant Model as Amazon Bedrock
    participant Tools as Allowed Tools
    participant Retrieval as Official-source Retriever
    participant Rules as Eligibility Engine
    participant Human as 專業人員

    User->>UI: 描述人生事件
    UI->>Privacy: 偵測並遮罩 direct identifiers
    Privacy->>API: sanitized text + allowlisted attributes
    API->>Flow: 載入去識別化 session 與目前狀態

    alt 需要語意理解或 grounded explanation
        Flow->>Agent: task + allowed tools + execution limits
        Agent->>Model: model invocation
        Model-->>Agent: structured response 或 tool request
        Agent->>Tools: 執行狀態允許的 tool
        opt 需要官方依據
            Tools->>Retrieval: 查詢限定範圍的官方文件
            Retrieval-->>Tools: evidence + citation metadata
        end
        opt 需要資格判斷
            Tools->>Rules: 結構化屬性 + versioned rules
            Rules-->>Tools: eligible / ineligible / needs information / human review
        end
        Tools-->>Agent: validated tool result
        Agent-->>Flow: project-owned structured AgentResult
    else 純確定性步驟
        Flow->>Rules: 執行 transition guard 或資格規則
        Rules-->>Flow: deterministic result
    end

    alt 缺少必要資訊
        Flow-->>API: 下一個 allowlisted question
        API-->>UI: 顯示缺漏問題
        UI-->>User: 請使用者補充或修正
    else 需要人工判斷
        Flow-->>Human: 提供轉介與待確認事項
        Flow-->>API: needs human review
        API-->>UI: 顯示人工協助入口
    else 可以完成
        Flow-->>API: 資格結果、理由、citations、checklist
        API-->>UI: 顯示結果並要求重要步驟確認
    end
```

## 控制與責任邊界

- Client 保留姓名、身分證字號、地址、電話與 email；backend 只接收 sanitized text 與
  allowlisted eligibility attributes。
- State machine 擁有狀態轉換、tool allowlist、迭代上限、錯誤處理與人工確認。
- Agent / LLM 只負責語意工作，不得自行判斷或覆寫福利資格。
- Eligibility engine 是資格狀態的唯一決策者；Retriever 只回傳可引用的官方依據。
- Strands、Bedrock model、retrieval implementation、session persistence 與 AgentCore
  deployment 都保留在自有 interface 後方，可在技術 spike 後替換。

已接受的決策與未決事項分別記錄於 [Architecture Decision Records](decisions/README.md)
與根目錄 [README](../README.md)。
