/**
 * 本機追蹤暫存：已追蹤項目（localStorage）＋本輪諮詢待追蹤（sessionStorage）。
 * 後端尚無 POST /cases 前供結果頁／追蹤頁共用。
 */

import type { ItemView } from "../types/session";
import type { TrackedBenefitItem } from "../types/tracking";
import { itemCategoryLabel, itemName, lifeEventName } from "../components/alt/copy";
import { getItemDetail } from "../mocks/itemDetails";

const TRACKED_KEY = "jiezhu.trackedBenefitItems.v1";
const PENDING_KEY = "jiezhu.pendingBenefitItems.v1";

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

export function listTrackedBenefitItems(): TrackedBenefitItem[] {
  if (!canUseStorage()) {
    return [];
  }
  const items = readJson<TrackedBenefitItem[]>(window.localStorage, TRACKED_KEY, []);
  return [...items].sort((a, b) => (a.addedAt < b.addedAt ? 1 : -1));
}

export function isBenefitItemTracked(itemId: string): boolean {
  return listTrackedBenefitItems().some((item) => item.itemId === itemId);
}

export function addTrackedBenefitItem(
  input: Omit<TrackedBenefitItem, "addedAt"> & { addedAt?: string },
): TrackedBenefitItem {
  const next: TrackedBenefitItem = {
    ...input,
    addedAt: input.addedAt ?? new Date().toISOString(),
  };
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
  return {
    itemId: item.itemId,
    name: itemName(item.itemId),
    categoryLabel: itemCategoryLabel(item.itemId, item.kind),
    lifeEventId: eventId,
    lifeEventLabel: lifeEventName(eventId),
    agency: detail?.agency,
    nextAction: detail?.steps[0]
      ? `下一步：${detail.steps[0]}`
      : "回來看辦理進度與應備文件",
  };
}
