import type { MyDataSourceSet, ProfileState } from "../types/navigator";

export function createInitialProfile(): ProfileState {
  return {
    basic: {
      title: "基本資料",
      description: "用於判斷戶籍地適用的地方性補助，以及年齡相關的資格門檻。",
      fields: [
        { code: "name", label: "姓名", why: "產生申請表預填內容時使用", value: "李○芳", source: "self" },
        { code: "birth", label: "出生年", why: "年齡是多數給付的基本門檻條件", value: "1979 年", source: "self" },
        {
          code: "city",
          label: "戶籍地",
          why: "決定由哪個縣市受理，以及適用哪一套地方標準",
          value: "臺北市 中山區",
          source: "self",
          options: ["臺北市 中山區", "新北市 板橋區", "桃園市 中壢區", "其他"],
        },
        { code: "phone", label: "聯絡電話", why: "僅用於你主動要求人工協助時回撥", value: "09xx-xxx-xxx", source: "self" },
      ],
    },
    family: {
      title: "家庭狀況",
      description: "家戶組成影響平均收入計算，以及特殊境遇、育兒等項目的認定。",
      fields: [
        {
          code: "marital",
          label: "婚姻狀況",
          why: "喪偶、離婚是特殊境遇家庭的認定條件之一",
          value: "喪偶",
          source: "self",
          options: ["未婚", "已婚", "離婚", "喪偶"],
        },
        {
          code: "household",
          label: "同戶籍人數",
          why: "家戶人數是計算每人每月平均收入的分母",
          value: "3 人",
          source: "self",
          options: ["1 人", "2 人", "3 人", "4 人以上"],
        },
        {
          code: "children",
          label: "未成年子女數",
          why: "影響遺屬給付加給、育兒津貼與生活津貼核算",
          value: "2 位",
          source: "self",
          options: ["沒有", "1 位", "2 位", "3 位以上"],
        },
        {
          code: "relation",
          label: "與過世者關係",
          why: "請領資格與順位依親屬關係認定",
          value: "配偶",
          source: "self",
          options: ["配偶", "子女", "父母", "其他親屬"],
        },
      ],
    },
    econ: {
      title: "經濟狀況",
      description: "資力審查的核心欄位。授權 MyData 後可由官方資料直接帶入。",
      fields: [
        { code: "income", label: "家庭年所得", why: "低收、中低收與各項生活扶助的門檻依據", value: "", source: "self" },
        { code: "avg", label: "每人每月平均收入", why: "由年所得與家戶人數自動推算", value: "", source: "calc" },
        { code: "property", label: "不動產與車輛", why: "財產是否超過門檻會直接決定資格", value: "", source: "self" },
        { code: "deposit", label: "存款總額", why: "部分項目設有存款上限", value: "", source: "self" },
        { code: "labor", label: "本人勞保投保狀態", why: "影響就業保險相關給付的請領資格", value: "", source: "self" },
        {
          code: "employment",
          label: "目前就業狀況",
          why: "部分給付排除同時領取性質相同的補助",
          value: "",
          source: "self",
          options: ["未就業", "非自願離職", "有工作", "退休", "無工作能力"],
        },
      ],
    },
    status: {
      title: "身分別",
      description: "具備特定身分可開啟專屬補助項目，多數需官方證明認定。",
      fields: [
        { code: "lowincome", label: "低收 / 中低收入戶", why: "許多項目以此為前提條件", value: "", source: "self" },
        { code: "disability", label: "身心障礙證明", why: "身障相關補助的認定基礎", value: "", source: "self" },
        {
          code: "indigenous",
          label: "原住民身分",
          why: "原民會專屬補助項目的認定條件",
          value: "",
          source: "self",
          options: ["是", "否"],
        },
      ],
    },
  };
}

export const MY_DATA_SOURCE_SETS: MyDataSourceSet[] = [
  { name: "個人所得資料", org: "財政部財政資訊中心", fieldCode: "income" },
  { name: "財產歸屬清單", org: "財政部財政資訊中心", fieldCode: "property" },
  { name: "勞保被保險人投保資料", org: "勞動部勞工保險局", fieldCode: "labor" },
  { name: "全戶戶籍資料", org: "內政部戶政司", fieldCode: "household" },
  { name: "低收入戶／中低收入戶證明", org: "衛生福利部", fieldCode: "lowincome" },
  { name: "身心障礙證明", org: "衛生福利部", fieldCode: "disability" },
];

export const MYDATA_MOCK_VALUES: Record<string, string> = {
  income: "NT$ 312,000",
  property: "無不動產 · 汽車 1 輛",
  labor: "已退保（2 個月前）",
  household: "3 人",
  lowincome: "未取得資格",
  disability: "無",
};
