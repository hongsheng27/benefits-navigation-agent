# 快速上手指南

讓前後端在本機跑起來，連接共用的 AWS RDS PostgreSQL 資料庫。

## 前置條件

- Python 3.13+（`python --version`）
- Node.js 18+（`node --version`）
- [uv](https://docs.astral.sh/uv/getting-started/installation/) Python 套件管理器
- 有效的 AWS 臨時憑證（從 Workshop Studio 取得）

## 步驟

### 1. 設定環境變數

```bash
# 在專案根目錄
cp .env.example .env
```

編輯 `.env`，填入你的 AWS 臨時憑證：
```
AWS_ACCESS_KEY_ID=（貼上你的）
AWS_SECRET_ACCESS_KEY=（貼上你的）
AWS_SESSION_TOKEN=（貼上你的）
```

RDS 和 Bedrock 設定已經預填好，不需要改。

### 2. Backend

```bash
cd backend
uv sync          # 安裝所有 Python 依賴（包含 boto3）
```

啟動：
```bash
.venv/bin/uvicorn app.main:create_app --factory --reload --reload-exclude .venv --port 8000
```

看到 `Application startup complete.` 就是成功。

### 3. Frontend

```bash
cd frontend
cp .env.example .env    # 預設指向 localhost:8000
npm install
npm run dev
```

打開 http://localhost:5173/ 即可使用。

## 測試流程

1. 在輸入框描述你的情境，例如：「我失業了」、「爸爸工作受傷」、「家人需要長照」
2. 確認系統辨識出的生命事件
3. 回答追問的欄位
4. 查看最終的補助方案建議

## 常見問題

### Bedrock 呼叫失敗
- 檢查 AWS 憑證是否過期（臨時憑證有時效）
- 執行 `aws sts get-caller-identity` 確認憑證有效

### RDS 連不上
- 確認你的 IP 有被 RDS Security Group 允許（port 5432）
- 確認 RDS instance 設為 Publicly Accessible

### boto3 沒有安裝
- 執行 `cd backend && uv sync` 會自動安裝所有依賴

## EC2 部署（生產環境）

EC2 IP: `35.88.159.212`
- Backend 跑在 port 8000
- 前端 build 後由 nginx 提供服務（port 80）
- 部署腳本見 `scripts/deploy_ec2.sh`（待建立）
