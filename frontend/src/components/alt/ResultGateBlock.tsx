import { useState } from "react";

type ResultGateBlockProps = {
  situationLabel: string;
  disabled?: boolean;
  onViewResults: () => void;
  onConfirmRestart: () => void;
  /** 嵌在對話泡泡流程時，略過外層標題（助理訊息已說明）。 */
  embeddedInChat?: boolean;
};

/**
 * 結果前確認：查看結果，或確認後清空重來。
 * 可獨立顯示，也可嵌在對話窗內。
 */
export function ResultGateBlock({
  situationLabel,
  disabled = false,
  onViewResults,
  onConfirmRestart,
  embeddedInChat = false,
}: ResultGateBlockProps) {
  const [restartConfirmOpen, setRestartConfirmOpen] = useState(false);

  if (restartConfirmOpen) {
    return (
      <div
        role="alertdialog"
        aria-labelledby="restart-confirm-title"
        aria-describedby="restart-confirm-desc"
        className={
          embeddedInChat
            ? "self-start rounded-sm border border-[#e2d3b5] bg-[#f8f3ea] px-3.5 py-3.5"
            : "rounded-sm border border-[#e2d3b5] bg-[#f8f3ea] px-5 py-5"
        }
      >
        <h2
          id="restart-confirm-title"
          className="text-[1.02rem] font-semibold leading-[1.6] text-[#171513]"
        >
          確定要從頭再說一次嗎？
        </h2>
        <p
          id="restart-confirm-desc"
          className="mt-2 text-[0.88rem] leading-[1.95] text-[#4a453d]"
        >
          前面在對話裡輸入與選擇過的內容都會清掉，需要重新說明發生的事。這個動作無法復原。
        </p>
        <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          <button
            type="button"
            disabled={disabled}
            onClick={() => {
              setRestartConfirmOpen(false);
              onConfirmRestart();
            }}
            className="rounded-sm bg-[#2f4f45] px-4 py-2 text-[0.88rem] font-semibold tracking-[0.02em] text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed disabled:bg-[#ddd5c7] disabled:text-[#6b6459]"
          >
            確定，從頭開始
          </button>
          <button
            type="button"
            disabled={disabled}
            onClick={() => setRestartConfirmOpen(false)}
            className="rounded-sm border border-[#c9c0b0] bg-transparent px-4 py-2 text-[0.88rem] text-[#3a352e] transition-colors hover:border-[#2f4f45] hover:text-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed disabled:text-[#a89f90]"
          >
            先不要，再想想
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={embeddedInChat ? "self-start" : undefined}>
      {!embeddedInChat ? (
        <p className="text-[0.92rem] leading-[1.95] text-[#4a453d]">
          關於「{situationLabel}」，我們好像已經掌握夠多了。要先看看整理結果嗎？若還有別的情況，也可以從頭再說一次。
        </p>
      ) : null}
      <div
        className={`flex flex-wrap gap-2 ${embeddedInChat ? "" : "mt-4"}`}
        role="group"
        aria-label="是否查看結果"
      >
        <button
          type="button"
          disabled={disabled}
          onClick={onViewResults}
          className="rounded-sm border border-[#2f4f45] bg-[#2f4f45] px-3.5 py-2 text-[0.88rem] leading-[1.6] font-semibold text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed disabled:opacity-60"
        >
          查看結果
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => setRestartConfirmOpen(true)}
          className="rounded-sm border border-[#cfc5b4] bg-[#fffdfa] px-3.5 py-2 text-[0.88rem] leading-[1.6] text-[#3a352e] transition-colors hover:border-[#2f4f45] hover:text-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed disabled:opacity-60"
        >
          我還有其他情況想說
        </button>
      </div>
    </div>
  );
}
