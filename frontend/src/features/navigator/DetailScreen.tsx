import { APPLY_GUIDES, BENEFIT_ITEMS } from "../../mocks/benefitCatalog";
import { ELIGIBILITY_QUESTIONS } from "../../mocks/eligibilityQuestions";
import {
  estimate,
  formatMoney,
  getMissingRequirementCodes,
  isDocumentReady,
  readiness,
  resolveDocumentSource,
  verdict,
} from "./benefitEngine";
import { NotEligibleAndInfoPanel } from "./NotEligibleAndInfoPanel";
import { findProfileField, useNavigator } from "./NavigatorContext";

export function DetailScreen() {
  const { state, backToMatch, authorizeMyData, revealPlainExplanation, showToast } =
    useNavigator();
  const { answers, mydata, profile, explained, selectedItemId } = state;

  const item = BENEFIT_ITEMS.find((x) => x.id === selectedItemId);
  if (!item) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-6 text-center">
        <p className="text-sm text-slate-500">找不到這個項目。</p>
        <button
          className="mt-3 rounded-xl border border-slate-300 px-4 py-2 text-sm font-bold text-slate-600"
          onClick={backToMatch}
          type="button"
        >
          ← 回媒合結果
        </button>
      </div>
    );
  }

  const v = verdict(item, answers);
  const ready = readiness(item, answers, mydata.authorized);
  const est = estimate(item, answers, mydata.authorized);
  const guide = APPLY_GUIDES[item.id];
  const missingLabels = getMissingRequirementCodes(item, answers).map(
    (code) => ELIGIBILITY_QUESTIONS.find((q) => q.code === code)?.label ?? code,
  );
  const city = findProfileField(profile, "city")?.value;

  const autoDocs = item.documents.filter((d) => d.sourceType === "auto");
  const myDocs = item.documents.filter((d) => d.sourceType === "mydata");
  const selfDocs = item.documents.filter((d) => d.sourceType === "self");

  return (
    <div className="space-y-6">
      <button
        className="text-sm font-bold text-slate-500 transition hover:text-[#27756c]"
        onClick={backToMatch}
        type="button"
      >
        ← 回媒合結果
      </button>

      <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4 px-7 py-6">
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-[#27756c]">
              申請準備清單
            </p>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900">
              {item.name}
            </h1>
            <p className="mt-1 text-sm text-slate-400">{item.org}</p>
          </div>
          <span className="rounded-full bg-slate-100 px-3 py-1.5 text-sm font-bold text-slate-600">
            {v === "ok"
              ? "符合"
              : v === "info"
                ? "需補充資訊"
                : v === "no"
                  ? "不符合"
                  : "待確認"}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-px border-t border-slate-200 bg-slate-200 sm:grid-cols-4">
          <KeyMetric
            label="預估可領"
            value={est.ok ? formatMoney(est.amount) : "尚無法估算"}
            hint={est.ok ? (est.kind === "monthly" ? "／月" : "一次性") : undefined}
          />
          <KeyMetric
            label="文件備妥率"
            value={`${ready.percent}%`}
            hint={`${ready.got}／${ready.total} 項`}
          />
          <KeyMetric label="受理期間" value={item.deadline || "全年受理"} />
          <KeyMetric label="辦理方式" value={guide?.onlineNote || "—"} />
        </div>
        <div className="border-t border-slate-200 px-7 py-5">
          <h4 className="text-sm font-bold text-slate-900">這項補助是什麼</h4>
          <p className="mt-2 text-sm leading-7 text-slate-600">
            {guide?.fullDescription || "〈完整說明待官方文件確認後填入〉"}
          </p>
          <p className="mt-3 text-xs text-slate-400">
            說明來源：<span className="italic text-slate-300">{item.basis}</span>
          </p>
        </div>
        <div className="border-t border-slate-200 px-7 py-5">
          <h4 className="text-sm font-bold text-slate-900">主管機關與適用地區</h4>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <InfoBox
              label="主管機關"
              value={guide?.authority || item.org}
              hint={guide?.level}
            />
            <InfoBox
              label="適用地區"
              value={guide?.area || "—"}
              hint={city ? `你的戶籍地：${city}` : "尚未填寫戶籍地"}
            />
            <InfoBox label="辦理地點" value={item.location} hint={guide?.onlineNote} />
          </div>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
        <div className="space-y-6">
          <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h3 className="text-base font-bold text-slate-900">
              為什麼{v === "ok" ? "可能符合" : "還不能確認"}
            </h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">{item.reason}</p>
            {explained ? (
              <div className="mt-3 rounded-xl border border-[#c3e2d9] bg-[#e6f2ef] px-4 py-3">
                <p className="text-[11px] font-bold text-[#27756c]">白話說明</p>
                <p className="mt-1 text-sm leading-6 text-[#0b5a4b]">
                  {item.plainExplanation}
                </p>
              </div>
            ) : (
              <button
                className="mt-3 rounded-xl border border-slate-300 px-4 py-2 text-sm font-bold text-slate-600 transition hover:border-[#74a9a3] hover:text-[#27756c]"
                onClick={revealPlainExplanation}
                type="button"
              >
                用白話再說一次
              </button>
            )}
            {missingLabels.length > 0 && (
              <div className="mt-3 rounded-xl bg-[#eaf0f5] px-4 py-3">
                <p className="text-sm text-[#3f5b73]">
                  還需要確認：<strong>{missingLabels.join("、")}</strong>
                </p>
                <button
                  className="mt-2 rounded-lg bg-white px-3 py-1.5 text-xs font-bold text-[#3f5b73] shadow-sm"
                  onClick={backToMatch}
                  type="button"
                >
                  回去補答問題
                </button>
              </div>
            )}
            <p className="mt-3 text-xs text-slate-400">
              判定依據：<span className="italic text-slate-300">{item.basis}</span>
              {item.deadline && (
                <span className="ml-2 rounded-full bg-[#fbf1de] px-2 py-0.5 text-[11px] font-bold text-[#96660f]">
                  {item.deadline}
                </span>
              )}
            </p>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h3 className="text-base font-bold text-slate-900">
              完整申請步驟{" "}
              <span className="ml-1 rounded-full bg-[#eaf0f5] px-2 py-0.5 text-xs text-[#3f5b73]">
                共 {guide?.steps.length ?? 0} 步
              </span>
            </h3>
            <p className="mt-2 text-xs leading-6 text-slate-400">
              本站不代為送件，以下是你需要自行完成的流程。標示<strong>前置步驟</strong>
              的必須先完成，否則後面辦不下去。
            </p>
            <div className="mt-4 space-y-4">
              {(guide?.steps ?? []).map((step, index) => (
                <div className="flex gap-3" key={step.title}>
                  <span
                    className={`grid size-7 shrink-0 place-items-center rounded-full text-xs font-bold ${
                      step.isPrerequisite
                        ? "bg-[#fbf1de] text-[#96660f]"
                        : "bg-slate-100 text-slate-500"
                    }`}
                  >
                    {index + 1}
                  </span>
                  <div>
                    <p className="text-sm font-bold text-slate-900">
                      {step.title}
                      {step.isPrerequisite && (
                        <span className="ml-2 rounded-full bg-[#fbf1de] px-2 py-0.5 text-[11px] font-bold text-[#96660f]">
                          前置步驟
                        </span>
                      )}
                    </p>
                    <p className="mt-1 text-xs leading-6 text-slate-500">
                      {step.detail}
                    </p>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-4 flex justify-between border-t border-slate-100 pt-3 text-sm">
              <span className="text-slate-400">給付計算方式</span>
              <span className="font-bold text-slate-800">{item.amountLabel}</span>
            </div>
          </section>

          {guide && guide.links.length > 0 && (
            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="text-base font-bold text-slate-900">官方資料來源與連結</h3>
              <p className="mt-2 text-xs leading-6 text-slate-400">
                本頁所有說明都可以回到下列官方頁面核對。
              </p>
              <div className="mt-3 space-y-2">
                {guide.links.map((link) => (
                  <button
                    className="flex w-full items-center justify-between gap-3 rounded-xl border border-slate-200 px-4 py-3 text-left transition hover:border-[#74a9a3] hover:bg-[#f1f8f6]"
                    key={link.label}
                    onClick={() => showToast(`（示範）將開啟：${link.label}`)}
                    type="button"
                  >
                    <span className="text-sm font-bold text-[#27756c]">
                      {link.label}
                    </span>
                    <span className="text-xs text-slate-400">{link.note}</span>
                  </button>
                ))}
              </div>
            </section>
          )}
        </div>

        <div className="space-y-6">
          <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-base font-bold text-slate-900">應備文件</h3>
              <span
                className={`rounded-full px-2.5 py-1 text-xs font-bold ${
                  ready.percent >= 66
                    ? "bg-[#e6f2ef] text-[#27756c]"
                    : "bg-[#eaf0f5] text-[#3f5b73]"
                }`}
              >
                備妥 {ready.percent}%
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-400">
              共 {item.documents.length} 項，其中 {ready.got} 項可由系統自動備妥。
            </p>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100">
              <div
                className={`h-full rounded-full ${ready.percent >= 66 ? "bg-[#0d7360]" : ready.percent >= 33 ? "bg-[#96660f]" : "bg-slate-400"}`}
                style={{ width: `${ready.percent}%` }}
              />
            </div>
            <div className="mt-3 flex flex-wrap gap-4 border-b border-slate-100 pb-3 text-xs text-slate-400">
              <span>
                帳戶帶入{" "}
                {
                  autoDocs.filter((d) => isDocumentReady(d, answers, mydata.authorized))
                    .length
                }
                /{autoDocs.length}
              </span>
              <span>
                MyData{" "}
                {
                  myDocs.filter((d) => isDocumentReady(d, answers, mydata.authorized))
                    .length
                }
                /{myDocs.length}
              </span>
              <span>自備 {selfDocs.length}</span>
            </div>
            <div className="mt-2 divide-y divide-slate-100">
              {item.documents.map((doc) => {
                const ok = isDocumentReady(doc, answers, mydata.authorized);
                const source = resolveDocumentSource(doc.name);
                const pillClass = ok
                  ? doc.sourceType === "auto"
                    ? "bg-[#e6f2ef] text-[#27756c]"
                    : "bg-[#eeecf8] text-[#54479c]"
                  : doc.sourceType === "mydata"
                    ? "bg-[#eeecf8] text-[#54479c]"
                    : doc.sourceType === "auto"
                      ? "bg-[#eaf0f5] text-[#3f5b73]"
                      : "bg-slate-100 text-slate-500";
                const pillLabel = ok
                  ? doc.sourceType === "auto"
                    ? "已帶入"
                    : "已取得"
                  : doc.sourceType === "mydata"
                    ? "授權後可得"
                    : doc.sourceType === "auto"
                      ? "補答問題後可帶入"
                      : "需自行準備";
                return (
                  <div className="flex gap-3 py-3" key={doc.name}>
                    <span
                      className={`mt-0.5 grid size-6 shrink-0 place-items-center rounded-lg text-xs font-bold ${
                        ok
                          ? doc.sourceType === "auto"
                            ? "bg-[#0d7360] text-white"
                            : "bg-[#54479c] text-white"
                          : "border border-dashed border-slate-300 text-slate-400"
                      }`}
                    >
                      {ok ? "✓" : "·"}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-slate-800">
                        {doc.name}{" "}
                        <span
                          className={`ml-1 rounded-full px-2 py-0.5 text-[11px] font-bold ${pillClass}`}
                        >
                          {pillLabel}
                        </span>
                      </p>
                      <p className="mt-0.5 text-xs text-slate-400">{doc.note}</p>
                      <p className="mt-1 text-xs text-slate-400">
                        <span className="mr-1 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold text-slate-400">
                          來源
                        </span>
                        {source.org}
                        {source.linkLabel !== "—" && (
                          <button
                            className="ml-1 font-bold text-[#27756c]"
                            onClick={() =>
                              showToast(`（示範）將開啟：${source.linkLabel}`)
                            }
                            type="button"
                          >
                            {source.linkLabel} ↗
                          </button>
                        )}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          {!mydata.authorized && myDocs.length > 0 && (
            <section className="rounded-2xl border-2 border-[#d9d3f0] bg-[#eeecf8] p-5">
              <p className="text-sm font-bold text-[#54479c]">
                🔐 授權 MyData 可再備妥 {myDocs.length} 項
              </p>
              <p className="mt-2 text-xs leading-6 text-[#4a4270]">
                戶籍、所得、財產、勞保等官方證明可由你本人授權後自動取得，不必臨櫃調閱。
              </p>
              <button
                className="mt-3 rounded-xl bg-[#54479c] px-4 py-2 text-sm font-bold text-white transition hover:bg-[#463b85]"
                onClick={authorizeMyData}
                type="button"
              >
                前往 MyData 授權
              </button>
            </section>
          )}

          <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h3 className="text-base font-bold text-slate-900">帶著這份清單去辦理</h3>
            <p className="mt-1 text-xs text-slate-400">
              建議印出來，或存成 PDF 存在手機裡。
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                className="rounded-xl bg-[#153f3b] px-4 py-2 text-sm font-bold text-white transition hover:bg-[#1c504b]"
                onClick={() => window.print()}
                type="button"
              >
                列印 / 存成 PDF
              </button>
              <button
                className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-bold text-slate-600 transition hover:border-[#74a9a3] hover:text-[#27756c]"
                onClick={() => showToast("（示範）已下載預填申請表")}
                type="button"
              >
                下載預填表單
              </button>
            </div>
          </section>
        </div>
      </div>

      <NotEligibleAndInfoPanel
        answers={answers}
        currentItemId={item.id}
        items={BENEFIT_ITEMS}
        onBackToMatch={backToMatch}
        questions={ELIGIBILITY_QUESTIONS}
      />
    </div>
  );
}

type KeyMetricProps = {
  label: string;
  value: string;
  hint?: string;
};

function KeyMetric({ label, value, hint }: KeyMetricProps) {
  return (
    <div className="bg-white px-5 py-4">
      <p className="text-[11px] font-bold text-slate-400">{label}</p>
      <p className="mt-1 text-base font-bold text-slate-900">
        {value}
        {hint && (
          <span className="ml-1 text-xs font-medium text-slate-400">{hint}</span>
        )}
      </p>
    </div>
  );
}

type InfoBoxProps = {
  label: string;
  value: string;
  hint?: string;
};

function InfoBox({ label, value, hint }: InfoBoxProps) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
      <p className="text-[11px] font-bold text-slate-400">{label}</p>
      <p className="mt-1 text-sm font-bold text-slate-900">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-slate-400">{hint}</p>}
    </div>
  );
}
