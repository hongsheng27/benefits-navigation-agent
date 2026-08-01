# Implementation Plan

- [x] 1. LLM 將 Case 2 描述萃取為 `occupational_injury`
- [x] 2. 第二頁由 backend snapshot 顯示事件確認
- [x] 3. 在後端 fixture 登記 Case 2 七個候選項目與 relevance predicates
- [x] 4. 在 field registry 登記四個主題、七個固定選項欄位
- [x] 5. 每次接受 attributes 後以最新答案重新查詢候選項目
- [x] 6. 保持候選資料 governance gate，全數回 `needs_human_review`
- [x] 7. 讓 frontend live 結果依父親／照顧者分組
- [x] 8. 新增後端完整流程、篩選邊界與前端 regression tests
- [x] 9. 更新 AWS migration guide
- [x] 10. 執行前後端測試、live API 流程與 `git diff --check`
- [ ] 11. 以 in-app browser 做人工點擊驗證（本次 session 未提供 browser control tool）
- [x] 12. 取消 frontend localStorage session restore，重新整理或重新進入時從頭開始
- [x] 13. 新增 legacy cached session 不會被復原的 regression test
- [x] 14. Case 2 第三頁選擇答案時不自動送出，改由使用者按「送出答案」
- [x] 15. 新增最後一題不自動進結果的 frontend regression test
- [x] 16. 將 LLM 事件契約改為 ordered `event_ids`，Case 2 同時萃取職災與長照
- [x] 17. 在 backend session 與 API snapshot 保留 `lifeEvents`，並以 primary `lifeEvent` 相容舊使用者
- [x] 18. 在前端確認、問題與結果畫面顯示複數事件並新增 regression tests
- [ ] 19. 重啟後端後以 live Bedrock 重跑 Case 2，確認新 schema 實際回傳職災與長照兩個 ID
- [x] 20. 將 multi-event 上限由 3 調整為 5，並驗證四個合法事件不會被誤判為無法辨識
- [x] 21. 以 live Bedrock 驗證複合描述的五個合法事件可全部寫入 `lifeEvents`

## Deferred SQLite Cutover

`origin/feat/databaseV3` 合併後，以 SQLite adapter 與 seed 取代 fixture。本批不複製該分支
的 schema、migration 或 composition root。
