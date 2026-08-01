/**
 * 諮詢後面板的 Copilot stub。
 *
 * 第一版不呼叫後端／Bedrock：用預寫摘要與關鍵字回覆示範問答。
 * 不做資格判定；遇到「可不可以領／算不算符合」會引導回規則結果與官方窗口。
 */

import type { CopilotContext, CopilotMessage } from "../types/postConsult";

function messageId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export function buildCopilotGreeting(context: CopilotContext): CopilotMessage {
  if (context.kind === "related_provisions") {
    const titles =
      context.provisionTitles.length > 0
        ? context.provisionTitles.map((title) => `「${title}」`).join("、")
        : "目前整理到的官方網頁摘錄";
    return {
      id: messageId("greet"),
      role: "assistant",
      content:
        `我先用白話整理了與「${context.lifeEventLabel}」較相關的依據：${titles}。` +
        "左側可看原文摘錄；你也可以問期限、金額差在哪、要去哪個窗口。" +
        "提醒：這些是候選摘錄，不是最終核定，也不能由我判定你是否符合資格。",
    };
  }

  return {
    id: messageId("greet"),
    role: "assistant",
    content:
      `這份「${context.guideTitle ?? "申請解說"}」把常見流程拆成步驟與應備文件。` +
      "你可以問某一份文件為什麼需要、哪一步要先做，或某個縣市窗口差在哪。" +
      "我只協助說明流程，不會代你送件，也不會判定能不能領到補助。",
  };
}

function mentionsEligibility(question: string): boolean {
  return /符不符合|可不可以領|能不能申請|有沒有資格|會不會過|一定能領/.test(
    question,
  );
}

function replyRelatedProvisions(question: string, context: CopilotContext): string {
  if (mentionsEligibility(question)) {
    return (
      "資格能不能成立，要由系統的規則結果與受理機關認定，我不能替你下結論。" +
      "建議你對照諮詢結果裡各項目的狀態，並以左側官方摘錄的條件向窗口確認。"
    );
  }
  if (/期限|多久|幾天|幾個月|時效/.test(question)) {
    return (
      "期限常因縣市而異：例如臺北市環保葬鼓勵金常見是領回後 2 個月內完成環保葬、完成後 1 個月內申請；" +
      "新北則多為遷出或起掘後 1 年內完成、完成後 1 個月內臨櫃。請以左側該筆來源的原文為準。"
    );
  }
  if (/金額|多少錢|幾萬|7000|七千/.test(question)) {
    return (
      "金額也依來源與骨灰／骨骸而不同。新北常見從 7,000 到 2 萬；臺北、桃園、澎湖也多落在 1 萬或 2 萬這檔。" +
      "左側每筆法條下方有白話摘要，可先對你的情況最接近的那一筆。"
    );
  }
  if (/聯合奠祭|免費服務/.test(question)) {
    return (
      "臺北市聯合奠祭是免費殯葬服務（約 23 項），不是現金鼓勵金；要符合約 10 類資格之一並帶齊證明。" +
      "若沒有資格證明，可能改為部分項目減半收費。詳見左側「聯合奠祭家屬須知」。"
    );
  }
  if (/窗口|去哪|哪裡申請|臨櫃/.test(question)) {
    return (
      "窗口通常是各縣市殯葬管理處、殯儀館服務中心或區公所。" +
      `你目前相關摘錄包括：${context.provisionTitles.join("、") || "見左側列表"}。` +
      "點開來源連結可看到該機關的申請說明。"
    );
  }
  return (
    "我可以幫你對照左側摘錄的重點：誰可以申請、期限、金額級距、要帶什麼。" +
    "請盡量指出縣市或方案名稱（例如新北環保葬、臺北聯合奠祭），我會講得更具體。" +
    "若問題涉及「你個案是否符合」，請回到諮詢結果或洽官方窗口。"
  );
}

function replyApplicationGuide(question: string, context: CopilotContext): string {
  if (mentionsEligibility(question)) {
    return (
      "申請解說只說明「通常怎麼走」，不能代替資格判定。" +
      "請先看諮詢結果各項目狀態；若仍標示需要更多資料或人工協助，代表還不能自動認定。"
    );
  }
  if (/文件|證明|要帶|準備/.test(question)) {
    return (
      "常見會先備死亡證明與身分／關係證明；若要申請環保葬鼓勵金，再加遷出證明、完成環保葬證明與帳戶資料。" +
      "聯合奠祭另需資格證明與亡者照片。左側每個步驟都有應備文件清單。"
    );
  }
  if (/順序|先做|第幾|哪一步/.test(question)) {
    return (
      "建議順序多半是：死亡登記 → 整理喪葬文件 → 向地方殯葬窗口申請鼓勵金或聯合奠祭 → 再確認勞保等中央項目。" +
      "有十日或一個月這類期限的，應優先處理，避免後面卡住。"
    );
  }
  if (/勞保|喪葬給付|中央/.test(question)) {
    return (
      "勞保喪葬給付與地方政府環保葬鼓勵金是不同管道，文件與時效不要混用。" +
      "若諮詢結果已列出相關項目，請以其狀態為準，並向勞保局確認當下申請方式。"
    );
  }
  return (
    `關於「${context.guideTitle ?? "申請流程"}」，我可以解釋某一步在做什麼、文件用途或窗口差異。` +
    "試著問「第一步要帶什麼」或「聯合奠祭期限」，我會對應到左側步驟說明。"
  );
}

/** 依面板類型產生 stub 回覆（非真實 LLM）。 */
export function replyToCopilot(
  question: string,
  context: CopilotContext,
): CopilotMessage {
  const trimmed = question.trim();
  const content =
    trimmed.length === 0
      ? "請先輸入你想了解的問題，例如期限、文件或窗口。"
      : context.kind === "related_provisions"
        ? replyRelatedProvisions(trimmed, context)
        : replyApplicationGuide(trimmed, context);

  return {
    id: messageId("reply"),
    role: "assistant",
    content,
  };
}

export function createUserMessage(content: string): CopilotMessage {
  return {
    id: messageId("user"),
    role: "user",
    content: content.trim(),
  };
}
