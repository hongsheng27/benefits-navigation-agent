const HOW_IT_WORKS = [
  {
    step: "描述狀況",
    detail: "說說發生了什麼事，用你自己的話就好，我會慢慢問清楚。",
  },
  {
    step: "狀況解讀",
    detail: "確認我有沒有理解錯，理解錯了可以隨時重新描述。",
  },
  {
    step: "媒合與評估",
    detail: "回答幾個必要問題，只問判定資格真正需要的欄位。",
  },
  {
    step: "準備清單",
    detail: "拿到應備文件、辦理順序與受理機關，可列印帶去辦理。",
  },
];

const TRUST_NOTES = [
  { label: "免費", detail: "不收任何費用" },
  { label: "不代辦", detail: "僅提供查詢與準備，申請仍由你自行送件" },
  { label: "可隨時刪除", detail: "你的資料由你控制" },
];

function BannerIllustration() {
  return (
    <svg
      aria-label="接住服務示意圖：人生突然的變動，由一張安全網承接"
      className="block h-auto w-full"
      role="img"
      viewBox="0 0 1000 260"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect fill="#e6f2ef" height="260" rx="16" width="1000" />
      <circle cx="878" cy="46" fill="#d4e9e3" r="58" />
      <circle cx="86" cy="212" fill="#d4e9e3" r="70" />
      <g fill="none" stroke="#0d7360" strokeOpacity="0.34" strokeWidth="2">
        <path d="M40 196 Q500 262 960 196" />
        <path d="M40 210 Q500 276 960 210" />
        <path d="M120 200 L150 232" />
        <path d="M200 205 L228 238" />
        <path d="M290 210 L316 242" />
        <path d="M390 214 L414 246" />
        <path d="M500 216 L522 248" />
        <path d="M610 214 L632 246" />
        <path d="M710 210 L734 242" />
        <path d="M800 205 L826 238" />
        <path d="M880 199 L906 231" />
      </g>
      <g transform="translate(112,58)">
        <rect
          fill="#fff"
          fillOpacity="0.72"
          height="120"
          rx="12"
          width="132"
          x="-46"
          y="-8"
        />
        <circle cx="8" cy="30" fill="#3f5b73" r="15" />
        <path d="M-8 88 q16-32 32-32 t32 32z" fill="#3f5b73" />
        <circle cx="48" cy="42" fill="#8fa6b8" r="10" />
        <path d="M34 88 q14-22 28-22 t14 22z" fill="#8fa6b8" />
        <path d="M62 16 v-14" stroke="#96660f" strokeWidth="3" />
        <circle cx="62" cy="-2" fill="#efa32a" r="4" />
        <text
          fill="#0d7360"
          fontFamily="sans-serif"
          fontSize="13"
          fontWeight="700"
          textAnchor="middle"
          x="20"
          y="108"
        >
          親人過世
        </text>
      </g>
      <g transform="translate(330,50)">
        <rect
          fill="#fff"
          fillOpacity="0.72"
          height="128"
          rx="12"
          width="128"
          x="-44"
          y="0"
        />
        <circle cx="10" cy="38" fill="#54479c" r="15" />
        <path d="M-6 96 q16-32 32-32 t32 32z" fill="#54479c" />
        <circle cx="52" cy="62" fill="#a49bd8" r="10" />
        <path d="M40 96 q12-20 24-20 t12 20z" fill="#a49bd8" />
        <path d="M26 62 h18" stroke="#54479c" strokeLinecap="round" strokeWidth="3" />
        <text
          fill="#0d7360"
          fontFamily="sans-serif"
          fontSize="13"
          fontWeight="700"
          textAnchor="middle"
          x="20"
          y="118"
        >
          獨自照顧孩子
        </text>
      </g>
      <g transform="translate(548,50)">
        <rect
          fill="#fff"
          fillOpacity="0.72"
          height="128"
          rx="12"
          width="128"
          x="-44"
          y="0"
        />
        <circle cx="20" cy="36" fill="#a35a2c" r="15" />
        <path d="M4 94 q16-32 32-32 t32 32z" fill="#a35a2c" />
        <rect fill="#d8874f" height="26" rx="4" width="34" x="-24" y="56" />
        <path d="M-16 56 v-6 h18 v6" fill="none" stroke="#a35a2c" strokeWidth="3" />
        <text
          fill="#0d7360"
          fontFamily="sans-serif"
          fontSize="13"
          fontWeight="700"
          textAnchor="middle"
          x="20"
          y="118"
        >
          失去收入
        </text>
      </g>
      <g transform="translate(766,50)">
        <rect
          fill="#fff"
          fillOpacity="0.72"
          height="128"
          rx="12"
          width="128"
          x="-44"
          y="0"
        />
        <circle cx="14" cy="38" fill="#0d7360" r="14" />
        <path d="M0 94 q14-30 28-30 t28 30z" fill="#0d7360" />
        <circle cx="54" cy="46" fill="#7bbfa9" r="11" />
        <path d="M40 94 q14-24 28-24 t10 24z" fill="#7bbfa9" />
        <path d="M74 52 v42" stroke="#5f6b74" strokeLinecap="round" strokeWidth="3" />
        <text
          fill="#0d7360"
          fontFamily="sans-serif"
          fontSize="13"
          fontWeight="700"
          textAnchor="middle"
          x="20"
          y="118"
        >
          照顧長輩
        </text>
      </g>
      <text
        fill="#0a5f50"
        fontFamily="sans-serif"
        fontSize="15"
        fontWeight="700"
        letterSpacing="2"
        textAnchor="middle"
        x="500"
        y="30"
      >
        生活突然改變的時候，不必自己一個人查
      </text>
    </svg>
  );
}

export function IntroHero() {
  return (
    <div className="mb-6 overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
      <BannerIllustration />
      <div className="px-7 py-6">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          先說說你的狀況，我幫你找出可以申請的補助
        </h1>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-500">
          遇到親人過世、失去工作、獨自照顧家人這類突然的變動時，往往不知道政府有哪些補助、
          該去哪個機關、要準備什麼文件。接住會先聽你說明處境，再幫你判斷可能符合的項目，
          並整理成一份可以帶去辦理的清單。
        </p>

        <div className="mt-6 grid gap-4 border-y border-slate-100 py-5 sm:grid-cols-2 lg:grid-cols-4">
          {HOW_IT_WORKS.map((item, index) => (
            <div className="flex gap-3" key={item.step}>
              <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-[#e6f2ef] text-xs font-bold text-[#27756c]">
                {index + 1}
              </span>
              <div>
                <p className="text-sm font-bold text-slate-900">{item.step}</p>
                <p className="mt-1 text-xs leading-6 text-slate-400">{item.detail}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-5 flex flex-wrap gap-x-8 gap-y-3">
          {TRUST_NOTES.map((note) => (
            <p className="text-xs leading-6 text-slate-400" key={note.label}>
              <span className="font-bold text-[#27756c]">{note.label}</span>　
              {note.detail}
            </p>
          ))}
        </div>
      </div>
    </div>
  );
}
