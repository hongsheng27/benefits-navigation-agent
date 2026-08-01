import styles from "../components/alt/alt.module.css";

const PILLARS = [
  {
    title: "先聽你說發生什麼事",
    body: "不用先懂法規名詞。用平常說話的方式描述就好，我們再幫你對到可能相關的補助與手續。",
  },
  {
    title: "只問真正需要的條件",
    body: "不會要姓名、身分證字號這類個資。問到夠判斷方向就停，減少白跑一趟。",
  },
  {
    title: "把下一步攤開來看",
    body: "告訴你可能要辦什麼、建議順序、該找哪個機關。我們協助你準備，不會代你送件。",
  },
] as const;

const PROMISES = [
  {
    title: "資格不靠感覺決定",
    body: "是否可能符合，由確定性規則判斷，不是讓 AI 自行裁定。",
  },
  {
    title: "依據盡量回到官方",
    body: "說明會盡量連到官方來源與受理窗口，方便你自行核對。",
  },
  {
    title: "你可以隨時回來",
    body: "追蹤進度留下文件與流程；機關總覽幫你對照該找誰。",
  },
] as const;

type ProductHomePageProps = {
  onStartConsult: () => void;
  onOpenTracking: () => void;
  onOpenAgencies: () => void;
};

export function ProductHomePage({
  onStartConsult,
  onOpenTracking,
  onOpenAgencies,
}: ProductHomePageProps) {
  return (
    <div className={`${styles.page} min-h-[calc(100vh-4rem)] text-[#171513]`}>
      <main className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-8 sm:py-16">
        <p
          className={`${styles.serif} text-[2.6rem] leading-[1.1] tracking-[0.14em] text-[#2f4f45] sm:text-[3.2rem]`}
        >
          接住
        </p>
        <h1 className="mt-5 text-[1.45rem] font-semibold leading-[1.55] text-[#171513] sm:text-[1.75rem]">
          生活突然改變時，
          <br />
          先有人陪你理出下一步。
        </h1>
        <p className="mt-5 max-w-2xl text-[0.98rem] leading-[1.95] text-[#4a453d]">
          親人過世、失去工作、需要長照……這類變動常常不知道政府有哪些補助、該去哪個機關、要準備什麼。
          接住希望在混亂裡先接住你：聽你說明處境，整理可能相關的項目與辦理方向，讓你比較不用一個人把規定查完。
        </p>

        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
          <button
            type="button"
            onClick={onStartConsult}
            className="rounded-sm bg-[#2f4f45] px-6 py-3.5 text-[1rem] font-semibold tracking-[0.04em] text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
          >
            開始新諮詢
          </button>
          <button
            type="button"
            onClick={onOpenTracking}
            className="rounded-sm border border-[#c9c0b0] bg-transparent px-5 py-3.5 text-[0.95rem] text-[#3a352e] transition-colors hover:border-[#2f4f45] hover:text-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
          >
            查看追蹤進度
          </button>
          <button
            type="button"
            onClick={onOpenAgencies}
            className="rounded-sm border border-[#c9c0b0] bg-transparent px-5 py-3.5 text-[0.95rem] text-[#3a352e] transition-colors hover:border-[#2f4f45] hover:text-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
          >
            瀏覽補助機關
          </button>
        </div>

        <section className="mt-14 border-t border-[#e0d8ca] pt-10" aria-labelledby="how-heading">
          <h2
            id="how-heading"
            className="text-[1.15rem] font-semibold tracking-[0.02em] text-[#2f4f45]"
          >
            我們想怎麼幫你
          </h2>
          <ul className="mt-6 space-y-6">
            {PILLARS.map((item, index) => (
              <li key={item.title} className="flex gap-4">
                <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-[#f1f4f0] text-[0.78rem] font-semibold text-[#2f4f45]">
                  {index + 1}
                </span>
                <div>
                  <h3 className="text-[0.98rem] font-semibold text-[#171513]">
                    {item.title}
                  </h3>
                  <p className="mt-1.5 text-[0.9rem] leading-[1.9] text-[#5c564e]">
                    {item.body}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section className="mt-14 border-t border-[#e0d8ca] pt-10" aria-labelledby="promise-heading">
          <h2
            id="promise-heading"
            className="text-[1.15rem] font-semibold tracking-[0.02em] text-[#2f4f45]"
          >
            我們堅持的事
          </h2>
          <ul className="mt-6 grid gap-5 sm:grid-cols-3">
            {PROMISES.map((item) => (
              <li key={item.title}>
                <h3 className="text-[0.92rem] font-semibold text-[#171513]">
                  {item.title}
                </h3>
                <p className="mt-1.5 text-[0.88rem] leading-[1.85] text-[#5c564e]">
                  {item.body}
                </p>
              </li>
            ))}
          </ul>
        </section>

        <section className="mt-14 border-t border-[#e0d8ca] pt-10">
          <p className="max-w-2xl text-[0.92rem] leading-[1.9] text-[#5c564e]">
            接住不是承辦窗口，也不能保證核定結果。我們希望在你最慌的時候，先幫你把「可能有哪些路、下一步做什麼」說清楚一點。
          </p>
          <button
            type="button"
            onClick={onStartConsult}
            className="mt-6 rounded-sm bg-[#2f4f45] px-6 py-3 text-[0.95rem] font-semibold tracking-[0.04em] text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
          >
            我想先說明我的情況
          </button>
        </section>
      </main>
    </div>
  );
}
