import { useState } from "react";

import type { ProfileField } from "../../types/navigator";

type EditFieldModalProps = {
  field: ProfileField;
  onSave: (value: string) => void;
  onClose: () => void;
};

export function EditFieldModal({ field, onSave, onClose }: EditFieldModalProps) {
  const [draft, setDraft] = useState(field.value);

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/40 p-5"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <h3 className="text-lg font-bold text-slate-900">修改「{field.label}」</h3>
        <p className="mt-1 text-sm leading-6 text-slate-400">{field.why}</p>

        {field.options ? (
          <div className="mt-4 space-y-2">
            {field.options.map((option) => (
              <button
                className={`w-full rounded-xl border px-4 py-3 text-left text-base transition ${
                  option === field.value
                    ? "border-[#0d7360] bg-[#e6f2ef] font-bold text-[#0d7360]"
                    : "border-slate-200 hover:border-[#74a9a3] hover:bg-[#f1f8f6]"
                }`}
                key={option}
                onClick={() => onSave(option)}
                type="button"
              >
                {option}
              </button>
            ))}
            <button
              className="w-full rounded-xl border border-slate-200 px-4 py-2 text-sm font-bold text-slate-500"
              onClick={onClose}
              type="button"
            >
              取消
            </button>
          </div>
        ) : (
          <div className="mt-4">
            <input
              className="w-full rounded-xl border border-slate-200 px-4 py-3 text-base outline-none focus:border-[#5da79e] focus:ring-4 focus:ring-[#5da79e]/15"
              onChange={(event) => setDraft(event.target.value)}
              value={draft}
            />
            <div className="mt-4 flex gap-2">
              <button
                className="rounded-xl bg-[#153f3b] px-4 py-2 text-sm font-bold text-white transition hover:bg-[#1c504b]"
                onClick={() => onSave(draft)}
                type="button"
              >
                儲存
              </button>
              <button
                className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-bold text-slate-500"
                onClick={onClose}
                type="button"
              >
                取消
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
