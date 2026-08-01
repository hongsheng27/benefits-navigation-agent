import { lifeEventName } from "./copy";

type EventConfirmationProps = {
  lifeEvent: string;
  disabled: boolean;
  onConfirm: () => void;
  onRedescribe: () => void;
};

/**
 * 事件辨識結果的確認。
 *
 * 事件代號決定後面每一步展開什麼問題，猜錯會讓使用者被問一整串無關的事，所以由使用者
 * 拍板而不是直接往下走。
 */
export function EventConfirmation({
  lifeEvent,
  disabled,
  onConfirm,
  onRedescribe,
}: EventConfirmationProps) {
  return (
    <div
      aria-live="polite"
      className="mt-6 border-l-2 border-[#2f4f45] bg-[#f1f4f0] px-4 py-5 sm:px-5"
    >
      <p className="text-[0.85rem] leading-[1.9] tracking-[0.06em] text-[#2f4f45]">
        我讀到的是
      </p>
      <p className="mt-1.5 text-[1.05rem] leading-[1.8] font-semibold text-[#171513]">
        {lifeEventName(lifeEvent)}
      </p>
      <p className="mt-2 text-[0.88rem] leading-[2] text-[#4a453d]">
        接下來要問的條件會依這個判斷展開，所以先請你確認。理解錯了可以重新描述。
      </p>

      <div className="mt-5 flex flex-wrap gap-x-4 gap-y-3">
        <button
          type="button"
          onClick={onConfirm}
          disabled={disabled}
          className="rounded-sm bg-[#2f4f45] px-5 py-2.5 text-[0.92rem] leading-[1.8] font-semibold tracking-[0.04em] text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed disabled:bg-[#ddd5c7] disabled:text-[#6b6459]"
        >
          對，就是這件事
        </button>
        <button
          type="button"
          onClick={onRedescribe}
          disabled={disabled}
          className="rounded-sm border border-[#c9c0b0] bg-[#f7f4ee] px-5 py-2.5 text-[0.92rem] leading-[1.8] text-[#3a352e] transition-colors hover:border-[#2f4f45] hover:text-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed disabled:text-[#8b8377]"
        >
          不太對，我重新描述
        </button>
      </div>
    </div>
  );
}
