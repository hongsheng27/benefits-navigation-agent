/**
 * 申請解說 fixture。
 *
 * 依生活事件提供示範步驟；未知事件回 null，禁止退回喪葬指南。
 * 僅供說明示範，不代為送件、不做資格判定。
 */

import type { ApplicationGuide } from "../types/postConsult";

const SPOUSE_DEATH_GUIDE: ApplicationGuide = {
  guideId: "guide_spouse_death_v1",
  lifeEventId: "spouse_death",
  title: "配偶過世後常見申請與辦理順序",
  overview:
    "多數家庭會先完成死亡登記與必要證明，再依情況辦理喪葬相關補助、環保葬鼓勵金或聯合奠祭，最後才處理勞保／健保等後續項目。以下是示範用的整理，實際仍以各機關當下規定為準。",
  disclaimer:
    "接住不代為送件，也不保證核定結果。下列步驟與文件來自官方網頁摘錄（候選資料），送件前請再向受理機關確認。",
  steps: [
    {
      stepId: "death_registration",
      title: "辦理死亡登記",
      description:
        "向戶政事務所完成死亡登記，取得後續申請常需要的戶籍相關證明。這通常是多數補助與手續的前置步驟。",
      requiredDocuments: [
        "死亡證明書或相驗屍體證明書",
        "申請人身分證明",
        "與亡者關係證明（如戶口名簿）",
      ],
      agencyName: "戶政事務所",
      deadlineNote: "請儘速辦理；後續許多申請會需要已完成登記的證明。",
      tips: [
        "先確認死亡證明正本份數是否夠後續多處使用或可申請影本／謄本。",
        "若同時要辦聯合奠祭，留意其十日內登記的期限。",
      ],
    },
    {
      stepId: "gather_funeral_docs",
      title: "整理喪葬／環保葬相關文件",
      description:
        "若考慮環保葬鼓勵金或聯合奠祭，先把遷出證明、完成環保葬證明、資格證明等準備齊，才比較不會白跑一趟。",
      requiredDocuments: [
        "骨（灰）骸存放設施寄存遷出證明（環保葬鼓勵金常見）",
        "環保葬完成證明（若已完成）",
        "申請人金融機構帳戶影本與領據（現金鼓勵金常見）",
        "聯合奠祭資格證明（若適用）",
      ],
      agencyName: null,
      deadlineNote:
        "臺北市環保葬鼓勵金常見時限：領回後 2 個月內完成環保葬，完成後 1 個月內申請；新北則多為遷出／起掘後 1 年內完成、完成後 1 個月內臨櫃。",
      tips: [
        "不同縣市金額與窗口不同，先確認亡者／骨灰來源落在哪個行政區。",
        "桃園市另有受理期間（例如 115 年預算年度），過期或預算用完可能無法申請。",
      ],
    },
    {
      stepId: "apply_local_funeral_support",
      title: "向地方殯葬窗口申請鼓勵金或聯合奠祭",
      description:
        "依你的所在地與資格，臨櫃或依公告方式提出環保葬鼓勵金、聯合奠祭等申請。窗口常見為殯葬管理處、殯儀館服務中心或區公所。",
      requiredDocuments: [
        "身分證明文件",
        "完成證明／遷出證明（鼓勵金）",
        "死亡證明、親屬關係證明、亡者照片與資格證明（聯合奠祭）",
      ],
      agencyName: "地方殯葬管理機關（依縣市而定）",
      deadlineNote: "聯合奠祭常見：自死亡日或遺體具領日起十日內登記最近場次。",
      tips: [
        "新北申請人及亡者不限新北市民，但遷出／起掘來源與金額級距要對照計畫。",
        "未帶齊資格證明時，聯合奠祭可能改為部分項目減半收費，而不是完全免費。",
      ],
    },
    {
      stepId: "labor_funeral_benefit",
      title: "確認勞保喪葬給付等中央項目",
      description:
        "若亡者有勞工保險等投保身分，可能另有喪葬給付或遺屬相關給付。這與地方政府環保葬鼓勵金是不同管道，條件與文件也不相同。",
      requiredDocuments: [
        "死亡證明文件",
        "投保／身分相關資料",
        "申請人身分與關係證明",
      ],
      agencyName: "勞動部勞工保險局（若涉及勞保）",
      deadlineNote: "各給付請領時效不同，請以勞保局當下公告為準。",
      tips: [
        "諮詢結果若仍顯示「需要更多資料」或「需人工協助」，代表條件還不足以自動判定。",
        "不要把地方鼓勵金的文件清單直接套用到勞保給付。",
      ],
    },
  ],
};

const JOB_LOSS_GUIDE: ApplicationGuide = {
  guideId: "guide_job_loss_v1",
  lifeEventId: "job_loss",
  title: "失業／被資遣後常見申請與辦理順序",
  overview:
    "多數情況會先確認是否屬於非自願離職，再到公立就業服務機構辦理求職登記，接著依就業保險規定確認失業給付，並視需要使用就業諮詢或職業訓練。以下是示範用整理，實際以各機關當下規定為準。",
  disclaimer:
    "接住不代為送件，也不保證核定結果。下列步驟為示範候選說明，送件前請再向就業服務機構或勞保局確認。",
  steps: [
    {
      stepId: "confirm_involuntary_separation",
      title: "確認離職原因與證明文件",
      description:
        "先整理資遣通知、離職證明或相關文件，確認是否可能符合非自願離職等請領前提。這裡只協助準備，不代替機關認定。",
      requiredDocuments: [
        "離職證明或資遣相關文件",
        "身分證明",
        "投保／薪資相關資料（若已持有）",
      ],
      agencyName: null,
      deadlineNote: "請領時效依就業保險規定，請以勞保局公告為準。",
      tips: [
        "若不清楚離職類型，可先向原投保單位或就業服務站詢問如何開立證明。",
        "不要把「有沒有工作意願」等條件自行解讀成最終資格。",
      ],
    },
    {
      stepId: "register_at_employment_service",
      title: "向公立就業服務機構辦理求職登記",
      description:
        "多數失業給付流程會要求先到公立就業服務機構完成求職登記，並配合就業諮詢或推介就業／職訓安排。",
      requiredDocuments: [
        "身分證明",
        "離職相關證明",
        "印章或依現場要求之文件",
      ],
      agencyName: "公立就業服務機構（就業服務站）",
      deadlineNote: "請儘早辦理，以免影響後續請領時程。",
      tips: [
        "可同時詢問職業訓練與就業促進措施。",
        "各地站所預約／臨櫃方式可能不同，建議先電話或官網確認。",
      ],
    },
    {
      stepId: "apply_unemployment_benefit",
      title: "依就業保險確認失業給付請領",
      description:
        "完成求職登記等前置步驟後，再依就業保險規定向勞保局或指定管道確認失業給付請領方式與應備文件。",
      requiredDocuments: [
        "求職登記／就業服務相關證明",
        "身分與帳戶資料",
        "其他勞保局公告之請領文件",
      ],
      agencyName: "勞動部勞工保險局",
      deadlineNote: "等待期、給付期間與續領規定以勞保局最新說明為準。",
      tips: [
        "諮詢結果若仍顯示需再確認，代表條件尚不足以自動判定。",
        "地方就業服務與中央給付窗口不同，文件不要混用清單。",
      ],
    },
  ],
};

const OCCUPATIONAL_INJURY_GUIDE: ApplicationGuide = {
  guideId: "guide_occupational_injury_v1",
  lifeEventId: "occupational_injury",
  title: "職災與照顧安排常見辦理順序",
  overview:
    "若家人因工作事故失能並需要照顧，常見會先追蹤職災認定與職災保險相關給付，再依需要辦理身心障礙鑑定、長照需求評估，並為照顧者尋求支持或就業協助。以下是示範用整理，實際以各機關當下規定為準。",
  disclaimer:
    "接住不代為送件，也不保證核定結果。下列步驟為示範候選說明，不做資格判定；送件前請再向勞保局、公所、1966 或家庭照顧者支持窗口確認。",
  steps: [
    {
      stepId: "track_occupational_recognition",
      title: "追蹤職業災害認定進度",
      description:
        "若職災認定還在申請中，先向受理窗口確認案件進度與是否需補件。認定結果常會影響後續職災保險給付方向。",
      requiredDocuments: [
        "申請案件編號或受理證明（若已有）",
        "診斷相關資料（依窗口要求）",
      ],
      agencyName: "勞動部勞工保險局／相關受理單位",
      deadlineNote: "補件期限以案件通知為準。",
      tips: [
        "不必在 app 內提供公司細節或事故細節。",
        "認定結果未出前，仍可先整理後續可能需要的證明。",
      ],
    },
    {
      stepId: "check_occupational_benefits",
      title: "確認職災保險相關給付方向",
      description:
        "在有職災保險或認定進度的前提下，再向勞保局確認傷病、失能等給付的說明與應備文件。是否符合仍由承辦機關判斷。",
      requiredDocuments: [
        "職災認定相關文件（若已取得）",
        "診斷／失能相關證明（依公告）",
        "申請人身分與帳戶資料",
      ],
      agencyName: "勞動部勞工保險局",
      deadlineNote: "各給付請領時效不同，請以勞保局公告為準。",
      tips: [
        "職災給付與一般勞保項目可能是不同管道，文件清單不要互套。",
      ],
    },
    {
      stepId: "disability_and_long_term_care",
      title: "視需要辦理身障鑑定與長照評估",
      description:
        "若照顧需求持續，可向戶籍地公所了解身心障礙鑑定，並撥打 1966 詢問長照需求評估與服務方向。",
      requiredDocuments: [
        "身分與戶籍相關證明",
        "醫療院所／公所要求之申請表件",
      ],
      agencyName: "戶籍地公所／指定醫療機構／1966 長照專線",
      deadlineNote: null,
      tips: [
        "長照服務是否適用，須經照管單位評估。",
        "鑑定與長照可與職災流程並行了解，但窗口各自獨立。",
      ],
    },
    {
      stepId: "caregiver_support",
      title: "為照顧者尋求支持與就業協助",
      description:
        "照顧者可洽詢喘息服務、家庭照顧者支持據點，或就業服務相關資源；需要有人一起釐清時，也可先打 1966 或地方支持窗口。",
      requiredDocuments: ["依各窗口公告之申請資料"],
      agencyName: "家庭照顧者支持據點／就業服務機構／1966",
      deadlineNote: null,
      tips: [
        "不必等所有資格確認完才求助。",
        "就業支持與喘息服務的受理單位可能不同，可分開詢問。",
      ],
    },
  ],
};

const GUIDES_BY_EVENT: Record<string, ApplicationGuide> = {
  spouse_death: SPOUSE_DEATH_GUIDE,
  parent_death: {
    ...SPOUSE_DEATH_GUIDE,
    guideId: "guide_parent_death_v1",
    lifeEventId: "parent_death",
    title: "親人過世後常見申請與辦理順序",
  },
  child_death: {
    ...SPOUSE_DEATH_GUIDE,
    guideId: "guide_child_death_v1",
    lifeEventId: "child_death",
    title: "親人過世後常見申請與辦理順序",
  },
  job_loss: JOB_LOSS_GUIDE,
  occupational_injury: OCCUPATIONAL_INJURY_GUIDE,
};

/**
 * 取得申請解說。
 *
 * 未知事件回 `null`，禁止退回喪葬指南。
 * 若傳入多個 lifeEventIds，回傳第一個有指南的事件。
 */
export function getApplicationGuide(
  lifeEventId: string | null,
  lifeEventIds: string[] = [],
): ApplicationGuide | null {
  if (lifeEventId && GUIDES_BY_EVENT[lifeEventId]) {
    return GUIDES_BY_EVENT[lifeEventId];
  }
  for (const eventId of lifeEventIds) {
    if (GUIDES_BY_EVENT[eventId]) {
      return GUIDES_BY_EVENT[eventId];
    }
  }
  return null;
}
