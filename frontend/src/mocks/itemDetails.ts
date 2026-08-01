import type { ItemDetail } from "../types/itemDetail";

/**
 * 結果詳情示範資料（依 itemId）。
 * 金額／資格僅供畫面參考，不代表 deterministic eligibility 已判定。
 */
export const ITEM_DETAILS: Record<string, ItemDetail> = {
  death_registration: {
    itemId: "death_registration",
    location: "過世者戶籍地戶政事務所（部分縣市可線上預約）",
    amountLabel: "無給付金額（行政手續）",
    summary:
      "死亡登記是後續多數補助與繼承相關手續的起點。完成後才能取得除戶證明等文件。",
    agency: "戶政事務所（內政部戶政司規範）",
    eligibilityNotes: ["需為適格申請人（如配偶、親屬或受委任人）", "需備妥死亡證明文件"],
    steps: [
      "向醫院或相關單位取得死亡證明",
      "至戶籍地戶政辦理死亡登記",
      "領取除戶戶籍謄本等後續所需文件",
    ],
    documents: ["死亡證明書", "申請人身分證件", "戶口名簿（如有）"],
    officialUrl: "https://www.ris.gov.tw/",
  },
  funeral_benefit: {
    itemId: "funeral_benefit",
    location: "勞動部勞工保險局（可線上或臨櫃）",
    amountLabel: "依投保薪資計算（示意）",
    summary:
      "過世者生前有勞工保險時，符合條件的請領人可申請喪葬給付。請留意請領時效，建議取得文件後儘早提出。",
    agency: "勞動部勞工保險局",
    eligibilityNotes: [
      "過世者生前有勞工保險投保紀錄",
      "申請人為適格請領人身分",
      "需在規定時效內提出",
    ],
    steps: [
      "完成死亡登記並取得證明文件",
      "確認投保身分與請領人身分",
      "填寫申請書並檢附文件送件或線上申請",
    ],
    documents: [
      "喪葬給付申請書",
      "死亡證明或除戶戶籍謄本",
      "請領人與過世者關係證明",
      "請領人金融帳戶資料",
    ],
    officialUrl: "https://www.bli.gov.tw/",
  },
  survivor_pension: {
    itemId: "survivor_pension",
    location: "勞動部勞工保險局或國民年金相關窗口（依投保身分）",
    amountLabel: "依年資與投保薪資計算；未成年子女可能有加給",
    summary:
      "遺屬年金需確認過世者投保年資與請領人條件。是否加給會受家庭狀況影響，實際金額以承辦機關核定為準。",
    agency: "勞動部勞工保險局／衛生福利部（依制度）",
    eligibilityNotes: [
      "過世者投保年資達到門檻",
      "請領人符合遺屬資格",
      "需檢附關係與扶養相關證明",
    ],
    steps: [
      "確認投保制度（勞保／國保等）",
      "整理關係與扶養證明",
      "向對應機關提出遺屬年金申請",
    ],
    documents: [
      "遺屬年金申請書",
      "過世者投保資料",
      "戶籍謄本或關係證明",
      "未成年子女證明（如適用）",
    ],
    officialUrl: "https://www.bli.gov.tw/",
  },
  health_insurance_change: {
    itemId: "health_insurance_change",
    location: "健保署／投保單位或區公所（依投保身分）",
    amountLabel: "無現金給付（身分變更手續）",
    summary:
      "家中投保身分可能因喪偶等因素需要變更。先確認目前依附關係，再向對應窗口辦理。",
    agency: "衛生福利部中央健康保險署",
    eligibilityNotes: ["需確認目前健保依附或投保狀態", "備妥身分與戶籍相關文件"],
    steps: ["確認目前投保身分", "備妥證明文件", "向健保署或投保單位申請變更"],
    documents: ["身分證件", "戶口名簿或戶籍謄本", "相關證明文件"],
    officialUrl: "https://www.nhi.gov.tw/",
  },
  unemployment_benefit: {
    itemId: "unemployment_benefit",
    location: "公立就業服務機構辦理失業認定後，由勞保局核發",
    amountLabel: "依平均月投保薪資一定比例計算（示意）",
    summary:
      "非自願離職且符合投保與求職等條件時，可申請失業給付。需先完成失業認定與就業諮詢相關程序。",
    agency: "勞動部勞工保險局／勞動力發展署（就業服務）",
    eligibilityNotes: [
      "非自願離職",
      "就業保險投保年資符合規定",
      "有就業意願並依規定尋職",
    ],
    steps: [
      "取得非自願離職證明",
      "至就服機構辦理失業認定／就業諮詢",
      "依通知完成失業給付請領",
    ],
    documents: [
      "身分證件",
      "非自願離職證明",
      "存摺封面",
      "印章（臨櫃時）",
    ],
    officialUrl: "https://www.bli.gov.tw/",
  },
  employment_service: {
    itemId: "employment_service",
    location: "各地公立就業服務機構或台灣就業通",
    amountLabel: "諮詢服務，無固定金額",
    summary:
      "可透過就業服務取得求職媒合、職訓資訊與就業諮詢。與失業給付程序常一併進行。",
    agency: "勞動部勞動力發展署",
    eligibilityNotes: ["有就業或轉職需求即可洽詢", "部分方案另有資格條件"],
    steps: ["至就服機構或線上登記", "與就服員討論求職／職訓方向", "依建議參加媒合或訓練"],
    documents: ["身分證件", "履歷（建議自備）"],
    officialUrl: "https://www.taiwanjobs.gov.tw/",
  },
  occupational_injury_recognition: {
    itemId: "occupational_injury_recognition",
    location: "勞動部職業安全衛生署／勞保局相關窗口（依案情）",
    amountLabel: "認定本身無給付；通過後才進入給付申請",
    summary:
      "職災相關給付通常以職業災害認定為前提。尚未認定時，應先確認申請進度與應補文件。",
    agency: "勞動部（職安署／勞保局依程序）",
    eligibilityNotes: ["傷害或疾病與工作具相當因果關係", "依規定提出認定申請"],
    steps: [
      "蒐集就醫與工作相關證明",
      "提出職業災害認定申請",
      "依通知補件並追蹤結果",
    ],
    documents: ["申請書", "醫療診斷證明", "工作相關證明（依機關要求）"],
    officialUrl: "https://www.osha.gov.tw/",
  },
  occupational_injury_recognition_follow_up: {
    itemId: "occupational_injury_recognition_follow_up",
    location: "原受理職災認定之機關窗口",
    amountLabel: "無（進度追蹤）",
    summary:
      "職災認定申請中時，可先確認案件進度與是否需補件。本 app 不收公司或事故細節。",
    agency: "勞動部相關受理單位",
    eligibilityNotes: ["已提出認定申請或案件處理中"],
    steps: ["查詢案件進度", "依通知補件", "取得認定結果後再辦後續給付"],
    documents: ["案件編號或收執聯", "補件通知所列文件"],
    officialUrl: "https://www.osha.gov.tw/",
  },
  occupational_disability_benefit: {
    itemId: "occupational_disability_benefit",
    location: "勞動部勞工保險局",
    amountLabel: "依失能程度與投保薪資計算（示意）",
    summary:
      "職災失能／傷病給付需以認定與診斷為基礎。是否符合、金額多少由承辦機關依規定核定。",
    agency: "勞動部勞工保險局",
    eligibilityNotes: ["職業災害已認定或程序進行中", "符合傷病／失能給付要件"],
    steps: ["確認職災認定狀態", "備妥診斷與相關文件", "向勞保局提出給付申請"],
    documents: ["給付申請書", "診斷證明", "職災認定相關文件", "金融帳戶資料"],
    officialUrl: "https://www.bli.gov.tw/",
  },
  occupational_accident_disability_benefit: {
    itemId: "occupational_accident_disability_benefit",
    location: "勞動部勞工保險局（職災保險）",
    amountLabel: "依失能程度與投保薪資計算（示意）",
    summary:
      "職災保險失能給付需依認定、診斷與失能程度由承辦機關確認，示範資料不代表已核定。",
    agency: "勞動部勞工保險局",
    eligibilityNotes: ["有職災保險投保", "失能狀態符合請領要件"],
    steps: ["確認職災認定與診斷", "評估失能程度相關程序", "提出失能給付申請"],
    documents: ["申請書", "診斷與失能相關證明", "投保與身分文件"],
    officialUrl: "https://www.bli.gov.tw/",
  },
  disability_assessment: {
    itemId: "disability_assessment",
    location: "戶籍地公所／指定醫療院所",
    amountLabel: "鑑定手續；後續服務另計",
    summary:
      "身心障礙鑑定是銜接身障服務與部分照顧資源的常見步驟。可先向公所或醫療院所確認流程。",
    agency: "衛生福利部／地方政府社會局（依流程）",
    eligibilityNotes: ["有鑑定需求之身心狀況", "依縣市規定提出申請"],
    steps: ["向公所或醫院洽詢鑑定流程", "安排評估", "取得證明後銜接相關服務"],
    documents: ["申請表", "身分證件", "相關病歷或診斷（依要求）"],
    officialUrl: "https://www.mohw.gov.tw/",
  },
  long_term_care_assessment: {
    itemId: "long_term_care_assessment",
    location: "1966 長照專線／縣市長期照顧管理中心",
    amountLabel: "依評估結果適用服務，非固定現金",
    summary:
      "可透過 1966 詢問長照需求評估。實際服務內容由照管單位依政策與評估結果確認。",
    agency: "衛生福利部／縣市長期照顧管理中心",
    eligibilityNotes: ["有長照服務需求", "經評估符合長照服務對象"],
    steps: ["撥打 1966 或洽照管中心", "安排需求評估", "依評估結果使用服務"],
    documents: ["身分證件", "相關醫療或失能證明（依評估需要）"],
    officialUrl: "https://1966.gov.tw/",
  },
  caregiver_support_services: {
    itemId: "caregiver_support_services",
    location: "縣市家庭照顧者支持中心／長照相關窗口",
    amountLabel: "喘息與支持服務，依評估提供",
    summary:
      "家庭照顧者可詢問喘息服務與支持方案。是否適用需依照顧安排與評估結果確認。",
    agency: "衛生福利部／地方政府家庭照顧者支持單位",
    eligibilityNotes: ["實際負擔家庭照顧責任", "依各縣市方案資格"],
    steps: ["聯繫支持窗口或 1966", "說明照顧處境", "依建議申請喘息或支持服務"],
    documents: ["身分證件", "與被照顧者關係證明（如需要）"],
    officialUrl: "https://1966.gov.tw/",
  },
  caregiver_employment_support: {
    itemId: "caregiver_employment_support",
    location: "公立就業服務機構／照顧者支持相關窗口",
    amountLabel: "視方案而定（諮詢或補助）",
    summary:
      "若因照顧而減少工時或離職，可再確認就業服務或其他照顧者就業支持方向。",
    agency: "勞動部勞動力發展署／地方政府相關單位",
    eligibilityNotes: ["照顧責任影響就業", "各方案另有條件"],
    steps: ["說明工作受影響情形", "洽就服或支持窗口", "依建議參加諮詢或方案"],
    documents: ["身分證件", "工作或照顧相關證明（依方案）"],
    officialUrl: "https://www.taiwanjobs.gov.tw/",
  },
  caregiver_support_contact: {
    itemId: "caregiver_support_contact",
    location: "1966 或所在地家庭照顧者支持窗口",
    amountLabel: "諮詢專線，無固定金額",
    summary:
      "不必等所有資格確認完才求助。需要有人一起釐清時，可先聯絡支持專線。",
    agency: "衛生福利部／地方政府支持窗口",
    eligibilityNotes: ["有照顧相關求助需求即可聯繫"],
    steps: ["撥打 1966 或查詢在地窗口", "說明現況與需要的協助", "依建議接續服務"],
    documents: ["通常無需事前備齊文件"],
    officialUrl: "https://1966.gov.tw/",
  },
  taipei_green_funeral_incentive: {
    itemId: "taipei_green_funeral_incentive",
    location: "臺北市殯葬管理處相關窗口",
    amountLabel: "依市府公告鼓勵金額（示意）",
    summary: "臺北市多元環保葬鼓勵金，需符合市府公告之環保葬方式與申請資格。",
    agency: "臺北市政府殯葬管理處",
    eligibilityNotes: ["採用公告認可之環保葬方式", "符合申請人身分與時效"],
    steps: ["確認葬法符合規定", "備妥申請文件", "向市府窗口提出申請"],
    documents: ["申請表", "死亡登記相關證明", "環保葬證明（依公告）"],
    officialUrl: "https://www.funerals.taipei.gov.tw/",
  },
  taipei_joint_funeral_service: {
    itemId: "taipei_joint_funeral_service",
    location: "臺北市殯葬管理處",
    amountLabel: "聯合奠祭服務（非現金給付）",
    summary: "臺北市聯合奠祭服務可協助處理部分殯葬安排，細節以市府公告為準。",
    agency: "臺北市政府殯葬管理處",
    eligibilityNotes: ["符合聯合奠祭申請條件"],
    steps: ["洽殯葬管理處確認場次與資格", "備妥文件申請", "依通知辦理"],
    documents: ["申請表", "死亡證明或除戶證明", "其他公告所需文件"],
    officialUrl: "https://www.funerals.taipei.gov.tw/",
  },
  new_taipei_green_funeral_incentive: {
    itemId: "new_taipei_green_funeral_incentive",
    location: "新北市殯葬管理相關窗口",
    amountLabel: "依市府公告鼓勵金額（示意）",
    summary: "新北市環保葬鼓勵金，申請條件與金額以市府最新公告為準。",
    agency: "新北市政府民政局／殯葬相關單位",
    eligibilityNotes: ["採用認可之環保葬方式", "符合申請資格與時效"],
    steps: ["確認葬法與公告資格", "備妥文件", "向市府提出申請"],
    documents: ["申請表", "相關死亡與環保葬證明"],
    officialUrl: "https://www.ntpc.gov.tw/",
  },
  taoyuan_green_funeral_incentive: {
    itemId: "taoyuan_green_funeral_incentive",
    location: "桃園市殯葬管理相關窗口",
    amountLabel: "依市府公告鼓勵金額（示意）",
    summary: "桃園市環保葬鼓勵金，細節以市府公告為準。",
    agency: "桃園市政府民政局／殯葬相關單位",
    eligibilityNotes: ["採用認可之環保葬方式", "符合申請資格"],
    steps: ["確認資格與葬法", "備妥文件申請", "依通知辦理"],
    documents: ["申請表", "相關證明文件"],
    officialUrl: "https://www.tycg.gov.tw/",
  },
  penghu_green_funeral_subsidy: {
    itemId: "penghu_green_funeral_subsidy",
    location: "澎湖縣殯葬或民政相關窗口",
    amountLabel: "依縣府公告補助金額（示意）",
    summary: "澎湖縣多元環保葬補助，申請條件以縣府公告為準。",
    agency: "澎湖縣政府",
    eligibilityNotes: ["採用認可之環保葬方式", "符合縣民或公告資格"],
    steps: ["確認公告資格", "備妥文件", "向縣府窗口申請"],
    documents: ["申請表", "相關證明文件"],
    officialUrl: "https://www.penghu.gov.tw/",
  },
};

export function getItemDetail(itemId: string): ItemDetail | null {
  return ITEM_DETAILS[itemId] ?? null;
}
