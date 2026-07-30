import type { ApplyGuide, BenefitItem } from "../types/navigator";

export const BENEFIT_ITEMS: BenefitItem[] = [
  {
    id: "funeral",
    name: "喪葬給付",
    org: "勞動部勞工保險局",
    deadline: "有請領時效",
    basis: "〈條例名稱〉第 〇 條",
    location: "勞動部勞工保險局（可線上辦理）",
    amountLabel: "依投保薪資計算",
    requires: ["insured_type", "relation"],
    reason: "過世者生前有投保，且你為適格請領人。",
    plainExplanation:
      "因為過世者生前有勞工保險，而你是配偶，所以可以申請這筆給付。請留意有請領時效，建議先辦死亡登記取得文件後儘早提出。",
    documents: [
      { name: "喪葬給付申請書", sourceType: "auto", needs: ["relation"], note: "請領人與親屬關係由你的資料帶入" },
      { name: "死亡證明書或除戶戶籍謄本", sourceType: "mydata", needs: [], note: "MyData 戶政除戶資料" },
      { name: "請領人與過世者關係證明", sourceType: "mydata", needs: [], note: "MyData 全戶戶籍資料可佐證" },
      { name: "投保單位與投保資料", sourceType: "auto", needs: ["insured_type"], note: "依你填的投保身分帶入受理機關" },
      { name: "喪葬費用收據", sourceType: "self", needs: [], note: "需由禮儀公司開立，系統無法取得" },
      { name: "請領人金融帳戶封面影本", sourceType: "self", needs: [], note: "請自行準備存摺影本" },
    ],
  },
  {
    id: "survivor",
    name: "遺屬年金",
    org: "勞動部勞工保險局",
    deadline: "有請領時效",
    basis: "〈條例名稱〉第 〇 條",
    location: "勞動部勞工保險局",
    amountLabel: "依年資與投保薪資計算",
    requires: ["insured_type", "insured_years", "relation"],
    reason: "須確認投保年資是否達到門檻。",
    plainExplanation:
      "遺屬年金需要確認過世者的投保年資是否達到門檻。年資確認後即可判定，也會影響是否有未成年子女加給。",
    documents: [
      { name: "遺屬年金申請書", sourceType: "auto", needs: ["relation"], note: "請領人資料與親屬關係已可預填" },
      { name: "過世者投保年資資料", sourceType: "mydata", needs: [], note: "MyData 勞保局被保險人投保資料" },
      { name: "全戶戶籍謄本", sourceType: "mydata", needs: [], note: "MyData 內政部戶政資料" },
      { name: "未成年子女加給申報", sourceType: "auto", needs: ["children"], note: "依你填的子女數自動帶入" },
      { name: "在學證明（子女加給）", sourceType: "self", needs: [], note: "需向學校申請" },
      { name: "金融帳戶封面影本", sourceType: "self", needs: [], note: "請自行準備存摺影本" },
    ],
  },
  {
    id: "special",
    name: "特殊境遇家庭扶助",
    org: "地方社會局處",
    deadline: null,
    basis: "〈條例名稱〉第 〇 條",
    location: "戶籍地公所社會課",
    amountLabel: "依縣市與子女數核算",
    requires: ["relation", "children", "employment"],
    reason: "喪偶且獨力扶養未成年子女，符合特殊境遇認定方向。",
    plainExplanation:
      "你符合喪偶且獨力扶養未成年子女的條件方向，還須經家庭收入審查。收入資料可由 MyData 帶入後即時試算。",
    documents: [
      { name: "扶助申請書", sourceType: "auto", needs: ["relation", "children"], note: "家庭組成由你的資料帶入" },
      { name: "全戶戶籍謄本", sourceType: "mydata", needs: [], note: "MyData 內政部戶政資料" },
      { name: "全戶所得清單", sourceType: "mydata", needs: [], note: "MyData 財政部所得資料" },
      { name: "全戶財產歸屬清單", sourceType: "mydata", needs: [], note: "MyData 財政部財產資料" },
      { name: "就業狀況說明", sourceType: "auto", needs: ["employment"], note: "依你填的就業狀況帶入" },
      { name: "子女在學證明", sourceType: "self", needs: [], note: "需向學校申請" },
      { name: "存款餘額證明", sourceType: "self", needs: [], note: "需向往來銀行申請" },
    ],
  },
  {
    id: "unemploy",
    name: "失業給付（就業保險）",
    org: "勞動部勞工保險局",
    deadline: "退保後 2 年內",
    basis: "〈條例名稱〉第 〇 條",
    location: "公立就業服務機構辦理求職登記後轉送",
    amountLabel: "投保薪資 60%，最長 6 個月",
    requires: ["employment"],
    reason: "須為非自願離職且就保年資符合。",
    plainExplanation:
      "你目前為非自願離職，方向上符合請領條件，但須確認就保年資與求職登記程序。",
    documents: [
      { name: "失業給付申請書", sourceType: "auto", needs: ["employment"], note: "離職狀況由你的資料帶入" },
      { name: "離職證明書（載明非自願）", sourceType: "self", needs: [], note: "需向原雇主索取，最關鍵文件" },
      { name: "本人勞保投保資料", sourceType: "mydata", needs: [], note: "MyData 勞保局投保資料" },
      { name: "國民身分證影本", sourceType: "mydata", needs: [], note: "MyData 戶政身分證影像" },
      { name: "扶養眷屬證明（加給）", sourceType: "auto", needs: ["children"], note: "依你填的子女數帶入" },
      { name: "金融帳戶封面影本", sourceType: "self", needs: [], note: "請自行準備存摺影本" },
    ],
  },
  {
    id: "relief",
    name: "急難紓困",
    org: "衛福部 · 公所社會課",
    deadline: "事件後 6 個月內",
    basis: "〈條例名稱〉第 〇 條",
    location: "戶籍地或現居地公所社會課",
    amountLabel: "一次性核發",
    requires: ["employment", "household"],
    reason: "主要收入者過世且收入中斷，屬急難救助範圍。",
    plainExplanation:
      "家庭主要收入者過世並導致收入中斷，屬急難救助受理範圍，訪視後從速核發。",
    documents: [
      { name: "急難救助申請書", sourceType: "auto", needs: ["household"], note: "家戶組成由你的資料帶入" },
      { name: "國民身分證影本", sourceType: "mydata", needs: [], note: "MyData 戶政身分證影像" },
      { name: "致生急難事由證明", sourceType: "self", needs: [], note: "需向醫院或原雇主取得" },
      { name: "近三個月存摺明細", sourceType: "self", needs: [], note: "請自行至銀行補摺" },
      { name: "全戶戶籍資料", sourceType: "mydata", needs: [], note: "MyData 內政部戶政資料" },
    ],
  },
];

export const APPLY_GUIDES: Record<string, ApplyGuide> = {
  funeral: {
    fullDescription:
      "被保險人死亡時，由支出殯葬費的遺屬請領的一次性給付。給付金額依過世者死亡當月起前 6 個月的平均月投保薪資計算，發給一定月數。若同一被保險人的遺屬有多人，應共同具領；未共同具領時，由順序在先者具領。",
    authority: "勞動部勞工保險局",
    level: "中央機關",
    area: "全國適用（不分縣市）",
    onlineNote: "可線上辦理（勞保局 e 化服務系統）",
    steps: [
      { title: "先辦理死亡登記", detail: "向戶籍地戶政事務所辦理，取得除戶證明。這是後續所有申請的前置文件。", isPrerequisite: true },
      { title: "確認過世者的投保身分與投保單位", detail: "不同保險別由不同機關受理。可透過 MyData 調閱投保資料確認。" },
      { title: "備齊申請書與證明文件", detail: "申請書可於勞保局網站下載，或使用本站的預填版本。" },
      { title: "選擇送件方式", detail: "臨櫃至勞保局各地辦事處、郵寄、或以自然人憑證線上申辦。" },
      { title: "等待審核與撥款", detail: "審核通過後匯入指定帳戶。若文件不全，勞保局會函請補正。" },
    ],
    links: [
      { label: "勞動部勞工保險局 · 喪葬給付專區", note: "給付說明與申請書下載" },
      { label: "勞保局 e 化服務系統", note: "線上申辦入口" },
      { label: "全國法規資料庫 · 勞工保險條例", note: "法規原文" },
    ],
  },
  survivor: {
    fullDescription:
      "被保險人在保險有效期間死亡，其符合條件的遺屬可按月請領的年金給付。給付金額依投保年資與平均月投保薪資計算，並設有最低保障金額。有符合條件的遺屬多人時，每多一人加發一定比例，最多加計上限。請領人須符合親屬順位與年齡、身心障礙或扶養未成年子女等條件。",
    authority: "勞動部勞工保險局",
    level: "中央機關",
    area: "全國適用（不分縣市）",
    onlineNote: "可線上辦理（需自然人憑證）",
    steps: [
      { title: "先辦理死亡登記", detail: "取得除戶證明與死亡證明書。", isPrerequisite: true },
      { title: "查明過世者的投保年資", detail: "年資直接影響是否符合門檻與給付金額，可透過 MyData 調閱勞保投保資料。" },
      { title: "確認自己是否為適格請領人", detail: "依親屬順位認定，配偶、子女、父母等各有不同條件。" },
      { title: "填具申請書並檢附關係證明", detail: "需證明與過世者的親屬關係，戶籍資料可由 MyData 取得。" },
      { title: "送件並等待核定", detail: "核定後按月撥入指定帳戶，首次核發可能追溯自請領日。" },
    ],
    links: [
      { label: "勞動部勞工保險局 · 遺屬年金專區", note: "資格條件與試算" },
      { label: "勞保局 · 給付金額試算服務", note: "線上試算" },
      { label: "全國法規資料庫 · 勞工保險條例", note: "法規原文" },
    ],
  },
  special: {
    fullDescription:
      "針對特殊境遇家庭提供的扶助措施，包含子女生活津貼、緊急生活扶助、子女教育費補助、傷病醫療補助等項目。認定條件包含喪偶、離婚、未婚生子、家暴受害、配偶失蹤或入獄等情形之一，且家庭總收入按全家人口平均分配須低於當地最低生活費一定倍數，並符合不動產與存款的財產限額。",
    authority: "衛生福利部社會及家庭署（政策）",
    level: "中央訂定 · 地方執行",
    area: "各縣市受理，實際金額與加給依地方規定",
    onlineNote: "部分縣市可線上申辦，多數需臨櫃",
    steps: [
      { title: "確認是否符合特殊境遇認定", detail: "須符合喪偶、離婚、家暴等法定情形之一。" },
      { title: "查明家庭收入與財產是否低於門檻", detail: "以全家人口平均分配計算。所得與財產資料可由 MyData 取得。" },
      { title: "向戶籍地公所社會課提出申請", detail: "各縣市受理窗口與應備文件略有差異，建議先電話確認。" },
      { title: "配合家庭訪視或資料補正", detail: "承辦人員可能進行訪視或要求補充說明。" },
      { title: "核定後按月或按次撥款", detail: "子女生活津貼通常按月核發，需定期重新審核。" },
    ],
    links: [
      { label: "衛福部社會及家庭署 · 特殊境遇家庭專區", note: "法定條件與扶助項目" },
      { label: "各縣市政府社會局處 · 申辦資訊", note: "依戶籍地查詢受理窗口" },
      { label: "全國法規資料庫 · 特殊境遇家庭扶助條例", note: "法規原文" },
    ],
  },
  unemploy: {
    fullDescription:
      "被保險人非自願離職，且辦理退保當日前 3 年內保險年資合計滿一定期間，具工作能力及繼續工作意願，向公立就業服務機構辦理求職登記後，經一定期間仍無法推介就業或安排職業訓練者，得請領失業給付。給付標準為離職退保前平均月投保薪資的一定比例，並設有給付月數上限；有扶養無工作收入之眷屬者可加給。",
    authority: "勞動部勞工保險局（核發）· 公立就業服務機構（受理）",
    level: "中央機關",
    area: "全國適用，於各地就業服務站辦理",
    onlineNote: "須先臨櫃辦理求職登記，後續認定可線上",
    steps: [
      { title: "向原雇主索取離職證明書", detail: "必須載明「非自願離職」字樣，這是最關鍵且無法由系統代取的文件。", isPrerequisite: true },
      { title: "至公立就業服務機構辦理求職登記", detail: "須本人臨櫃，並填寫失業給付申請書及給付收據。" },
      { title: "接受就業推介或職訓安排", detail: "經 14 日內無法推介就業或安排職訓，才符合請領條件。" },
      { title: "由就業服務機構轉送勞保局核定", detail: "不需自行送件至勞保局。" },
      { title: "每月辦理失業再認定", detail: "須定期回報求職情形，未辦理將停止發給。" },
    ],
    links: [
      { label: "勞動部勞工保險局 · 失業給付", note: "給付條件與金額計算" },
      { label: "台灣就業通 · 就業服務站查詢", note: "查詢最近的辦理地點" },
      { label: "全國法規資料庫 · 就業保險法", note: "法規原文" },
    ],
  },
  relief: {
    fullDescription:
      "針對家庭因負擔家計者失業、罹患重傷病、死亡、失蹤或其他原因，導致生活陷於困境的家庭，提供一次性的救助金。核發金額依家庭人口數與困境程度認定，經訪視評估後從速核發，屬急需救助性質，處理時程通常較其他項目快。",
    authority: "衛生福利部社會救助及社工司（政策）",
    level: "中央訂定 · 地方執行",
    area: "各縣市公所受理，可於戶籍地或現居地申請",
    onlineNote: "須臨櫃申請（因需訪視評估）",
    steps: [
      { title: "準備致生急難的事由證明", detail: "例如死亡證明書、診斷證明書、非自願離職證明等。", isPrerequisite: true },
      { title: "向公所社會課提出申請", detail: "可於戶籍地或實際居住地的公所辦理，不限戶籍地。" },
      { title: "配合訪視小組實地訪查", detail: "承辦人員會實地了解家庭狀況與急迫程度。" },
      { title: "審查會核定金額", detail: "依家庭人口數與困境程度決定核發額度。" },
      { title: "核定後撥款", detail: "屬急難性質，核定與撥款時程通常較短。" },
    ],
    links: [
      { label: "衛福部 · 急難紓困實施方案", note: "受理條件與核發標準" },
      { label: "1957 福利諮詢專線", note: "電話諮詢與轉介" },
      { label: "各縣市公所社會課", note: "查詢受理窗口" },
    ],
  },
};
