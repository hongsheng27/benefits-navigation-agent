import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

import type {
  AttributeValue,
  QuestionGroupView,
  QuestionView,
} from "../../types/session";
import { fieldLabel, optionLabel } from "./copy";
import { QuestionGroupList } from "./QuestionGroupList";
import { ResultGateBlock } from "./ResultGateBlock";

type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  content: string;
};

type ChoiceOption = {
  label: string;
  value: AttributeValue;
};

export type AttributeChatResultGate = {
  situationLabel: string;
  onViewResults: () => void;
  onConfirmRestart: () => void;
};

type AttributeChatPanelProps = {
  groups: QuestionGroupView[];
  collectorQuestion: string | null;
  disabled: boolean;
  readOnly?: boolean;
  answeredCount: number;
  onChatTurn: (text: string) => void | Promise<void>;
  onSubmitChoices: (answers: Record<string, AttributeValue>) => void;
  initialChoiceAnswers?: Record<string, AttributeValue>;
  /** 資訊已齊時，在同一對話窗詢問是否查看結果。 */
  resultGate?: AttributeChatResultGate | null;
};

const RESULT_GATE_MESSAGE_ID = "result_gate";
const BRIDGE_MESSAGE_ID = "bridge";
const RESULT_GATE_PROMPT =
  "我們好像已經掌握夠多了。要先看看整理結果嗎？若你還有別的情況想說，也可以從頭再說明一次。";

function bridgePrompt(situationLabel: string): string {
  return `好，我們先以「${situationLabel}」往下整理。`;
}

function firstMissingQuestion(groups: QuestionGroupView[]): QuestionView | null {
  return groups[0]?.questions[0] ?? null;
}

function isChoiceQuestion(question: QuestionView): boolean {
  if (question.valueKind === "boolean") {
    return true;
  }
  return question.optionIds.length > 0;
}

function choiceOptionsFor(question: QuestionView): ChoiceOption[] {
  if (question.valueKind === "boolean") {
    return [
      { label: "是", value: true },
      { label: "否", value: false },
    ];
  }
  return question.optionIds.map((optionId) => ({
    label: optionLabel(optionId),
    value: optionId,
  }));
}

/** 畫面優先用前端正面問句；後端 collector／purpose 說明不當題目。 */
function promptForField(
  collectorQuestion: string | null,
  fieldId: string | null,
): string {
  if (fieldId) {
    const label = fieldLabel(fieldId);
    if (label !== fieldId) {
      return label;
    }
  }
  if (collectorQuestion?.trim()) {
    return collectorQuestion.trim();
  }
  return "請用幾句話補充還需要的條件，例如所在縣市或投保身分。";
}

/**
 * 對話式資格蒐集：有選項時像 Claude 一樣可點選（也可打字）；
 * 開放式才純文字。完整選擇題表單仍可當備援。
 */
export function AttributeChatPanel({
  groups,
  collectorQuestion,
  disabled,
  readOnly = false,
  answeredCount,
  onChatTurn,
  onSubmitChoices,
  initialChoiceAnswers = {},
  resultGate = null,
}: AttributeChatPanelProps) {
  const [mode, setMode] = useState<"chat" | "choices">("chat");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const currentQuestion = useMemo(
    () => firstMissingQuestion(groups),
    [groups],
  );
  const currentFieldId = currentQuestion?.fieldId ?? null;
  const gateActive = resultGate !== null;
  const skippedQuestions =
    gateActive && groups.length === 0 && answeredCount === 0;

  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    // 確認後沒有追問時直接開閘門：先承接事件，再問要不要看結果。
    if (resultGate && groups.length === 0) {
      return [
        {
          id: BRIDGE_MESSAGE_ID,
          role: "assistant",
          content: bridgePrompt(resultGate.situationLabel),
        },
        {
          id: RESULT_GATE_MESSAGE_ID,
          role: "assistant",
          content: RESULT_GATE_PROMPT,
        },
      ];
    }
    return [
      {
        id: "seed",
        role: "assistant",
        content: promptForField(
          collectorQuestion,
          firstMissingQuestion(groups)?.fieldId ?? null,
        ),
      },
    ];
  });

  const showChoiceChips =
    !gateActive &&
    currentQuestion !== null &&
    isChoiceQuestion(currentQuestion);
  const choiceOptions = currentQuestion ? choiceOptionsFor(currentQuestion) : [];

  useEffect(() => {
    if (busy || gateActive) {
      return;
    }
    if (currentQuestion === null) {
      return;
    }
    const prompt = promptForField(collectorQuestion, currentFieldId);
    if (!prompt) {
      return;
    }
    setMessages((current) => {
      const last = current[current.length - 1];
      if (last?.role === "assistant" && last.content === prompt) {
        return current;
      }
      // 尚在等使用者回答時，改寫上一句助理問句（避免留下 purpose 說明）。
      if (last?.role === "assistant") {
        return [
          ...current.slice(0, -1),
          { id: last.id, role: "assistant", content: prompt },
        ];
      }
      return [
        ...current,
        {
          id: `ask_${Date.now()}`,
          role: "assistant",
          content: prompt,
        },
      ];
    });
  }, [collectorQuestion, currentFieldId, currentQuestion, busy, gateActive]);

  useEffect(() => {
    if (!gateActive || !resultGate) {
      return;
    }
    setMode("chat");
    setMessages((current) => {
      if (current.some((message) => message.id === RESULT_GATE_MESSAGE_ID)) {
        return current;
      }
      const withoutTrailingEmptyAsk = (() => {
        const last = current[current.length - 1];
        if (
          last?.role === "assistant" &&
          last.id !== RESULT_GATE_MESSAGE_ID &&
          last.id !== BRIDGE_MESSAGE_ID &&
          currentQuestion === null
        ) {
          return current.slice(0, -1);
        }
        return current;
      })();
      const hasUserTurn = withoutTrailingEmptyAsk.some(
        (message) => message.role === "user",
      );
      const hasBridge = withoutTrailingEmptyAsk.some(
        (message) => message.id === BRIDGE_MESSAGE_ID,
      );
      // 從未進過問答時補承接句，避免只剩閘門像另開一頁。
      const withBridge =
        !hasUserTurn && !hasBridge
          ? [
              {
                id: BRIDGE_MESSAGE_ID,
                role: "assistant" as const,
                content: bridgePrompt(resultGate.situationLabel),
              },
              ...withoutTrailingEmptyAsk,
            ]
          : withoutTrailingEmptyAsk;
      return [
        ...withBridge,
        {
          id: RESULT_GATE_MESSAGE_ID,
          role: "assistant",
          content: RESULT_GATE_PROMPT,
        },
      ];
    });
  }, [gateActive, currentQuestion, resultGate]);

  async function submitChatText(text: string) {
    if (!text || disabled || readOnly || busy) {
      return;
    }
    setBusy(true);
    setDraft("");
    setMessages((current) => [
      ...current,
      { id: `user_${Date.now()}`, role: "user", content: text },
    ]);
    try {
      await onChatTurn(text);
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitChatText(draft.trim());
  }

  async function handlePickChoice(option: ChoiceOption) {
    if (!currentQuestion || disabled || readOnly || busy) {
      return;
    }
    setBusy(true);
    setDraft("");
    setMessages((current) => [
      ...current,
      { id: `user_${Date.now()}`, role: "user", content: option.label },
    ]);
    try {
      onSubmitChoices({ [currentQuestion.fieldId]: option.value });
    } finally {
      setBusy(false);
    }
  }

  if (mode === "choices" && !gateActive) {
    return (
      <div>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <p className="text-[0.88rem] text-[#5c564e]">
            一次回答多題。已記錄 {answeredCount} 項條件。
          </p>
          <button
            type="button"
            disabled={disabled || readOnly}
            onClick={() => setMode("chat")}
            className="text-[0.88rem] font-semibold text-[#2f4f45] underline-offset-4 hover:underline"
          >
            改回一題一題
          </button>
        </div>
        <QuestionGroupList
          groups={groups}
          disabled={disabled}
          readOnly={readOnly}
          initialAnswers={initialChoiceAnswers}
          onSubmit={onSubmitChoices}
        />
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-[0.88rem] leading-[1.7] text-[#5c564e]">
          {gateActive
            ? skippedQuestions
              ? "目前沒有要再問的細節。你可以先看整理結果，或從頭再說一次其他情況。"
              : "問得差不多了。你可以先看整理結果，或從頭再說一次其他情況。"
            : showChoiceChips
              ? "可直接點選下方選項，或用自己的話打字。選項會寫成條件代號，不會用對話判定資格。"
              : "這題沒有固定選項，請用自己的話回答。我們會轉成條件代號，不會用對話判定資格。"}{" "}
          已記錄 {answeredCount} 項。
        </p>
        {!gateActive ? (
          <button
            type="button"
            disabled={disabled || readOnly}
            onClick={() => setMode("choices")}
            className="shrink-0 text-[0.88rem] font-semibold text-[#2f4f45] underline-offset-4 hover:underline"
          >
            一次回答多題
          </button>
        ) : null}
      </div>

      <div className="flex min-h-[14rem] flex-col gap-3 rounded-sm border border-[#e0d8ca] bg-[#f4f0e8] px-4 py-4">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`max-w-[95%] rounded-sm px-3 py-2.5 text-[0.88rem] leading-[1.75] ${
              message.role === "assistant"
                ? "self-start bg-[#faf8f4] text-[#3a352e] ring-1 ring-[#e0d8ca]"
                : "self-end bg-[#2f4f45] text-[#f7f4ee]"
            }`}
          >
            {message.content}
          </div>
        ))}

        {showChoiceChips && !busy && !readOnly ? (
          <div
            className="flex flex-wrap gap-2 self-start"
            role="group"
            aria-label="可選答案"
          >
            {choiceOptions.map((option) => (
              <button
                key={`${String(option.value)}-${option.label}`}
                type="button"
                disabled={disabled || busy}
                onClick={() => void handlePickChoice(option)}
                className="rounded-sm border border-[#cfc5b4] bg-[#fffdfa] px-3.5 py-2 text-[0.88rem] leading-[1.6] text-[#3a352e] transition-colors hover:border-[#2f4f45] hover:text-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {option.label}
              </button>
            ))}
          </div>
        ) : null}

        {gateActive && resultGate && !busy ? (
          <ResultGateBlock
            embeddedInChat
            situationLabel={resultGate.situationLabel}
            disabled={disabled}
            onViewResults={resultGate.onViewResults}
            onConfirmRestart={resultGate.onConfirmRestart}
          />
        ) : null}

        {busy ? (
          <p className="text-[0.82rem] text-[#8b8377]">正在整理你的回答…</p>
        ) : null}
      </div>

      {!gateActive ? (
        <form onSubmit={(event) => void handleSubmit(event)} className="mt-4">
          <label className="sr-only" htmlFor="attribute-chat-input">
            {showChoiceChips ? "用文字回答，或上方點選選項" : "用文字回答目前問題"}
          </label>
          <div className="flex gap-2">
            <input
              id="attribute-chat-input"
              type="text"
              value={draft}
              disabled={disabled || readOnly || busy}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={
                showChoiceChips
                  ? "或打字回答，例如：臺北市／有勞保"
                  : "請用幾句話說明"
              }
              className="min-w-0 flex-1 rounded-sm border border-[#c9c0b0] bg-[#faf8f4] px-3 py-2.5 text-[0.92rem] outline-none focus:border-[#2f4f45] disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={disabled || readOnly || busy || !draft.trim()}
              className="shrink-0 rounded-sm bg-[#2f4f45] px-4 py-2.5 text-[0.9rem] font-semibold text-[#f7f4ee] transition-colors hover:bg-[#254038] disabled:cursor-not-allowed disabled:bg-[#ddd5c7] disabled:text-[#6b6459]"
            >
              送出
            </button>
          </div>
        </form>
      ) : null}
    </div>
  );
}
