import { ELIGIBILITY_QUESTIONS } from "../../mocks/eligibilityQuestions";
import { BENEFIT_ITEMS } from "../../mocks/benefitCatalog";
import type {
  BenefitItem,
  EligibilityQuestion,
  ProfileState,
} from "../../types/navigator";
import { BenefitCard } from "./BenefitCard";
import { IneligibleItemCard } from "./IneligibleItemCard";
import { MoneySummary } from "./MoneySummary";
import { readiness, totals, verdict } from "./benefitEngine";
import { findProfileField, useNavigator } from "./NavigatorContext";

function getPrefillValue(
  question: EligibilityQuestion,
  profile: ProfileState,
  mydataAuthorized: boolean,
): string | null {
  if (question.profileField) {
    const value = findProfileField(profile, question.profileField)?.value;
    if (value) {
      return value;
    }
  }
  if (question.mydataPrefill && mydataAuthorized) {
    return "15 年以上";
  }
  return null;
}

function groupByVerdict(items: BenefitItem[], answers: Record<string, string>) {
  const groups: { ok: BenefitItem[]; info: BenefitItem[]; no: BenefitItem[] } = {
    ok: [],
    info: [],
    no: [],
  };
  items.forEach((item) => {
    const v = verdict(item, answers);
    const key = v === "pending" ? "info" : v;
    groups[key].push(item);
  });
  return groups;
}

export function MatchScreen() {
  const {
    state,
    answerQuestion,
    skipQuestion,
    undoLastAnswer,
    resetAnswers,
    authorizeMyData,
    openDetail,
    toggleShowIneligible,
  } = useNavigator();

  const { answers, profile, mydata, showIneligible } = state;
  const answeredCount = Object.keys(answers).length;
  const nextQuestion = ELIGIBILITY_QUESTIONS.find((q) => !answers[q.code]) ?? null;
  const benefitTotals = totals(BENEFIT_ITEMS, answers, mydata.authorized);
  const groups = groupByVerdict(BENEFIT_ITEMS, answers);

  let totalDocs = 0;
  let readyDocs = 0;
  BENEFIT_ITEMS.forEach((item) => {
    const r = readiness(item, answers, mydata.authorized);
    totalDocs += r.total;
    readyDocs += r.got;
  });
  const overallPercent = totalDocs ? Math.round((readyDocs / totalDocs) * 100) : 0;
  const okCount = groups.ok.length;

  return (
    <div className="space-y-6">
      {nextQuestion ? (
        <>
          <QuestionCard
            answeredCount={answeredCount}
            onAnswer={(value) => answerQuestion(nextQuestion.code, value)}
            onSkip={() => skipQuestion(nextQuestion.code)}
            onUndo={undoLastAnswer}
            prefill={getPrefillValue(nextQuestion, profile, mydata.authorized)}
            question={nextQuestion}
            total={ELIGIBILITY_QUESTIONS.length}
          />
          <MoneySummary totals={benefitTotals} variant="compact" />
        </>
      ) : (
        <>
          <MoneySummary totals={benefitTotals} variant="full" />
          <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-[#e6f2ef] px-6 py-5">
            <div>
              <p className="text-sm font-bold text-[#153f3b]">問題都回答完了</p>
              <p className="mt-1 text-xs text-[#27756c]">
                下方是依你的情況評估的結果與文件備妥率，想調整答案可以按右邊的按鈕。
              </p>
            </div>
            <div className="flex gap-2">
              <button
                className="rounded-xl border border-[#c3e2d9] bg-white px-4 py-2 text-sm font-bold text-[#27756c] transition hover:bg-[#f0faf7]"
                onClick={resetAnswers}
                type="button"
              >
                重新回答問題
              </button>
              {!mydata.authorized && (
                <button
                  className="rounded-xl bg-[#54479c] px-4 py-2 text-sm font-bold text-white transition hover:bg-[#463b85]"
                  onClick={authorizeMyData}
                  type="button"
                >
                  🔐 授權 MyData 提高備妥率
                </button>
              )}
            </div>
          </div>
        </>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="可能相關的項目" value={String(BENEFIT_ITEMS.length)} />
        <Stat
          label="目前判定符合"
          value={String(okCount)}
          valueClassName="text-[#27756c]"
        />
        <Stat
          label="已回答問題"
          value={`${answeredCount} / ${ELIGIBILITY_QUESTIONS.length}`}
        />
        <Stat
          label="整體文件備妥率"
          value={`${overallPercent}%`}
          valueClassName={overallPercent >= 66 ? "text-[#27756c]" : "text-[#96660f]"}
        />
      </div>

      {groups.ok.length > 0 && (
        <section>
          <h3 className="mb-3 text-base font-bold text-slate-900">
            你可能符合{" "}
            <span className="ml-1 rounded-full bg-[#e6f2ef] px-2 py-0.5 text-xs text-[#27756c]">
              {groups.ok.length} 項
            </span>
          </h3>
          <div className="grid gap-4 sm:grid-cols-2">
            {groups.ok.map((item) => (
              <BenefitCard
                answers={answers}
                item={item}
                key={item.id}
                mydataAuthorized={mydata.authorized}
                onOpen={openDetail}
                questions={ELIGIBILITY_QUESTIONS}
              />
            ))}
          </div>
        </section>
      )}

      {groups.info.length > 0 && (
        <section>
          <h3 className="mb-3 text-base font-bold text-slate-900">
            還需要補充資訊{" "}
            <span className="ml-1 rounded-full bg-[#eaf0f5] px-2 py-0.5 text-xs text-[#3f5b73]">
              {groups.info.length} 項
            </span>
          </h3>
          <div className="grid gap-4 sm:grid-cols-2">
            {groups.info.map((item) => (
              <BenefitCard
                answers={answers}
                item={item}
                key={item.id}
                mydataAuthorized={mydata.authorized}
                onOpen={openDetail}
                questions={ELIGIBILITY_QUESTIONS}
              />
            ))}
          </div>
        </section>
      )}

      {groups.no.length > 0 && (
        <section className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-6 py-5">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-base font-bold text-slate-700">
              不符合資格{" "}
              <span className="ml-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
                {groups.no.length} 項
              </span>
            </h3>
            <button
              className="rounded-full border border-slate-300 px-3 py-1.5 text-xs font-bold text-slate-500 transition hover:border-[#74a9a3] hover:text-[#27756c]"
              onClick={toggleShowIneligible}
              type="button"
            >
              {showIneligible ? "收合 ▴" : "展開看原因 ▾"}
            </button>
          </div>
          <p className="mb-4 text-xs leading-6 text-slate-400">
            這些項目經判定不符合，
            <strong className="text-slate-500">你不需要為它們準備文件或跑一趟</strong>
            。每一項都會說明差在哪個條件。
          </p>
          {showIneligible ? (
            <div className="grid gap-3 sm:grid-cols-2">
              {groups.no.map((item) => (
                <IneligibleItemCard answers={answers} item={item} key={item.id} />
              ))}
            </div>
          ) : (
            <div className="space-y-2">
              {groups.no.map((item) => (
                <IneligibleItemCard
                  answers={answers}
                  compact
                  item={item}
                  key={item.id}
                />
              ))}
            </div>
          )}
        </section>
      )}

      <p className="text-xs leading-6 text-slate-400">
        ℹ️ 備妥率會隨你回答的問題與 MyData 授權狀態即時變動。接住不受理申請、
        不代為送件，實際應備文件請以承辦單位要求為準。
      </p>
    </div>
  );
}

type StatProps = {
  label: string;
  value: string;
  valueClassName?: string;
};

function Stat({ label, value, valueClassName }: StatProps) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className={`text-xl font-bold ${valueClassName ?? "text-slate-900"}`}>
        {value}
      </p>
      <p className="text-xs text-slate-400">{label}</p>
    </div>
  );
}

type QuestionCardProps = {
  question: EligibilityQuestion;
  prefill: string | null;
  answeredCount: number;
  total: number;
  onAnswer: (value: string) => void;
  onSkip: () => void;
  onUndo: () => void;
};

function QuestionCard({
  question,
  prefill,
  answeredCount,
  total,
  onAnswer,
  onSkip,
  onUndo,
}: QuestionCardProps) {
  const percent = Math.round((answeredCount / total) * 100);
  const otherOptions = question.options.filter((option) => option !== prefill);

  return (
    <div className="rounded-3xl border-2 border-[#0d7360] bg-white p-7 shadow-md">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-bold text-[#0d7360]">✎ 回答問題來完成評估</p>
          <p className="mt-1 text-xs text-slate-400">
            每回答一題，下方的判定結果、可領金額與文件備妥率都會即時更新。
          </p>
        </div>
        <span className="text-2xl font-bold text-[#0d7360]">
          {answeredCount + 1}{" "}
          <small className="text-sm font-medium text-slate-400">/ {total}</small>
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-[#0d7360]"
          style={{ width: `${percent}%` }}
        />
      </div>
      <p className="my-5 text-2xl font-bold leading-snug text-slate-900">
        {question.prompt}
      </p>
      <div className="flex flex-wrap gap-3">
        {prefill && (
          <button
            aria-label={prefill}
            className="flex flex-col items-start rounded-xl border-2 border-[#54479c] bg-[#eeecf8] px-5 py-3.5 text-base font-bold text-[#54479c] transition hover:-translate-y-0.5"
            onClick={() => onAnswer(prefill)}
            type="button"
          >
            {prefill}
            <small className="text-xs font-medium opacity-80">來自我的資料</small>
          </button>
        )}
        {otherOptions.map((option) => (
          <button
            className="rounded-xl border border-slate-200 bg-slate-50 px-5 py-3.5 text-base transition hover:-translate-y-0.5 hover:border-[#0d7360] hover:bg-[#e6f2ef]"
            key={option}
            onClick={() => onAnswer(option)}
            type="button"
          >
            {option}
          </button>
        ))}
      </div>
      <p className="mt-4 rounded-lg bg-slate-50 px-4 py-3 text-xs leading-6 text-slate-500">
        為什麼問這個：{question.why}
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        {answeredCount > 0 && (
          <button
            className="rounded-full border border-slate-300 px-3 py-1.5 text-xs font-bold text-slate-500 transition hover:border-[#74a9a3] hover:text-[#27756c]"
            onClick={onUndo}
            type="button"
          >
            ← 回上一題
          </button>
        )}
        <button
          className="rounded-full border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-500 transition hover:border-[#74a9a3] hover:text-[#27756c]"
          onClick={onSkip}
          type="button"
        >
          先跳過這題
        </button>
        <span className="text-xs text-slate-400">
          還有 {total - answeredCount} 題就完成
        </span>
      </div>
    </div>
  );
}
