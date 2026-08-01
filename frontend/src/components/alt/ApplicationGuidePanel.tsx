import { getApplicationGuide } from "../../mocks/applicationGuides";
import type { CopilotContext } from "../../types/postConsult";
import { lifeEventName } from "./copy";
import { PostConsultPanel } from "./PostConsultPanel";

type ApplicationGuidePanelProps = {
  lifeEventId: string | null;
  lifeEventIds?: string[];
  sessionId?: string | null;
  onClose: () => void;
};

export function ApplicationGuidePanel({
  lifeEventId,
  lifeEventIds = [],
  sessionId = null,
  onClose,
}: ApplicationGuidePanelProps) {
  const guide = getApplicationGuide(lifeEventId, lifeEventIds);
  const resolvedEventId =
    guide?.lifeEventId ?? lifeEventId ?? lifeEventIds[0] ?? null;
  const lifeEventLabel = resolvedEventId
    ? lifeEventName(resolvedEventId)
    : "目前情況";

  const context: CopilotContext = {
    kind: "application_guide",
    lifeEventId: resolvedEventId,
    lifeEventLabel,
    provisionTitles: [],
    guideTitle: guide?.title ?? null,
    references: guide
      ? [
          {
            title: guide.title,
            body: `${guide.overview}\n\n${guide.disclaimer}`,
          },
          ...guide.steps.map((step, index) => ({
            title: `步驟 ${index + 1}：${step.title}`,
            body: [
              step.description,
              step.agencyName ? `窗口：${step.agencyName}` : null,
              step.deadlineNote ? `期限：${step.deadlineNote}` : null,
              step.requiredDocuments.length > 0
                ? `應備文件：\n- ${step.requiredDocuments.join("\n- ")}`
                : null,
              step.tips.length > 0
                ? `提醒：\n- ${step.tips.join("\n- ")}`
                : null,
            ]
              .filter((line): line is string => line !== null)
              .join("\n"),
          })),
        ]
      : [],
  };

  return (
    <PostConsultPanel
      kind="application_guide"
      title="申請解說"
      subtitle={guide?.title ?? "這一輪還沒有對應的申請步驟說明"}
      context={context}
      sessionId={sessionId}
      onClose={onClose}
    >
      {!guide ? (
        <p className="rounded-sm border border-dashed border-[#d8cfc0] bg-[#f7f4ee] px-4 py-6 text-[0.92rem] leading-[2] text-[#6b6459]">
          這一輪結果還沒有對應的申請步驟說明。請先對照結果清單，或直接洽詢承辦單位；我們不會用其他情境（例如喪葬）的說明代替。
        </p>
      ) : (
        <>
          <p className="text-[0.92rem] leading-[1.9] text-[#4a453d]">
            {guide.overview}
          </p>
          <p className="mt-3 rounded-sm border border-[#e2d3b5] bg-[#f8f3ea] px-3 py-2.5 text-[0.82rem] leading-[1.75] text-[#5c564e]">
            {guide.disclaimer}
          </p>

          <ol className="mt-6 space-y-5">
            {guide.steps.map((step, index) => (
              <li
                key={step.stepId}
                className="border-b border-[#e0d8ca] pb-5 last:border-b-0 last:pb-0"
              >
                <div className="flex gap-3">
                  <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-[#f1f4f0] text-[0.78rem] font-semibold text-[#2f4f45]">
                    {index + 1}
                  </span>
                  <div className="min-w-0">
                    <h3 className="text-[1rem] font-semibold text-[#171513]">
                      {step.title}
                    </h3>
                    <p className="mt-1.5 text-[0.9rem] leading-[1.85] text-[#4a453d]">
                      {step.description}
                    </p>

                    {step.agencyName ? (
                      <p className="mt-2 text-[0.84rem] text-[#5c564e]">
                        受理／相關窗口：{step.agencyName}
                      </p>
                    ) : null}

                    {step.deadlineNote ? (
                      <p className="mt-1 text-[0.84rem] leading-[1.75] text-[#6b6459]">
                        期限提醒：{step.deadlineNote}
                      </p>
                    ) : null}

                    {step.requiredDocuments.length > 0 ? (
                      <div className="mt-3">
                        <p className="text-[0.78rem] font-semibold tracking-[0.04em] text-[#2f4f45]">
                          這一步常要準備
                        </p>
                        <ul className="mt-1.5 list-disc space-y-1 pl-5 text-[0.86rem] leading-[1.75] text-[#4a453d]">
                          {step.requiredDocuments.map((document) => (
                            <li key={document}>{document}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}

                    {step.tips.length > 0 ? (
                      <div className="mt-3 rounded-sm bg-[#f1f4f0] px-3 py-2.5">
                        <p className="text-[0.78rem] font-semibold tracking-[0.04em] text-[#2f4f45]">
                          小提醒
                        </p>
                        <ul className="mt-1.5 space-y-1 text-[0.84rem] leading-[1.75] text-[#3a352e]">
                          {step.tips.map((tip) => (
                            <li key={tip}>· {tip}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </>
      )}
    </PostConsultPanel>
  );
}
