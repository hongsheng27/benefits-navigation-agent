import type { ItemStatus, ItemView, SessionSnapshot } from "../../types/session";
import styles from "./alt.module.css";
import {
  fieldLabel,
  itemKindLabel,
  itemName,
  optionLabel,
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

type ResultListProps = {
  snapshot: SessionSnapshot;
};

/**
 * 依 status 分區顯示候選項目。
 *
 * 每個項目各自帶一個 status，所以同時有好幾項符合是正常情況。後端目前的資料一律回
 * needs_human_review，所以「你可能符合」分區短期內會是空的 —— 那是刻意的安全預設，
 * 不是前端的問題。
 */
export function ResultList({ snapshot }: ResultListProps) {
  const { items, implementation } = snapshot;

  const grouped = STATUS_ORDER.map((status) => ({
    status,
    items: items.filter((item) => item.status === status),
  })).filter((group) => group.items.length > 0);

  return (
    <div>
      {implementation.isMock ? (
        <p className="border-l-2 border-[#8a5a1a] bg-[#f6f1e6] px-4 py-3.5 text-[0.85rem] leading-[2] text-[#4a453d] sm:px-5">
          {implementation.placeholderNotice}
        </p>
      ) : null}

      {grouped.length === 0 ? (
        <p className="mt-4 border border-dashed border-[#d8cfc0] bg-[#f7f4ee] px-4 py-6 text-[0.88rem] leading-[2] text-[#6b6459]">
          後端還沒有回傳任何候選項目。
        </p>
      ) : (
        grouped.map((group) => (
          <section key={group.status} className="mt-6">
            <h3
              className={`${styles.serif} text-[1.05rem] leading-[1.7] text-[#171513]`}
            >
              {statusSectionTitle(group.status)}
              <span className="ml-2 text-[0.8rem] tracking-[0.08em] text-[#6b6459]">
                {group.items.length} 項
              </span>
            </h3>
            <ul className="mt-3 divide-y divide-[#eee7db] border border-[#e0d8ca] bg-[#fdfbf7]">
              {group.items.map((item) => (
                <ResultRow item={item} key={item.itemId} />
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  );
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
