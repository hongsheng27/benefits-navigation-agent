import type { DimKey } from "../types/navigator";

export type DimMatcher = {
  key: DimKey;
  tag: string;
  keywords: string[];
};

export const DIM_MATCHERS: DimMatcher[] = [
  {
    key: "bereave",
    tag: "喪偶",
    keywords: ["過世", "走了", "往生", "去世", "死", "喪"],
  },
  {
    key: "children",
    tag: "育兒",
    keywords: ["小孩", "孩子", "子女", "兒子", "女兒", "念書", "上學"],
  },
  {
    key: "jobless",
    tag: "收入中斷",
    keywords: ["工作", "失業", "離職", "資遣", "裁員", "沒收入", "沒工作"],
  },
  {
    key: "money",
    tag: "生活困難",
    keywords: ["錢", "生活費", "撐不下", "付不出", "困難", "經濟"],
  },
  {
    key: "rent",
    tag: "居住負擔",
    keywords: ["房租", "租金", "房子", "住"],
  },
  {
    key: "care",
    tag: "照顧負擔",
    keywords: ["生病", "照顧", "住院", "失能", "長輩", "父母"],
  },
];

export type FollowUp = {
  need: DimKey;
  ask: string;
  chips: string[];
};

export const FOLLOW_UPS: FollowUp[] = [
  {
    need: "children",
    ask: "我了解了，這一定很不容易。想再多問一點：家裡還有其他人需要你照顧嗎？例如小孩或長輩。",
    chips: ["有兩個小孩要養", "有一個小孩", "要照顧長輩", "只有我自己"],
  },
  {
    need: "jobless",
    ask: "謝謝你告訴我。那你目前還有在工作嗎？家裡現在的經濟來源大概是什麼狀況？",
    chips: ["最近也失業了", "有工作但收入不夠", "沒有固定收入", "還在工作"],
  },
  {
    need: "money",
    ask: "我想確認一下你現在最急的是什麼——是生活費、房租，還是有其他馬上要處理的支出？",
    chips: ["生活費不夠", "房租快付不出來", "喪葬費用", "還不確定"],
  },
];

export const EXAMPLE_EVENTS = [
  "家人剛過世，不知道接下來要辦什麼",
  "家人突然重病，需要安排返家照護",
];

export const OPENING_MESSAGE =
  "你好，我是接住的協助小幫手。可以先跟我說說，最近發生了什麼事嗎？不用擔心用詞，用你自己的話說就好。";
