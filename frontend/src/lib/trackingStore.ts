/**
 * 本機追蹤暫存：已追蹤項目（localStorage）＋本輪諮詢待追蹤（sessionStorage）。
 * 後端尚無 POST /cases 前供結果頁／追蹤頁共用。
 */

import type { ItemView } from "../types/session";
import type {
  TrackedBenefitFlowStep,
  TrackedBenefitItem,
} from "../types/tracking";
import { itemCategoryLabel, itemName, lifeEventName } from "../components/alt/copy";
import { getItemDetail } from "../mocks/itemDetails";

const TRACKED_KEY = "jiezhu.trackedBenefitItems.v1";
const PENDING_KEY = "jiezhu.pendingBenefitItems.v1";

const FALLBACK_FLOW_LABELS = [
  "確認主管機關與申請方式",
  "備妥必要文件",
  "送件或洽詢窗口",
] as const;

export type PendingBenefitItem = {
  itemId: string;
  name: string;
  categoryLabel: string;
  lifeEventId: string;
  lifeEventLabel: string;
  agency?: string;
};

function canUseStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function readJson<T>(storage: Storage, key: string, fallback: T): T {
  try {
    const raw = storage.getItem(key);
    if (!raw) {
      return fallback;
    }
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function writeJson(storage: Storage, key: string, value: unknown): void {
  try {
    storage.setItem(key, JSON.stringify(value));
  } catch {
    // Quota or private mode — ignore for hackathon UX.
  }
}

/** 依項目詳情組步驟；沒有詳情時用通用三步。 */
export function buildFlowStepsForItem(itemId: string): TrackedBenefitFlowStep[] {
  const detail = getItemDetail(itemId);
  const labels =
    detail && detail.steps.length > 0 ? detail.steps : [...FALLBACK_FLOW_LABELS];
  return labels.map((label, index) => ({
    stepId: `${itemId}_step_${index + 1}`,
    label,
  }));
}

function normalizeTrackedItem(
  raw: Partial<TrackedBenefitItem> & Pick<TrackedBenefitItem, "itemId" | "name">,
): TrackedBenefitItem {
  const flowSteps =
    Array.isArray(raw.flowSteps) && raw.flowSteps.length > 0
      ? raw.flowSteps
      : buildFlowStepsForItem(raw.itemId);
  const completedStepCount = Math.min(
    Math.max(0, raw.completedStepCount ?? 0),
    flowSteps.length,
  );
  const currentLabel = flowSteps[completedStepCount]?.label;
  return {
    itemId: raw.itemId,
    name: raw.name,
    categoryLabel: raw.categoryLabel ?? "其他",
    lifeEventId: raw.lifeEventId ?? "unknown",
    lifeEventLabel: raw.lifeEventLabel ?? "你的情況",
    agency: raw.agency,
    nextAction:
      raw.nextAction ??
      (currentLabel
        ? `下一步：${currentLabel}`
        : completedStepCount >= flowSteps.length
          ? "這項已走完目前整理的步驟"
          : "回來看辦理進度與應備文件"),
    addedAt: raw.addedAt ?? new Date().toISOString(),
    flowSteps,
    completedStepCount,
  };
}

export function listTrackedBenefitItems(): TrackedBenefitItem[] {
  if (!canUseStorage()) {
    return [];
  }
  const items = readJson<Partial<TrackedBenefitItem>[]>(
    window.localStorage,
    TRACKED_KEY,
    [],
  );
  return items
    .filter(
      (item): item is Partial<TrackedBenefitItem> & Pick<TrackedBenefitItem, "itemId" | "name"> =>
        typeof item?.itemId === "string" && typeof item?.name === "string",
    )
    .map(normalizeTrackedItem)
    .sort((a, b) => (a.addedAt < b.addedAt ? 1 : -1));
}

export function isBenefitItemTracked(itemId: string): boolean {
  return listTrackedBenefitItems().some((item) => item.itemId === itemId);
}

export function addTrackedBenefitItem(
  input: Omit<TrackedBenefitItem, "addedAt" | "flowSteps" | "completedStepCount"> & {
    addedAt?: string;
    flowSteps?: TrackedBenefitFlowStep[];
    completedStepCount?: number;
  },
): TrackedBenefitItem {
  const next = normalizeTrackedItem({
    ...input,
    flowSteps: input.flowSteps ?? buildFlowStepsForItem(input.itemId),
    completedStepCount: input.completedStepCount ?? 0,
    addedAt: input.addedAt ?? new Date().toISOString(),
  });
  const current = listTrackedBenefitItems().filter(
    (item) => item.itemId !== next.itemId,
  );
  writeJson(window.localStorage, TRACKED_KEY, [next, ...current]);
  // 加入後從本輪待追蹤移除
  const pending = listPendingBenefitItems().filter(
    (item) => item.itemId !== next.itemId,
  );
  if (canUseStorage()) {
    writeJson(window.sessionStorage, PENDING_KEY, pending);
  }
  return next;
}

/** 將目前步驟標為完成，並推進到下一步。 */
export function advanceTrackedBenefitStep(
  itemId: string,
): TrackedBenefitItem | null {
  const items = listTrackedBenefitItems();
  const index = items.findIndex((item) => item.itemId === itemId);
  if (index < 0) {
    return null;
  }
  const current = items[index];
  if (current.completedStepCount >= current.flowSteps.length) {
    return current;
  }
  const completedStepCount = current.completedStepCount + 1;
  const nextStep = current.flowSteps[completedStepCount];
  const updated: TrackedBenefitItem = {
    ...current,
    completedStepCount,
    nextAction: nextStep
      ? `下一步：${nextStep.label}`
      : "這項已走完目前整理的步驟",
  };
  const nextList = [...items];
  nextList[index] = updated;
  writeJson(window.localStorage, TRACKED_KEY, nextList);
  return updated;
}

/** 從本機已追蹤清單移除單一項目。 */
export function removeTrackedBenefitItem(itemId: string): void {
  if (!canUseStorage()) {
    return;
  }
  const remaining = listTrackedBenefitItems().filter(
    (item) => item.itemId !== itemId,
  );
  writeJson(window.localStorage, TRACKED_KEY, remaining);
}

/** 清空本機全部已追蹤項目（不影響本輪待追蹤）。 */
export function clearTrackedBenefitItems(): void {
  if (!canUseStorage()) {
    return;
  }
  writeJson(window.localStorage, TRACKED_KEY, []);
}

export function listPendingBenefitItems(): PendingBenefitItem[] {
  if (!canUseStorage()) {
    return [];
  }
  return readJson<PendingBenefitItem[]>(window.sessionStorage, PENDING_KEY, []);
}

/**
 * 用本輪結果清單覆寫「待追蹤」（已加入追蹤的項目會被濾掉）。
 */
export function syncPendingBenefitItemsFromResults(
  items: ItemView[],
  lifeEventId: string | null,
): void {
  if (!canUseStorage()) {
    return;
  }
  const eventId = lifeEventId ?? "unknown";
  const trackedIds = new Set(
    listTrackedBenefitItems().map((item) => item.itemId),
  );
  const pending: PendingBenefitItem[] = items
    .filter((item) => !trackedIds.has(item.itemId))
    .map((item) => {
      const detail = getItemDetail(item.itemId);
      return {
        itemId: item.itemId,
        name: itemName(item.itemId),
        categoryLabel: itemCategoryLabel(item.itemId, item.kind),
        lifeEventId: eventId,
        lifeEventLabel: lifeEventName(eventId),
        agency: detail?.agency,
      };
    });
  writeJson(window.sessionStorage, PENDING_KEY, pending);
}

export function buildTrackedItemFromResult(
  item: ItemView,
  lifeEventId: string | null,
): Omit<TrackedBenefitItem, "addedAt"> {
  const eventId = lifeEventId ?? "unknown";
  const detail = getItemDetail(item.itemId);
  const flowSteps = buildFlowStepsForItem(item.itemId);
  return {
    itemId: item.itemId,
    name: itemName(item.itemId),
    categoryLabel: itemCategoryLabel(item.itemId, item.kind),
    lifeEventId: eventId,
    lifeEventLabel: lifeEventName(eventId),
    agency: detail?.agency,
    nextAction: flowSteps[0]
      ? `下一步：${flowSteps[0].label}`
      : "回來看辦理進度與應備文件",
    flowSteps,
    completedStepCount: 0,
  };
}
