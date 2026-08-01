# 資料格式

這份文件說明 `data/` 底下每個資料夾放什麼、欄位怎麼填。

背後的決定見 [ADR-0008](decisions/0008-curate-in-sql-serve-from-json.md):
蒐集與審核在 SQL 進行,**已確認**的記錄匯出成這裡的 JSON,系統執行時只讀 JSON。

## 用一本手冊來想

```
entitlement_graph/   手冊最前面的流程圖    「發生這件事,要辦哪些」
benefits/            每項福利的介紹頁      「這是什麼、去哪辦、帶什麼」
rules/               介紹頁上的申請資格欄   「誰可以申請」
provisions/          手冊最後的法條附錄     「法規原文怎麼寫」
evaluations/         校對用的範例與答案     「怎麼知道規則寫對了」
```

由粗到細:**發生什麼事 → 要辦哪些 → 誰能辦 → 法條怎麼寫的。**

## 填寫順序

前三層**不管走哪條路線都需要**,先做這三個:

1. `entitlement_graph/` — 一個人生事件一個檔
2. `benefits/` — 一項福利一個檔
3. `provisions/` — 一條法條一個檔

`rules/` 只有選定要做深度判定的那 1–2 項才需要,見
[hackathon-plan.md](hackathon-plan.md) 的範圍決定。

---

## 1. `entitlement_graph/` — 流程圖

一個人生事件一個檔,描述牽動哪些事項與先後順序。

```json
{
  "life_event": "spouse_death",
  "label": "配偶死亡",
  "steps": [
    { "benefit_id": "death_registration", "order": 1,
      "produces": ["除戶謄本"] },
    { "benefit_id": "nhi_status_change", "order": 2,
      "requires": ["除戶謄本"] },
    { "benefit_id": "labor_funeral_grant", "order": 2,
      "requires": ["除戶謄本"] },
    { "benefit_id": "survivor_pension", "order": 3,
      "requires": ["除戶謄本"] }
  ]
}
```

| 欄位 | 說明 |
|---|---|
| `life_event` | 事件代號,LLM 萃取時只能吐出這裡有的值 |
| `order` | 第幾順位辦理。同數字表示可並行 |
| `produces` | 辦完會拿到什麼(後續項目會用到) |
| `requires` | 需要先取得什麼才能辦 |

## 2. `benefits/` — 福利介紹頁

一項福利一個檔。**這一層不放資格條件。**

以審查介面裡的「新北市環保葬鼓勵金」為例:

```json
{
  "benefit_id": "nwt_eco_burial_grant",
  "name": "新北市環保葬鼓勵金",
  "summary": "為提高設施使用效率、減少建設費用支出、逐步推動公墓禁葬事宜訂定之鼓勵金發放計畫。",

  "county": "NWT",
  "purpose": "funeral_cost",
  "basis": "government_subsidy_or_relief",
  "payment_form": "cash_once",

  "agency": { "role": "application_contact",
              "name": "新北市政府殯葬管理處" },

  "applicant_note": "申請人及亡者不限新北市民",
  "deadline_note": "自本市公立納骨塔遷出或自本市公墓起掘骨灰(骸)次日起 1 年內完成環保葬;完成環保葬次日起 1 個月內臨櫃申辦",
  "exclusions": null,

  "documents_required": [],
  "notes": "頁面未詳列應備文件,僅提供委託書、申請書、領據下載連結。實際應備文件可能需查閱申請書內容或致電確認。",

  "rule_id": null,
  "provision_ids": ["nwt-eco-01"],

  "source": {
    "url": "https://…",
    "publisher": "新北市政府殯葬管理處",
    "published_at": "2024-11-01",
    "retrieved_at": "2026-07-26"
  },
  "verified_by": "…",
  "verified_at": "2026-07-26"
}
```

### 幾個要注意的欄位

**`county`、`purpose`、`basis`、`payment_form` 是 enum。**
只能填已定義的值。這些同時是 LLM 萃取時的**輸出詞彙表**——模型只能吐出這些值,吐別的會被程式拒絕。

**`exclusions`(互斥條件)不確定時填 `null`,不要留空字串。**
`null` 代表「尚未查證」,程式會在輸出加上提醒;空字串會被當成「查證過,沒有互斥條件」。這兩件事差很多。

**`published_at` 和 `retrieved_at` 是兩件事。**
前者是法規生效日(判斷適不適用),後者是你查到它的日期(判斷資料新不新)。兩個都要。

**`rule_id` 沒有做深度判定的項目就填 `null`。**
系統會把這一項當成導航資訊呈現,並標示「未經資格判定」。

## 3. `rules/` — 申請資格

只有要做深度判定的項目需要。條件必須拆解到程式可以比對。

```json
{
  "rule_id": "NWT-ECO-001",
  "benefit_id": "nwt_eco_burial_grant",
  "version": "2026-07",
  "source": {
    "url": "https://…",
    "provision_ids": ["nwt-eco-01"],
    "retrieved_at": "2026-07-26"
  },
  "required_attributes": [
    "origin_facility_county",
    "days_since_exhumation",
    "days_since_eco_burial"
  ],
  "logic": {
    "all_of": [
      { "id": "c1", "label": "骨灰自新北市公立納骨塔或公墓起掘",
        "field": "origin_facility_county", "op": "==", "value": "NWT" },
      { "id": "c2", "label": "起掘次日起 1 年內完成環保葬",
        "field": "days_since_exhumation", "op": "<=", "value": 365 },
      { "id": "c3", "label": "完成環保葬次日起 1 個月內臨櫃申辦",
        "field": "days_since_eco_burial", "op": "<=", "value": 30 }
    ]
  },
  "notes": "申請人與亡者不限新北市民,因此不需詢問戶籍"
}
```

> 以上條件為依審查介面內容整理的**示意**,實際條號與門檻以官方文件為準。

### 為什麼要 `label` 和 `id`

判定結果會回報「差在哪一條」,靠的就是這兩個欄位。使用者看到的
「您未滿 55 歲」就是某個條件的 `label`。

### `required_attributes` 決定系統要問什麼

系統從這裡反推該向使用者詢問哪些欄位。**沒列進來的欄位不會被問**,
所以漏了會導致該問的沒問。

拆解過程也會告訴你**哪些不用問**——例如上例的「不限新北市民」代表
戶籍這題不必問,寫在 `notes` 讓後續維護的人知道這不是漏掉。

### 支援的運算子

`==`、`!=`、`>=`、`<=`、`>`、`<`、`in`、`not_in`

組合器:`all_of`(全部成立)、`any_of`(其一成立),可以巢狀。

## 4. `provisions/` — 法條原文

**一條一個檔。不要按字數切。**

```json
{
  "provision_id": "nwt-eco-01",
  "law": "新北市環保葬鼓勵金發放計畫",
  "article": "三、申請條件",
  "text": "〔完整原文,不要截斷〕",
  "version": "2026-07",
  "url": "https://…",
  "publisher": "新北市政府殯葬管理處",
  "retrieved_at": "2026-07-26",
  "note": "申請條件與期限"
}
```

按字數機械切分會把「符合下列條件之一:一、… 二、… 三、…」從中間切斷,
造成判定時只看到前兩款而不知道有第三款。按「條」或「款」切,語意才完整。

**排除規定、但書、擇一條款要各自建檔**,並列進對應福利的 `provision_ids`。
這些最容易被漏掉,而漏掉不會有任何錯誤訊息。

## 5. `evaluations/` — 測試案例

每個做了規則的福利,至少三個案例:符合、不符合、邊界。

```json
[
  { "case_id": "nwt-eco-01", "note": "期限內,符合",
    "attributes": { "origin_facility_county": "NWT",
                    "days_since_exhumation": 200,
                    "days_since_eco_burial": 12 },
    "expect": { "status": "eligible" } },

  { "case_id": "nwt-eco-02", "note": "超過申辦期限",
    "attributes": { "origin_facility_county": "NWT",
                    "days_since_exhumation": 200,
                    "days_since_eco_burial": 45 },
    "expect": { "status": "ineligible", "failed": ["c3"] } },

  { "case_id": "nwt-eco-03", "note": "邊界:剛好第 30 天",
    "attributes": { "origin_facility_county": "NWT",
                    "days_since_exhumation": 200,
                    "days_since_eco_burial": 30 },
    "expect": { "status": "eligible" } }
]
```

**邊界案例最重要**——`<=` 和 `<` 寫錯只有邊界案例抓得到。

## 系統執行時怎麼用這些檔案

啟動時全部載入記憶體,查詢就是過濾:

```python
candidates = [
    b for b in BENEFITS
    if b["purpose"] == "funeral_cost"
    and b["county"] in ("NWT", None)      # None = 全國適用
]
```

法條是**直接查表**取得,不是語意搜尋:

```python
texts = [PROVISIONS[pid] for pid in benefit["provision_ids"]]
```

這是完整性的保證來源——要看哪幾條是事先對應好的,不由相似度排序決定。

語意搜尋只用在一種情況:使用者描述模糊,系統要判斷他講的是哪一項福利。

## 相關文件

- [ADR-0008](decisions/0008-curate-in-sql-serve-from-json.md) — 為什麼這樣分工
- [ADR-0007](decisions/0007-limit-data-retention-and-egress.md) — 隱私邊界
- [hackathon-plan.md](hackathon-plan.md) — 範圍與交付順序
- [positioning.md](positioning.md) — 為什麼需要可稽核的資料
