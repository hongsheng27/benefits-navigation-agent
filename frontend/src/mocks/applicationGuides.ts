/**
 * 申請解說 fixture。
 *
 * 步驟內容整理自 discovery candidates 與諮詢結果常見項目
 * （死亡登記、喪葬相關補助）。僅供說明示範，不代為送件。
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
};

/** 取得申請解說；未知事件時回傳配偶過世示範指南。 */
export function getApplicationGuide(
  lifeEventId: string | null,
): ApplicationGuide {
  if (lifeEventId && GUIDES_BY_EVENT[lifeEventId]) {
    return GUIDES_BY_EVENT[lifeEventId];
  }
  return SPOUSE_DEATH_GUIDE;
}
