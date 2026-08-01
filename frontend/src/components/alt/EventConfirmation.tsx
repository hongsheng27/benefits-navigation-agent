import { useMemo, useState } from "react";

import { lifeEventName } from "./copy";

const MAX_SELECTED = 5;

type EventConfirmationProps = {
  /** 模型建議、預設勾選 */
  lifeEvents: string[];
  /** 另外三個潛在選項，預設未勾選 */
  extraCandidateLifeEvents: string[];
  /** 舊路徑相容：單一事件 */
  lifeEvent?: string | null;
  disabled: boolean;
  onConfirm: (eventIds: string[]) => void;
  onRedescribe: () => void;
};

/**
 * 多事件確認：預設勾選建議、可加勾候補，單次最多五個。
 */
export function EventConfirmation({
  lifeEvents,
  extraCandidateLifeEvents,
  lifeEvent = null,
  disabled,
  onConfirm,
  onRedescribe,
}: EventConfirmationProps) {
  const suggested = useMemo(() => {
    if (lifeEvents.length > 0) {
      return lifeEvents;
    }
    return lifeEvent ? [lifeEvent] : [];
  }, [lifeEvents, lifeEvent]);

  const [selected, setSelected] = useState<string[]>(() => [...suggested]);

  const extras = extraCandidateLifeEvents.filter(
    (eventId) => !suggested.includes(eventId),
  );

  function toggle(eventId: string) {
    if (disabled) {
      return;
    }
    setSelected((current) => {
      if (current.includes(eventId)) {
        return current.filter((id) => id !== eventId);
      }
      if (current.length >= MAX_SELECTED) {
        return current;
      }
      return [...current, eventId];
    });
  }

  const canConfirm = selected.length > 0 && selected.length <= MAX_SELECTED;

  return (
    <div
      aria-live="polite"
      className="mt-6 border-l-2 border-[#2f4f45] bg-[#f1f4f0] px-4 py-5 sm:px-5"
    >
      <p className="text-[0.85rem] leading-[1.9] tracking-[0.06em] text-[#2f4f45]">
        我們理解成以下情況（可多選）
      </p>
      <p className="mt-2 text-[0.88rem] leading-[1.75] text-[#5c564e]">
        單次查詢最多選 {MAX_SELECTED} 個情況。後面會依你勾選的項目展開相關資源。
      </p>

      <fieldset className="mt-4" disabled={disabled}>
        <legend className="sr-only">建議的情況（預設已勾選）</legend>
        <ul className="flex flex-col gap-2">
          {suggested.map((eventId) => (
            <li key={eventId}>
              <label className="flex cursor-pointer items-start gap-3 rounded-sm bg-[#faf8f4] px-3 py-2.5 ring-1 ring-[#d9d2c4]">
                <input
                  type="checkbox"
                  checked={selected.includes(eventId)}
                  onChange={() => toggle(eventId)}
                  className="mt-1"
                />
                <span className="text-[1rem] leading-[1.7] font-semibold text-[#171513]">
                  {lifeEventName(eventId)}
                </span>
              </label>
            </li>
          ))}
        </ul>
      </fieldset>

      {extras.length > 0 ? (
        <fieldset className="mt-5" disabled={disabled}>
          <legend className="text-[0.85rem] font-semibold text-[#2f4f45]">
            也可能相關（可加選）
          </legend>
          <ul className="mt-2 flex flex-col gap-2">
            {extras.map((eventId) => (
              <li key={eventId}>
                <label className="flex cursor-pointer items-start gap-3 rounded-sm px-3 py-2.5 ring-1 ring-[#e0d8ca]">
                  <input
                    type="checkbox"
                    checked={selected.includes(eventId)}
                    onChange={() => toggle(eventId)}
                    className="mt-1"
                  />
                  <span className="text-[0.95rem] leading-[1.7] text-[#3a352e]">
                    {lifeEventName(eventId)}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
      ) : null}

      {selected.length >= MAX_SELECTED ? (
        <p className="mt-3 text-[0.82rem] text-[#8b5a2b]">
          已達上限 {MAX_SELECTED} 個。若要改選，請先取消其中一項。
        </p>
      ) : null}

      <div className="mt-5 flex flex-wrap gap-x-4 gap-y-3">
        <button
          type="button"
          onClick={() => onConfirm(selected)}
          disabled={disabled || !canConfirm}
          className="rounded-sm bg-[#2f4f45] px-5 py-2.5 text-[0.92rem] leading-[1.8] font-semibold tracking-[0.04em] text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed disabled:bg-[#ddd5c7] disabled:text-[#6b6459]"
        >
          對，就是這些
        </button>
        <button
          type="button"
          onClick={onRedescribe}
          disabled={disabled}
          className="rounded-sm border border-[#c9c0b0] bg-[#f7f4ee] px-5 py-2.5 text-[0.92rem] leading-[1.8] text-[#3a352e] transition-colors hover:border-[#2f4f45] hover:text-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed disabled:text-[#8b8377]"
        >
          不太對，我再說明一次
        </button>
      </div>
    </div>
  );
}
