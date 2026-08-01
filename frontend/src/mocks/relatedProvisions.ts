/**
 * 相關法條 fixture。
 *
 * 摘錄自 `data/benefit_discovery/extracted_candidates.v0.1.json`。
 * 皆為 HTML 抽取候選（review_status: candidate），不是已核對的全國法規條號。
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
    relatedItemIds: ["funeral_benefit"],
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
    relatedItemIds: ["funeral_benefit"],
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
    relatedItemIds: ["funeral_benefit"],
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
    relatedItemIds: ["funeral_benefit"],
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
    relatedItemIds: ["funeral_benefit", "death_registration"],
    lifeEventIds: ["spouse_death", "parent_death", "child_death"],
  },
];

/** provisionId 前綴／對應的縣市代號（與 applicant_jurisdiction 對齊）。 */
const PROVISION_JURISDICTION: Record<string, string> = {
  taipei_green_funeral_incentive: "TPE",
  taipei_joint_funeral_service: "TPE",
  new_taipei_green_funeral_incentive: "NWT",
  taoyuan_green_funeral_incentive: "TAO",
  penghu_green_funeral_subsidy: "PEN",
};

/** 依生活事件與所在地篩選相關法條。 */
export function getProvisionsForLifeEvent(
  lifeEventId: string | null,
  jurisdiction?: string | null,
): RelatedProvision[] {
  const byEvent = !lifeEventId
    ? RELATED_PROVISIONS
    : RELATED_PROVISIONS.filter((item) => item.lifeEventIds.includes(lifeEventId));
  const base = byEvent.length > 0 ? byEvent : RELATED_PROVISIONS;
  if (!jurisdiction || jurisdiction === "unsure" || jurisdiction === "OTHER_TW") {
    return base;
  }
  // 全國條文一律保留；地方條文只留與所在地相符者。
  return base.filter((item) => {
    const code = PROVISION_JURISDICTION[item.provisionId];
    return code === undefined || code === jurisdiction;
  });
}
