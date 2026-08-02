/**
 * 相關法條 fixture。
 *
 * 喪葬摘錄自 `data/benefit_discovery/extracted_candidates.v0.1.json`；
 * 失業／職災等為示範用候選說明（review_status: candidate），不是已核對的全國法規條號。
 *
 * 篩選契約：依當次結果 itemId 與生活事件命中；無命中回空陣列，禁止跨事件 fallback。
 */

import type { RelatedProvision } from "../types/postConsult";

export const RELATED_PROVISIONS: RelatedProvision[] = [
  {
    provisionId: "taipei_green_funeral_incentive",
    title: "臺北市多元環保葬鼓勵金",
    lawName: "臺北市多元環保葬鼓勵金申請說明",
    articleLabel: "申請期限與文件",
    publisherName: "臺北市殯葬管理處",
    sourceUrl: "https://memories.mso.gov.taipei/eco-burial/new-reward.php",
    excerpt:
      "申請人（即骨（灰）骸存放設施寄存遷出證明所示之原申請人）自富德靈骨樓、陽明山靈骨塔或臻愛樓領回骨灰（骸），於領回之次日起2個月內完成多元環保葬，並於完成之次日起1個月內，檢附下列文件親自或委託他人至臺北市懷愛館服務中心、陽明山臻善園辦或富德靈骨樓辦公室申請多元環保葬鼓勵金",
    plainLanguageSummary:
      "如果你是從臺北市指定靈骨塔領回骨灰或骨骸的原申請人，先在領回後兩個月內完成環保葬，再在完成後一個月內，帶齊完成證明、遷出證明、身分證明和帳戶資料，到懷愛館等指定窗口申請鼓勵金（常見為 1 萬或 2 萬元）。",
    reviewStatus: "candidate",
    relatedItemIds: ["funeral_benefit", "taipei_green_funeral_incentive"],
    lifeEventIds: ["spouse_death", "parent_death", "child_death"],
  },
  {
    provisionId: "new_taipei_green_funeral_incentive",
    title: "新北市環保葬鼓勵金",
    lawName: "新北市環保葬鼓勵金發放計畫",
    articleLabel: "三、申請條件；四、鼓勵金額度",
    publisherName: "新北市政府殯葬管理處",
    sourceUrl: "https://www.mso.ntpc.gov.tw/home.jsp?id=ffb7a5546a4ef474",
    excerpt:
      "本市自113年11月1日起實施新北市環保葬鼓勵金發放計畫\n三、申請條件：\n(一)自本市公立納骨塔遷出或自本市公墓起掘骨灰（骸）次日起1年內完成環保葬。\n(二)完成環保葬次日起1個月內，向本市殯儀館服務中心臨櫃申辦。\n(三)申請人及亡者不限新北市民。\n(四)環保葬地點不限於本市。\n四、鼓勵金額度：\n(一)自本市公立納骨塔遷出骨骸改環保葬者，發給鼓勵金新臺幣(以下同)2萬元；遷出骨灰改環保葬者，發給鼓勵金1萬元。\n(二)自本市公立公墓起掘改環保葬者：1萬元。\n(三)本市非述範圍起掘骨灰(骸)改環保葬者，發給鼓勵金7,000元。",
    plainLanguageSummary:
      "新北市從 113/11/1 起有環保葬鼓勵金。重點是：從新北公立納骨塔遷出或公墓起掘後一年內完成環保葬，完成後一個月內到殯儀館服務中心臨櫃申請。金額依骨骸／骨灰與來源不同，約 7,000 到 2 萬元；申請人與亡者不一定要是新北市民，葬在哪裡也不限新北。",
    reviewStatus: "candidate",
    relatedItemIds: ["funeral_benefit", "new_taipei_green_funeral_incentive"],
    lifeEventIds: ["spouse_death", "parent_death", "child_death"],
  },
  {
    provisionId: "taoyuan_green_funeral_incentive",
    title: "桃園市環保葬鼓勵金",
    lawName: "桃園市環保葬鼓勵金發放計畫",
    articleLabel: "金額與受理期間",
    publisherName: "桃園市政府民政局禮儀事務科",
    sourceUrl: "https://cab.tycg.gov.tw/News_Content.aspx?n=7802&s=1601908",
    excerpt:
      "自本市公立骨灰(骸)存放設施遷出存放之骨骸改環保葬者，發放鼓勵金2萬元。\n自本市公立骨灰(骸)存放設施遷出存放之骨灰改環保葬者，發放鼓勵金1萬元。\n受理鼓勵金申請期間：115年1月1日起至115年10月31日(或預算用罄)止。\n詳如附件\n發布單位：禮儀事務科\n聯絡人：桃園及中壢區請洽殯葬管理所辦理;其他區請洽各區公所辦理",
    plainLanguageSummary:
      "桃園市針對從本市公立骨灰（骸）設施遷出改環保葬者發鼓勵金：骨骸 2 萬、骨灰 1 萬。受理期間是 115/1/1 到 115/10/31（或預算用完）。桃園、中壢區找殯葬管理所，其他區找各區公所；更細的條件多半在附件計畫裡。",
    reviewStatus: "candidate",
    relatedItemIds: ["funeral_benefit", "taoyuan_green_funeral_incentive"],
    lifeEventIds: ["spouse_death", "parent_death", "child_death"],
  },
  {
    provisionId: "penghu_green_funeral_subsidy",
    title: "澎湖縣多元環保葬補助",
    lawName: "澎湖縣多元環保葬補助實施要點",
    articleLabel: null,
    publisherName: "澎湖縣政府民政處殯葬管理科",
    sourceUrl:
      "https://www.penghu.gov.tw/civil/home.jsp?id=461&act=view&dataserno=201908060001",
    excerpt:
      "多元環保葬補助實施要點\n發布日期：2019-08-06\n發布單位：殯葬管理科\n類別：殯葬管理\n內容：\n1.申請表\n2.多元環保葬補助實施要點\n3.領據\n\n補充（我的E政府入口頁）：另可申請多元環保葬補助，獎勵金為1萬元或2萬元。馬公市（樹葬、花葬）：收費標準請洽詢馬公市公所民政課，電話(06)9272173分機103或154。",
    plainLanguageSummary:
      "澎湖縣有多元環保葬補助實施要點，網頁上可見申請表、要點與領據下載；獎勵金常見為 1 萬或 2 萬元。馬公市樹葬、花葬細節可洽馬公市公所民政課。詳細資格與應備文件仍建議對照 PDF 附件或致電確認。",
    reviewStatus: "candidate",
    relatedItemIds: ["funeral_benefit", "penghu_green_funeral_subsidy"],
    lifeEventIds: ["spouse_death", "parent_death", "child_death"],
  },
  {
    provisionId: "taipei_joint_funeral_service",
    title: "臺北市聯合奠祭家屬須知",
    lawName: "臺北市聯合奠祭",
    articleLabel: "申請資格、應備證件、免費服務項目",
    publisherName: "臺北市殯葬管理處懷愛館服務中心",
    sourceUrl: "https://mso.gov.taipei/cp.aspx?n=485C4E58C9A2DD7B",
    excerpt:
      "參加聯合奠祭家屬須知：\n一、申請資格：\n亡者為低收入戶檢具相關證明文件者。\n亡者為中低收入戶檢具相關證明文件者。\n亡者為器官捐贈檢具相關證明文件件者。\n亡者為原住民檢具相關證明文件者。\n…（共10類）\n二、應備證件：\n死亡證明書正本1份或相驗屍體證明書正本。\n親屬關係證明文件或其他文件、亡者2吋照片2張。\n申請資格證明文件。\n三、市府辦理聯合奠祭免費服務項目共23項",
    plainLanguageSummary:
      "臺北市聯合奠祭是給符合特定資格亡者家屬的免費殯葬服務（約 23 項）。常見資格包括低收入戶、中低收入戶、器官捐贈、原住民等共約 10 類。要帶死亡證明、親屬關係證明、亡者照片與資格證明，到懷愛館服務中心辦理，並注意十日內登記、不能任意選場次等期限。",
    reviewStatus: "candidate",
    relatedItemIds: [
      "funeral_benefit",
      "death_registration",
      "taipei_joint_funeral_service",
    ],
    lifeEventIds: ["spouse_death", "parent_death", "child_death"],
  },
  {
    provisionId: "labor_funeral_and_survivor_overview",
    title: "勞工保險喪葬給付與遺屬給付（說明摘錄）",
    lawName: "勞工保險條例相關給付說明（示範摘錄）",
    articleLabel: "喪葬／遺屬給付請領提醒",
    publisherName: "勞動部勞工保險局",
    sourceUrl: "https://www.bli.gov.tw/",
    excerpt:
      "（示範候選摘錄）被保險人死亡時，其遺屬得依勞工保險規定請領喪葬給付或遺屬年金等給付。請領時效、應備文件與請領人順序以勞保局當下公告為準；本摘錄僅供流程說明，不構成資格認定。",
    plainLanguageSummary:
      "若亡者有勞工保險，家屬可能另有喪葬給付或遺屬相關給付可確認。這與地方政府環保葬鼓勵金是不同管道；文件、時效與窗口都以勞保局最新說明為準。",
    reviewStatus: "candidate",
    relatedItemIds: ["funeral_benefit", "survivor_pension", "death_registration"],
    lifeEventIds: ["spouse_death", "parent_death", "child_death"],
  },
  {
    provisionId: "employment_insurance_unemployment_benefit",
    title: "就業保險失業給付申請說明",
    lawName: "就業保險法／失業給付請領須知（示範摘錄）",
    articleLabel: "請領條件與辦理提醒",
    publisherName: "勞動部勞工保險局",
    sourceUrl: "https://www.bli.gov.tw/",
    excerpt:
      "（示範候選摘錄）被保險人非自願離職、具工作能力及繼續工作意願，向公立就業服務機構辦理求職登記、接受就業諮詢與推介就業或安排職業訓練後，得依就業保險規定請領失業給付。實際條件、等待期與給付期間以勞保局／就業服務機構最新公告為準。",
    plainLanguageSummary:
      "失業給付多半要先確認是否屬於非自願離職，再到公立就業服務機構辦理求職登記與後續諮詢。是否核定由承辦機關依就業保險規定判斷；接住只協助整理可能要走的步驟。",
    reviewStatus: "candidate",
    relatedItemIds: ["unemployment_benefit"],
    lifeEventIds: ["job_loss"],
  },
  {
    provisionId: "public_employment_service_overview",
    title: "公立就業服務與職業訓練諮詢",
    lawName: "就業服務相關說明（示範摘錄）",
    articleLabel: null,
    publisherName: "勞動部／各地公立就業服務機構",
    sourceUrl: "https://www.wda.gov.tw/",
    excerpt:
      "（示範候選摘錄）公立就業服務機構可提供求職登記、就業諮詢、職業訓練資訊與相關就業促進措施說明。非自願離職者辦理失業給付時，通常需先完成求職登記並配合後續就業服務安排。",
    plainLanguageSummary:
      "除了失業給付，也可先到就業服務站了解求職登記、職訓與就業諮詢。窗口與服務內容因地而異，建議直接洽詢所在地公立就業服務機構。",
    reviewStatus: "candidate",
    relatedItemIds: ["employment_service", "unemployment_benefit"],
    lifeEventIds: ["job_loss"],
  },
  {
    provisionId: "occupational_accident_recognition_overview",
    title: "職業災害認定與職災保險說明",
    lawName: "勞工職業災害保險及保護法相關說明（示範摘錄）",
    articleLabel: "認定申請與後續給付提醒",
    publisherName: "勞動部勞工保險局／勞動檢查單位",
    sourceUrl: "https://www.bli.gov.tw/",
    excerpt:
      "（示範候選摘錄）發生職業災害時，得依規定申請職業災害認定，並依職災保險請領傷病、失能等給付。申請進度、應備診斷證明與受理窗口以勞保局或相關單位當下說明為準；本摘錄不做個案資格判斷。",
    plainLanguageSummary:
      "職災認定常是後續失能給付等項目的前置。若認定還在處理中，可先向受理窗口確認進度與補件需求；是否符合給付仍由承辦機關認定。",
    reviewStatus: "candidate",
    relatedItemIds: [
      "occupational_injury_recognition",
      "occupational_injury_recognition_follow_up",
      "occupational_accident_disability_benefit",
      "occupational_disability_benefit",
    ],
    lifeEventIds: ["occupational_injury"],
  },
  {
    provisionId: "disability_assessment_overview",
    title: "身心障礙鑑定辦理說明",
    lawName: "身心障礙者權益保障相關鑑定流程（示範摘錄）",
    articleLabel: null,
    publisherName: "衛生福利部／地方政府社會局（處）",
    sourceUrl: "https://www.mohw.gov.tw/",
    excerpt:
      "（示範候選摘錄）申請身心障礙鑑定，通常需向戶籍地公所提出申請，並至指定醫療機構辦理鑑定。鑑定結果與證明核發時程依各地與醫療院所公告為準。",
    plainLanguageSummary:
      "若結果建議辦理身心障礙鑑定，可先向戶籍地公所或指定醫療院所確認申請方式與應備資料。接住不收證件、也不代為送件。",
    reviewStatus: "candidate",
    relatedItemIds: ["disability_assessment"],
    lifeEventIds: ["occupational_injury", "long_term_care_need"],
  },
  {
    provisionId: "long_term_care_1966_overview",
    title: "長期照顧服務（1966）諮詢說明",
    lawName: "長期照顧十年第2期計畫相關服務說明（示範摘錄）",
    articleLabel: "長照需求評估",
    publisherName: "衛生福利部／1966 長照服務專線",
    sourceUrl: "https://1966.gov.tw/",
    excerpt:
      "（示範候選摘錄）民眾可撥打 1966 長照服務專線洽詢長期照顧服務與需求評估。實際適用服務項目與補助，須經照管中心評估後依最新政策辦理。",
    plainLanguageSummary:
      "需要長期照顧時，可先打 1966 詢問評估與服務方向。是否適用特定服務，仍由照管單位依評估結果確認。",
    reviewStatus: "candidate",
    relatedItemIds: ["long_term_care_assessment"],
    lifeEventIds: ["occupational_injury", "long_term_care_need"],
  },
  {
    provisionId: "caregiver_support_overview",
    title: "家庭照顧者支持與喘息服務說明",
    lawName: "家庭照顧者支持服務相關說明（示範摘錄）",
    articleLabel: null,
    publisherName: "衛生福利部／地方政府家庭照顧者支持據點",
    sourceUrl: "https://1966.gov.tw/",
    excerpt:
      "（示範候選摘錄）家庭照顧者可洽詢喘息服務、支持團體、心理支持與相關諮詢資源。服務內容與申請方式依地方政府與據點公告為準；就業相關支持可另洽就業服務單位。",
    plainLanguageSummary:
      "若你正在負擔照顧工作，可先了解喘息服務與家庭照顧者支持窗口；若因照顧影響工作，也可一併詢問就業支持。是否適用仍需由服務單位評估。",
    reviewStatus: "candidate",
    relatedItemIds: [
      "caregiver_support_services",
      "caregiver_employment_support",
      "caregiver_support_contact",
    ],
    lifeEventIds: ["occupational_injury", "long_term_care_need"],
  },
];

/** provisionId 對應的縣市代號（與 applicant_jurisdiction 對齊）；未列者視為全國適用。 */
const PROVISION_JURISDICTION: Record<string, string> = {
  taipei_green_funeral_incentive: "TPE",
  taipei_joint_funeral_service: "TPE",
  new_taipei_green_funeral_incentive: "NWT",
  taoyuan_green_funeral_incentive: "TAO",
  penghu_green_funeral_subsidy: "PEN",
};

export type ProvisionsQuery = {
  lifeEventIds?: string[];
  itemIds?: string[];
  jurisdiction?: string | null;
};

function overlaps(left: string[], right: Set<string>): boolean {
  return left.some((id) => right.has(id));
}

/**
 * 依當次結果項目與生活事件篩選相關法條。
 *
 * - 有 itemIds：必須與 `relatedItemIds` 有交集。
 * - 有 lifeEventIds：必須與 `lifeEventIds` 有交集。
 * - 兩者都沒有：回空（不回傳全部喪葬資料）。
 * - 無命中：回空，禁止跨事件 fallback。
 */
export function getProvisionsForContext(
  query: ProvisionsQuery,
): RelatedProvision[] {
  const lifeEventIds = (query.lifeEventIds ?? []).filter(Boolean);
  const itemIds = (query.itemIds ?? []).filter(Boolean);
  const lifeEventSet = new Set(lifeEventIds);
  const itemSet = new Set(itemIds);

  if (lifeEventSet.size === 0 && itemSet.size === 0) {
    return [];
  }

  let matched = RELATED_PROVISIONS.filter((item) => {
    const eventOk =
      lifeEventSet.size === 0 || overlaps(item.lifeEventIds, lifeEventSet);
    const itemOk =
      itemSet.size === 0 || overlaps(item.relatedItemIds, itemSet);
    return eventOk && itemOk;
  });

  const jurisdiction = query.jurisdiction;
  if (
    jurisdiction &&
    jurisdiction !== "unsure" &&
    jurisdiction !== "OTHER_TW"
  ) {
    matched = matched.filter((item) => {
      const code = PROVISION_JURISDICTION[item.provisionId];
      return code === undefined || code === jurisdiction;
    });
  }

  return matched;
}

/** @deprecated 請改用 `getProvisionsForContext`；保留給舊呼叫端。 */
export function getProvisionsForLifeEvent(
  lifeEventId: string | null,
  jurisdiction?: string | null,
): RelatedProvision[] {
  return getProvisionsForContext({
    lifeEventIds: lifeEventId ? [lifeEventId] : [],
    jurisdiction,
  });
}
