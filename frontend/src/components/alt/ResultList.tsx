import type { ItemStatus, ItemView, SessionSnapshot } from "../../types/session";
import styles from "./alt.module.css";
import {
  fieldLabel,
  itemAudience,
  itemKindLabel,
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
}: ResultListProps) {
  const { items, implementation, lifeEvents } = snapshot;

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
        <p className="border-l-2 border-[#8a5a1a] bg-[#f6f1e6] px-4 py-3.5 text-[0.85rem] leading-[2] text-[#4a453d] sm:px-5">
          目前結果仍是示範資料，請先當作參考；送件前仍以承辦單位說明為準。
        </p>
      ) : null}

      {items.length === 0 ? (
        <p className="mt-4 border border-dashed border-[#d8cfc0] bg-[#f7f4ee] px-4 py-6 text-[0.88rem] leading-[2] text-[#6b6459]">
          目前還沒有整理出可辦的項目。你可以重新開始，或改用其他說法再試一次。
        </p>
      ) : hasAudienceGroups ? (
        <div>
          {audienceGroups.map((group) => (
            <section className="mt-8" key={group.audience}>
              <h3
                className={`${styles.serif} text-[1.18rem] leading-[1.7] text-[#2f4f45]`}
              >
                {resultAudienceTitle(group.audience)}
              </h3>
              <p className="mt-1 text-[0.88rem] leading-[1.9] text-[#6b6459]">
                {resultAudienceDescription(group.audience)}
              </p>
              <StatusGroups items={group.items} nested />
            </section>
          ))}

          {ungroupedItems.length > 0 ? (
            <section className="mt-8">
              <h3
                className={`${styles.serif} text-[1.18rem] leading-[1.7] text-[#2f4f45]`}
              >
                其他相關方向
              </h3>
              <StatusGroups items={ungroupedItems} nested />
            </section>
          ) : null}
        </div>
      ) : (
        eventBuckets.map((bucket) => (
          <div key={bucket.eventId ?? "all"} className="mt-6 first:mt-0">
            {bucket.eventId ? (
              <h2 className="text-[0.95rem] font-semibold tracking-[0.04em] text-[#2f4f45]">
                與「{lifeEventName(bucket.eventId)}」相關
              </h2>
            ) : null}
            <StatusGroups items={bucket.items} />
          </div>
        ))
      )}
    </div>
  );
}

function StatusGroups({
  items,
  nested = false,
}: {
  items: ItemView[];
  nested?: boolean;
}) {
  const grouped = STATUS_ORDER.map((status) => ({
    status,
    items: items.filter((item) => item.status === status),
  })).filter((group) => group.items.length > 0);
  const Heading = nested ? "h4" : "h3";

  return grouped.map((group) => (
    <section key={group.status} className={nested ? "mt-5" : "mt-6"}>
      <Heading
        className={`${styles.serif} text-[1.05rem] leading-[1.7] text-[#171513]`}
      >
        {statusSectionTitle(group.status)}
        <span className="ml-2 text-[0.8rem] tracking-[0.08em] text-[#6b6459]">
          {group.items.length} 項
        </span>
      </Heading>
      <ul className="mt-3 divide-y divide-[#eee7db] border border-[#e0d8ca] bg-[#fdfbf7]">
        {group.items.map((item) => (
          <ResultRow item={item} key={item.itemId} />
        ))}
      </ul>
    </section>
  ));
}

function ResultRow({ item }: { item: ItemView }) {
  return (
    <li className="px-4 py-4 sm:px-5">
      <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[0.98rem] leading-[1.8] font-semibold text-[#171513]">
          {itemName(item.itemId)}
        </span>
        <span className="rounded-xs border border-[#d8cfc0] px-2 py-0.5 text-[0.75rem] leading-[1.8] tracking-[0.06em] text-[#6b6459]">
          {itemKindLabel(item.kind)}
        </span>
      </p>

      {item.explanation ? (
        <p className="mt-2 text-[0.88rem] leading-[2] text-[#4a453d]">
          {item.explanation}
        </p>
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
