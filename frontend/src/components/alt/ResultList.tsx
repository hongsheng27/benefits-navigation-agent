import { useEffect, useState, type ReactNode } from "react";

import {
  addTrackedBenefitItem,
  buildTrackedItemFromResult,
  isBenefitItemTracked,
  syncPendingBenefitItemsFromResults,
} from "../../lib/trackingStore";
import { getItemDetail } from "../../mocks/itemDetails";
import type { ItemStatus, ItemView, SessionSnapshot } from "../../types/session";
import styles from "./alt.module.css";
import {
  fieldLabel,
  itemAudience,
  itemCategoryLabel,
  itemFallbackExplanation,
  itemName,
  lifeEventName,
  optionLabel,
  type ResultAudience,
  resultAudienceDescription,
  resultAudienceTitle,
  statusSectionTitle,
} from "./copy";

/** 分區顯示順序：能辦的放前面，辦不了的放後面。 */
const STATUS_ORDER: ItemStatus[] = [
  "eligible",
  "needs_information",
  "needs_human_review",
  "pending",
  "ineligible",
  "declined_by_user",
];

const AUDIENCE_ORDER: ResultAudience[] = ["care_recipient", "caregiver"];

type ResultListProps = {
  snapshot: SessionSnapshot;
  /** 示範用：依被照顧者／照顧者分組（不改 API）。 */
  groupByAudience?: boolean;
  /** 顯示「加入追蹤」並同步本輪待追蹤清單。 */
  enableItemTracking?: boolean;
  onGoToTracking?: (lifeEventId: string | null) => void;
};

/**
 * 結果清單分組優先序：
 * 1. `groupByAudience`（示範雙軌照顧）
 * 2. 多個 `lifeEvents`／`sourceLifeEvents`（正式多事件聯集）
 * 3. 僅依 status
 */
export function ResultList({
  snapshot,
  groupByAudience = false,
  enableItemTracking = true,
  onGoToTracking,
}: ResultListProps) {
  const { items, implementation, lifeEvents, lifeEvent } = snapshot;
  const primaryLifeEvent = lifeEvent ?? (lifeEvents.length > 0 ? lifeEvents[0] : null);

  useEffect(() => {
    if (!enableItemTracking || items.length === 0) {
      return;
    }
    syncPendingBenefitItemsFromResults(items, primaryLifeEvent);
  }, [enableItemTracking, items, primaryLifeEvent]);

  const audienceGroups = groupByAudience
    ? AUDIENCE_ORDER.map((audience) => ({
        audience,
        items: items.filter((item) => itemAudience(item.itemId) === audience),
      })).filter((group) => group.items.length > 0)
    : [];
  const ungroupedItems = groupByAudience
    ? items.filter((item) => itemAudience(item.itemId) === null)
    : items;
  const hasAudienceGroups = audienceGroups.length > 0;

  const eventOrder =
    lifeEvents.length > 0
      ? lifeEvents
      : [...new Set(items.flatMap((item) => item.sourceLifeEvents ?? []))];
  const splitByEvent = !hasAudienceGroups && eventOrder.length > 1;
  const eventBuckets = splitByEvent
    ? eventOrder
        .map((eventId) => ({
          eventId,
          items: items.filter((item) =>
            (item.sourceLifeEvents ?? []).includes(eventId),
          ),
        }))
        .filter((bucket) => bucket.items.length > 0)
    : [{ eventId: null as string | null, items }];

  return (
    <div>
      {implementation.isMock ? (
        <p className="border-l-2 border-[#8a5a1a] bg-[#f6f1e6] px-4 py-3.5 text-[0.88rem] leading-[2] text-[#4a453d] sm:px-5">
          下面先用示範資料帶你看一輪流程；實際送件前，還是以承辦單位的說明為準。
        </p>
      ) : null}

      {items.length === 0 ? (
        <p className="mt-5 border border-dashed border-[#d8cfc0] bg-[#f7f4ee] px-4 py-6 text-[0.92rem] leading-[2] text-[#6b6459]">
          這一輪還沒對上可辦的項目。若你願意，可以重新開始，或換個說法再說一次我們一起找。
        </p>
      ) : hasAudienceGroups ? (
        <div>
          {audienceGroups.map((group) => (
            <section className="mt-10 first:mt-0" key={group.audience}>
              <h3
                className={`${styles.serif} text-[1.18rem] leading-[1.7] text-[#2f4f45]`}
              >
                {resultAudienceTitle(group.audience)}
              </h3>
              <p className="mt-2 text-[0.9rem] leading-[2] text-[#6b6459]">
                {resultAudienceDescription(group.audience)}
              </p>
              <StatusGroups
                items={group.items}
                nested
                lifeEventId={primaryLifeEvent}
                enableItemTracking={enableItemTracking}
                onGoToTracking={onGoToTracking}
              />
            </section>
          ))}

          {ungroupedItems.length > 0 ? (
            <section className="mt-10">
              <h3
                className={`${styles.serif} text-[1.18rem] leading-[1.7] text-[#2f4f45]`}
              >
                其他也值得看一眼的方向
              </h3>
              <StatusGroups
                items={ungroupedItems}
                nested
                lifeEventId={primaryLifeEvent}
                enableItemTracking={enableItemTracking}
                onGoToTracking={onGoToTracking}
              />
            </section>
          ) : null}
        </div>
      ) : (
        eventBuckets.map((bucket) => (
          <div key={bucket.eventId ?? "all"} className="mt-8 first:mt-0">
            {bucket.eventId ? (
              <h2 className="text-[0.95rem] font-semibold leading-[1.8] tracking-[0.04em] text-[#2f4f45]">
                與「{lifeEventName(bucket.eventId)}」有關的部分
              </h2>
            ) : null}
            <StatusGroups
              items={bucket.items}
              lifeEventId={bucket.eventId ?? primaryLifeEvent}
              enableItemTracking={enableItemTracking}
              onGoToTracking={onGoToTracking}
            />
          </div>
        ))
      )}
    </div>
  );
}

function StatusGroups({
  items,
  nested = false,
  lifeEventId,
  enableItemTracking,
  onGoToTracking,
}: {
  items: ItemView[];
  nested?: boolean;
  lifeEventId: string | null;
  enableItemTracking: boolean;
  onGoToTracking?: (lifeEventId: string | null) => void;
}) {
  const grouped = STATUS_ORDER.map((status) => ({
    status,
    items: items.filter((item) => item.status === status),
  })).filter((group) => group.items.length > 0);
  const Heading = nested ? "h4" : "h3";

  return grouped.map((group) => (
    <section key={group.status} className={nested ? "mt-6" : "mt-8"}>
      <Heading
        className={`${styles.serif} text-[1.05rem] leading-[1.8] text-[#171513]`}
      >
        {statusSectionTitle(group.status)}
        <span className="ml-2 text-[0.8rem] tracking-[0.08em] text-[#6b6459]">
          {group.items.length} 項
        </span>
      </Heading>
      <ul className="mt-3 divide-y divide-[#eee7db] border border-[#e0d8ca] bg-[#fdfbf7]">
        {group.items.map((item) => (
          <ResultRow
            item={item}
            key={item.itemId}
            lifeEventId={lifeEventId}
            enableItemTracking={enableItemTracking}
            onGoToTracking={onGoToTracking}
          />
        ))}
      </ul>
    </section>
  ));
}

function formatAmountFromItem(item: ItemView): string | null {
  if (item.amountMin == null && item.amountMax == null) {
    return null;
  }
  const currency = item.amountCurrency?.trim() || "元";
  const period =
    item.amountPeriod === "monthly"
      ? "／月"
      : item.amountPeriod === "annual"
        ? "／年"
        : item.amountPeriod === "one_time"
          ? "（一次）"
          : "";
  if (item.amountMin != null && item.amountMax != null) {
    if (item.amountMin === item.amountMax) {
      return `${item.amountMin.toLocaleString("zh-TW")} ${currency}${period}`;
    }
    return `${item.amountMin.toLocaleString("zh-TW")}–${item.amountMax.toLocaleString("zh-TW")} ${currency}${period}`;
  }
  if (item.amountMin != null) {
    return `約 ${item.amountMin.toLocaleString("zh-TW")} ${currency}起${period}`;
  }
  return `最高約 ${item.amountMax!.toLocaleString("zh-TW")} ${currency}${period}`;
}

function DetailSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mt-3">
      <h4 className="text-[0.82rem] font-semibold tracking-[0.04em] text-[#2f4f45]">
        {title}
      </h4>
      <div className="mt-1 text-[0.85rem] leading-[1.95] text-[#4a453d]">
        {children}
      </div>
    </div>
  );
}

function ResultRow({
  item,
  lifeEventId,
  enableItemTracking,
  onGoToTracking,
}: {
  item: ItemView;
  lifeEventId: string | null;
  enableItemTracking: boolean;
  onGoToTracking?: (lifeEventId: string | null) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [tracked, setTracked] = useState(() => isBenefitItemTracked(item.itemId));
  const detail = getItemDetail(item.itemId);
  const amountLabel = formatAmountFromItem(item) ?? detail?.amountLabel ?? null;
  const officialUrl = detail?.officialUrl ?? item.citations[0]?.url ?? null;
  const explanation =
    item.explanation ?? item.summary ?? itemFallbackExplanation(item.itemId);

  function handleAddTracking() {
    addTrackedBenefitItem(buildTrackedItemFromResult(item, lifeEventId));
    setTracked(true);
  }
  return (
    <li className="px-4 py-4 sm:px-5">
      <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[0.98rem] leading-[1.8] font-semibold text-[#171513]">
          {item.displayName ?? itemName(item.itemId)}
        </span>
        <span className="rounded-xs border border-[#d8cfc0] px-2 py-0.5 text-[0.75rem] leading-[1.8] tracking-[0.06em] text-[#6b6459]">
          項目類型：{itemCategoryLabel(item.itemId, item.kind)}
        </span>
      </p>

      {explanation ? (
        <p className="mt-2 text-[0.88rem] leading-[2] text-[#4a453d]">{explanation}</p>
      ) : null}

      {item.missingFieldIds.length > 0 ? (
        <p className="mt-2 text-[0.85rem] leading-[2] text-[#6b6459]">
          還需要確認：
          {item.missingFieldIds.map((fieldId) => fieldLabel(fieldId)).join("、")}
        </p>
      ) : null}

      {item.decisiveConditions.length > 0 ? (
        <dl className="mt-2 flex flex-col gap-1 text-[0.85rem] leading-[2] text-[#6b6459]">
          {item.decisiveConditions.map((condition) => (
            <div className="flex flex-wrap gap-x-2" key={condition.fieldId}>
              <dt>差在這個條件：{fieldLabel(condition.fieldId)}</dt>
              <dd>
                你的情況 {formatConditionValue(condition.actual)} ／ 需要{" "}
                {formatConditionValue(condition.expected)}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}

      {item.citations.length > 0 ? (
        <ul className="mt-2 flex flex-col gap-1">
          {item.citations.map((citation) => (
            <li key={citation.documentId} className="text-[0.82rem] leading-[1.9]">
              <a
                href={citation.url}
                rel="noreferrer noopener"
                target="_blank"
                className="text-[#2f4f45] underline decoration-[#a8bdb2] underline-offset-2 hover:decoration-[#2f4f45]"
              >
                {citation.title}
              </a>
              <span className="ml-2 text-[#6b6459]">{citation.publisherName}</span>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <button
          type="button"
          onClick={() => setExpanded((current) => !current)}
          className="text-[0.85rem] font-semibold tracking-[0.04em] text-[#2f4f45] underline decoration-[#a8bdb2] underline-offset-2 hover:decoration-[#2f4f45]"
          aria-expanded={expanded}
        >
          {expanded ? "收合詳情" : "查看詳情"}
        </button>
        {enableItemTracking ? (
          tracked ? (
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.85rem] text-[#6b6459]">
              <span>已加入追蹤</span>
              {onGoToTracking ? (
                <button
                  type="button"
                  onClick={() => onGoToTracking(lifeEventId)}
                  className="font-semibold text-[#2f4f45] underline decoration-[#a8bdb2] underline-offset-2 hover:decoration-[#2f4f45]"
                >
                  查看追蹤
                </button>
              ) : null}
            </span>
          ) : (
            <button
              type="button"
              onClick={handleAddTracking}
              className="rounded-sm border border-[#2f4f45] bg-transparent px-3 py-1.5 text-[0.82rem] font-semibold tracking-[0.04em] text-[#2f4f45] transition-colors hover:bg-[#2f4f45] hover:text-[#f7f4ee]"
            >
              加入追蹤
            </button>
          )
        ) : null}
      </div>

      {expanded ? (
        <div className="mt-3 border-t border-[#eee7db] pt-3">
          {detail ? (
            <>
              <DetailSection title="完整說明">{detail.summary}</DetailSection>
              <DetailSection title="主管機關">{detail.agency}</DetailSection>
              <DetailSection title="申請地點">{detail.location}</DetailSection>
              {amountLabel ? (
                <DetailSection title="金額範圍">{amountLabel}</DetailSection>
              ) : null}
              <DetailSection title="資格條件">
                <ul className="list-disc pl-5">
                  {detail.eligibilityNotes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </DetailSection>
              <DetailSection title="申請步驟">
                <ol className="list-decimal pl-5">
                  {detail.steps.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
              </DetailSection>
              <DetailSection title="應備文件">
                <ul className="list-disc pl-5">
                  {detail.documents.map((doc) => (
                    <li key={doc}>{doc}</li>
                  ))}
                </ul>
              </DetailSection>
            </>
          ) : (
            <p className="text-[0.85rem] leading-[1.95] text-[#6b6459]">
              這筆項目的示範詳情尚未補齊；正式申請仍以承辦機關說明為準。
            </p>
          )}
          {officialUrl ? (
            <p className="mt-3">
              <a
                href={officialUrl}
                rel="noreferrer noopener"
                target="_blank"
                className="text-[0.85rem] font-semibold text-[#2f4f45] underline decoration-[#a8bdb2] underline-offset-2 hover:decoration-[#2f4f45]"
              >
                前往機關／官方頁面
              </a>
            </p>
          ) : null}
          <p className="mt-3 text-[0.78rem] leading-[1.8] text-[#8b8377]">
            以上為整理用示範說明，不代表資格已核定。
          </p>
        </div>
      ) : null}
    </li>
  );
}

/** 條件的值可能是代號、布林或數字，顯示時要各自處理。 */
function formatConditionValue(value: boolean | number | string): string {
  if (typeof value === "boolean") {
    return value ? "是" : "否";
  }
  if (typeof value === "number") {
    return String(value);
  }
  return optionLabel(value);
}
