/**
 * 把 Copilot 回覆裡常見的輕量 Markdown 排成可讀區塊。
 * 不引入 markdown 套件；只處理段落、粗體、條列與「步驟」標題。
 */

import type { ReactNode } from "react";

/** 先把黏在一起的步驟／條列拆成換行，方便後續解析。 */
export function normalizeCopilotReplyText(raw: string): string {
  let text = raw.replace(/\r\n/g, "\n").trim();
  // **步驟 N：標題** → 獨立成段
  text = text.replace(
    /\s*\*\*\s*(步驟\s*\d+\s*[：:][^*]+?)\*\*/g,
    "\n\n**$1**\n",
  );
  text = text.replace(
    /\s*\*\*\s*((?:重點提醒|注意|提醒)[：:]?[^*]*?)\*\*/g,
    "\n\n**$1**\n",
  );
  // 句中「 - 項目」改成條列（避開英文連字號詞）
  text = text.replace(/([。；：:!？?\n])\s*-\s+/g, "$1\n- ");
  text = text.replace(/\n{3,}/g, "\n\n");
  return text.trim();
}

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /\*\*([^*]+)\*\*/g;
  let lastIndex = 0;
  let match = pattern.exec(text);
  let part = 0;
  while (match) {
    if (match.index > lastIndex) {
      nodes.push(
        <span key={`${keyPrefix}_t_${part}`}>{text.slice(lastIndex, match.index)}</span>,
      );
      part += 1;
    }
    nodes.push(
      <strong key={`${keyPrefix}_b_${part}`} className="font-semibold text-[#2f4f45]">
        {match[1]}
      </strong>,
    );
    part += 1;
    lastIndex = match.index + match[0].length;
    match = pattern.exec(text);
  }
  if (lastIndex < text.length) {
    nodes.push(<span key={`${keyPrefix}_t_${part}`}>{text.slice(lastIndex)}</span>);
  }
  return nodes;
}

type Block =
  | { type: "paragraph"; text: string }
  | { type: "heading"; text: string }
  | { type: "list"; items: string[] };

function isStepHeading(line: string): boolean {
  return (
    /^\*\*\s*步驟\s*\d+\s*[：:]/.test(line) ||
    /^\*\*\s*(重點提醒|注意|提醒)/.test(line)
  );
}

function isListItem(line: string): boolean {
  return /^[-*•]\s+/.test(line) || /^\d+[\.、．)]\s+/.test(line);
}

function stripListMarker(line: string): string {
  return line.replace(/^[-*•]\s+/, "").replace(/^\d+[\.、．)]\s+/, "");
}

export function parseCopilotReplyBlocks(raw: string): Block[] {
  const text = normalizeCopilotReplyText(raw);
  const lines = text.split("\n");
  const blocks: Block[] = [];
  let paragraphLines: string[] = [];
  let listItems: string[] = [];

  function flushParagraph() {
    const joined = paragraphLines.join(" ").trim();
    paragraphLines = [];
    if (!joined) {
      return;
    }
    if (isStepHeading(joined)) {
      blocks.push({ type: "heading", text: joined });
      return;
    }
    blocks.push({ type: "paragraph", text: joined });
  }

  function flushList() {
    if (listItems.length === 0) {
      return;
    }
    blocks.push({ type: "list", items: [...listItems] });
    listItems = [];
  }

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      flushList();
      flushParagraph();
      continue;
    }
    if (isListItem(line)) {
      flushParagraph();
      listItems.push(stripListMarker(line));
      continue;
    }
    flushList();
    if (isStepHeading(line)) {
      flushParagraph();
      blocks.push({ type: "heading", text: line });
      continue;
    }
    // 「**步驟 1：標題** 說明」同一行：標題 + 後續當段落
    const stepSplit = line.match(
      /^(\*\*\s*步驟\s*\d+\s*[：:][^*]*\*\*)\s+(.+)$/,
    );
    if (stepSplit) {
      flushParagraph();
      blocks.push({ type: "heading", text: stepSplit[1] });
      paragraphLines.push(stepSplit[2]);
      continue;
    }
    paragraphLines.push(line);
  }
  flushList();
  flushParagraph();
  return blocks;
}

type CopilotReplyBodyProps = {
  content: string;
  /** 使用者訊息維持淺色，助理訊息用預設字色。 */
  tone?: "assistant" | "user";
};

export function CopilotReplyBody({
  content,
  tone = "assistant",
}: CopilotReplyBodyProps) {
  if (tone === "user") {
    return <>{content}</>;
  }

  const blocks = parseCopilotReplyBlocks(content);
  if (blocks.length === 0) {
    return <>{content}</>;
  }

  return (
    <div className="space-y-2.5 text-left">
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          return (
            <p
              key={`h_${index}`}
              className="pt-1 text-[0.88rem] font-semibold leading-[1.7] text-[#2f4f45] first:pt-0"
            >
              {renderInline(block.text, `h_${index}`)}
            </p>
          );
        }
        if (block.type === "list") {
          return (
            <ul
              key={`l_${index}`}
              className="list-disc space-y-1.5 pl-5 text-[0.86rem] leading-[1.75] text-[#3a352e]"
            >
              {block.items.map((item, itemIndex) => (
                <li key={`li_${index}_${itemIndex}`}>
                  {renderInline(item, `li_${index}_${itemIndex}`)}
                </li>
              ))}
            </ul>
          );
        }
        return (
          <p
            key={`p_${index}`}
            className="text-[0.86rem] leading-[1.75] text-[#3a352e]"
          >
            {renderInline(block.text, `p_${index}`)}
          </p>
        );
      })}
    </div>
  );
}
