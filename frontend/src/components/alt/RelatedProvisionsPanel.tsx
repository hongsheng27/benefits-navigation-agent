import { getProvisionsForLifeEvent } from "../../mocks/relatedProvisions";
import type { CopilotContext } from "../../types/postConsult";
import { lifeEventName } from "./copy";
import { PostConsultPanel } from "./PostConsultPanel";

type RelatedProvisionsPanelProps = {
  lifeEventId: string | null;
  onClose: () => void;
};

export function RelatedProvisionsPanel({
  lifeEventId,
  onClose,
}: RelatedProvisionsPanelProps) {
  const provisions = getProvisionsForLifeEvent(lifeEventId);
  const lifeEventLabel = lifeEventId
    ? lifeEventName(lifeEventId)
    : "目前情況";

  const context: CopilotContext = {
    kind: "related_provisions",
    lifeEventId,
    lifeEventLabel,
    provisionTitles: provisions.map((item) => item.title),
    guideTitle: null,
  };

  return (
    <PostConsultPanel
      kind="related_provisions"
      title="相關法條與官方依據"
      subtitle="以下摘錄來自官方網頁候選資料，先幫你對照可能相關的條件與說明。"
      context={context}
      onClose={onClose}
    >
      <p className="rounded-sm border border-[#e2d3b5] bg-[#f8f3ea] px-3 py-2.5 text-[0.82rem] leading-[1.75] text-[#5c564e]">
        這些是 discovery 抽出的候選摘錄，不是已人工核對的全國法規條號。實際申請請以各機關最新公告為準。
      </p>

      <ul className="mt-5 space-y-5">
        {provisions.map((provision) => (
          <li
            key={provision.provisionId}
            className="border-b border-[#e0d8ca] pb-5 last:border-b-0 last:pb-0"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-[1rem] font-semibold text-[#171513]">
                {provision.title}
              </h3>
              <span className="text-[0.75rem] tracking-[0.04em] text-[#8b8377]">
                候選摘錄
              </span>
            </div>
            <p className="mt-1 text-[0.84rem] text-[#5c564e]">
              {provision.lawName}
              {provision.articleLabel ? ` · ${provision.articleLabel}` : ""}
            </p>
            <p className="mt-1 text-[0.82rem] text-[#6b6459]">
              {provision.publisherName}
            </p>

            <div className="mt-3 rounded-sm bg-[#f1f4f0] px-3 py-3">
              <p className="text-[0.78rem] font-semibold tracking-[0.04em] text-[#2f4f45]">
                白話摘要
              </p>
              <p className="mt-1.5 text-[0.88rem] leading-[1.85] text-[#3a352e]">
                {provision.plainLanguageSummary}
              </p>
            </div>

            <div className="mt-3">
              <p className="text-[0.78rem] font-semibold tracking-[0.04em] text-[#8b8377]">
                原文摘錄
              </p>
              <p className="mt-1.5 whitespace-pre-wrap text-[0.86rem] leading-[1.85] text-[#4a453d]">
                {provision.excerpt}
              </p>
            </div>

            <a
              href={provision.sourceUrl}
              target="_blank"
              rel="noreferrer"
              className="mt-3 inline-block text-[0.86rem] font-semibold text-[#2f4f45] underline-offset-4 hover:underline"
            >
              開啟官方來源
            </a>
          </li>
        ))}
      </ul>
    </PostConsultPanel>
  );
}
