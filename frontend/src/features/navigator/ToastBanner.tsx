import { useNavigator } from "./NavigatorContext";

export function ToastBanner() {
  const { state } = useNavigator();

  if (!state.toast) {
    return null;
  }

  return (
    <div
      aria-live="polite"
      className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-full bg-slate-900 px-6 py-3 text-sm text-white shadow-lg"
      role="status"
    >
      {state.toast}
    </div>
  );
}
