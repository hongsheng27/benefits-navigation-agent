# Backend

Backend 採用 Python **modular monolith**，負責 API、workflow state、Agent tools、
官方文件 retrieval、deterministic eligibility rules、隱私界線與 AWS adapters。

## 已確認方向

- 使用 **FastAPI** 作為主要 HTTP transport，負責 routing、request / response
  validation、dependency wiring 與 error mapping。
- Application services、workflow、rules、retrieval 與 Agent contracts 保持
  framework-neutral，不把 business logic 寫進 route handlers。
- 採用 policy-governed hybrid orchestration：state machine 控制狀態、允許的 tools、
  停止條件與人工確認；LLM 不直接決定福利資格。
- Strands Agents + Amazon Bedrock 先作為 `AgentRunner` 後方的可逆 trial；schemas、
  tools、rules 與 session state 不依賴 Strands-specific types。
- Raw Lambda handler 不列為 MVP 必要項目；若未來部署需要，只能作為 application
  service 前方的 thin adapter。

## 尚待驗證

- AgentCore Runtime 是否成為必要部署路徑，取決於比賽帳號權限與技術 spike。
- Bedrock model、retrieval / RAG、session persistence 與 IaC 選型尚未決定。

目前檔案主要建立模組邊界與待實作入口；實作前應先確認 API、Agent tool 與
workflow state contracts，讓 frontend、backend 與 policy modules 可以平行開發。
