type ConfirmDialogProps = {
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDialog({
  title,
  description,
  confirmLabel,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/40 p-5"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onCancel();
        }
      }}
    >
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <h3 className="text-lg font-bold text-[#9e3a4e]">{title}</h3>
        <p className="mt-2 text-sm leading-6 text-slate-500">{description}</p>
        <div className="mt-5 flex gap-2">
          <button
            className="rounded-xl bg-[#9e3a4e] px-4 py-2 text-sm font-bold text-white transition hover:bg-[#873041]"
            onClick={onConfirm}
            type="button"
          >
            {confirmLabel}
          </button>
          <button
            className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-bold text-slate-500"
            onClick={onCancel}
            type="button"
          >
            取消
          </button>
        </div>
      </div>
    </div>
  );
}
