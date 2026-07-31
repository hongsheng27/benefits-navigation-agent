# ADR-0014: Keep Fixture Data Out of the Verified Governance Status

- Status: Accepted
- Date: 2026-07-30

## Context

`backend/app/orchestration/determination.py` only runs a full deterministic
eligibility evaluation when a program's governance status is `verified`.
Everything else resolves to `needs_human_review`. The offline fixtures in
`backend/app/orchestration/protocols.py` are all `candidate`, so a complete
offline run currently settles every item as `needs_human_review` and never
reaches `eligible`.

That blocks demonstrating and verifying a full path end to end. The obvious
shortcut is to relabel one fixture as `verified`.

## Decision

**Fixture data is never marked `verified`.** A record may only carry `verified`
after a person has actually read the governing statute, confirmed the rule
conditions and the citation, and recorded that review.

The default offline implementations therefore keep their honest governance
status and continue to produce `needs_human_review`. Depth needed for demos,
manual verification, or tests is supplied by fixtures that are explicitly
labelled as demonstration data and that the caller must inject through the
named parameters of `state_machine.advance()`. Nothing in the default path
depends on them.

A genuine `eligible` outcome remains reachable, but only by the honest route:
one real human review of one item is enough, because the fixtures are already
narrow.

## Rationale

`program_status` exists to answer one question — how much can we trust this
record. Writing `verified` onto data nobody reviewed does not just produce one
inaccurate row; it removes the only thing the field was for, and leaves no
principled place to stop doing it again elsewhere.

The failure modes are also not symmetric. Saying "needs human review" when the
answer was actually "you qualify" costs the user a conversation. Saying "you
qualify" from unreviewed data sends someone who is arranging a funeral to a
government office for nothing. The cheaper error is the cautious one.

## Consequences

- A default offline run settles all four items as `needs_human_review`. This is
  correct behaviour and is documented for the frontend in
  `docs/front_back_doc/README.md`, so it is not reported as a defect.
- Tests that need a settled outcome must inject the decision explicitly. That is
  a benefit: the test states its own assumption instead of inheriting it.
- The demonstration path and the default path can diverge. Whatever is shown in
  a demo must therefore say plainly that its depth comes from demonstration
  data.
- This does not resolve where reviewed rules will eventually live. That is
  tracked with the SQLite work, not here.

---

# ADR-0014：示範資料不得標成已核對狀態

- 狀態：已接受
- 日期：2026-07-30

## 背景

`backend/app/orchestration/determination.py` 只有在一筆方案的資料治理狀態是
`verified`（已核對）時，才會執行完整的確定性資格判定，其餘一律回
`needs_human_review`（需人工協助）。而 `backend/app/orchestration/protocols.py`
裡的離線示範資料全部是 `candidate`（候選），所以現在跑完整條離線流程，四個項目
全部停在需人工協助，永遠走不到「符合資格」。

這擋住了「把一條完整的路從頭驗證到尾」。最省事的做法是把其中一筆改標成 `verified`。

## 決定

**示範資料一律不得標成 `verified`。** 一筆資料只有在真的有人讀過相關法規、確認過
規則條件與引用依據、而且那次審查被記錄下來之後，才可以帶這個狀態。

因此離線的預設實作維持誠實的治理狀態，繼續產出需人工協助。示範、手動驗證或測試
需要的深度，由**明確標示為示範用**的資料提供，而且呼叫端必須透過
`state_machine.advance()` 的具名參數主動注入才會生效 —— 預設路徑不依賴它們。

真正的「符合資格」仍然拿得到，但只能走誠實那條路：因為示範資料本來就窄，
只要有一項真的經過人工審查就夠了。

## 理由

`program_status` 這個欄位存在的意義只有一個 —— 回答「這筆資料可信到什麼程度」。
在沒人審查過的資料上寫 `verified`，代價不是多了一筆不準的資料，而是這個欄位失去了
它唯一的用途，而且之後沒有任何站得住腳的理由拒絕在別的地方也這樣做。

而且兩種錯的代價不對等。明明符合卻回「需要人看一下」，使用者損失的是多問一次；
拿沒人核對過的資料回「你符合」，是讓一個正在辦喪事的人白跑一趟公所。
比較便宜的那個錯誤是保守的那個。

## 後果

- 預設的離線流程會讓四個項目全部停在需人工協助。這是正確行為，已經寫進
  `docs/front_back_doc/README.md` 給前端，不會被當成缺陷回報。
- 需要「已定案結果」的測試必須自己把判定注入進去。這其實是好事：
  測試會把自己的假設寫出來，而不是繼承一個看不見的預設值。
- 示範用的路徑與預設路徑會不一致。所以任何示範的場合都必須講明：
  它能走到結論是因為用了示範資料。
- 這份決定**沒有**解決「經過審查的規則最後要存在哪裡」。那件事跟 SQLite 的工作
  一起追蹤，不在這裡。
