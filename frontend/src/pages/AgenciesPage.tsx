import { useEffect, useMemo, useState } from "react";

import { listAgencies } from "../api/agencyClient";
import { listTrackedCases } from "../api/trackingClient";
import styles from "../components/alt/alt.module.css";
import {
  focusFromOpenCases,
  rankAgenciesForSituation,
  type AgencySituationFocus,
} from "../lib/agencySituation";
import type {
  AgencyConnectionStatus,
  AgencyDirectoryItem,
  AgencyOfficialStatus,
  AgencySourceType,
} from "../types/agency";

const SOURCE_TYPE_LABEL: Record<AgencySourceType, string> = {
  agency_site: "機關網站",
  benefit_index: "福利索引",
  reference_dataset: "參考資料集",
  other: "其他",
};

const OFFICIAL_LABEL: Record<AgencyOfficialStatus, string> = {
  verified_official: "已驗證官方",
  likely_official: "可能為官方",
  unverified: "尚未驗證",
};

const CONNECTION_LABEL: Record<AgencyConnectionStatus, string> = {
  active: "資料已接通",
  pending: "連線準備中",
  error: "連線異常",
  disabled: "已停用",
};

type AgencyCardProps = {
  agency: AgencyDirectoryItem;
  reasons?: string[];
  emphasized?: boolean;
};

function AgencyCard({ agency, reasons, emphasized = false }: AgencyCardProps) {
  return (
    <article
      className={`flex h-full flex-col border bg-[#fdfbf7] px-5 py-5 ${
        emphasized ? "border-[#2f4f45] shadow-[inset_3px_0_0_0_#2f4f45]" : "border-[#e0d8ca]"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-[0.75rem] tracking-[0.08em] text-[#8b8377]">
            {agency.jurisdictionLabel}
            <span className="mx-1.5 text-[#d0c6b6]">·</span>
            {SOURCE_TYPE_LABEL[agency.sourceType]}
          </p>
          <h2 className="mt-1.5 text-[1.1rem] font-semibold leading-[1.45] text-[#171513]">
            {agency.name}
          </h2>
        </div>
        <span className="rounded-sm border border-[#d8cfc0] px-2 py-0.5 text-[0.72rem] tracking-[0.04em] text-[#6b6459]">
          {CONNECTION_LABEL[agency.connectionStatus]}
        </span>
      </div>

      {reasons && reasons.length > 0 ? (
        <ul className="mt-3 space-y-1 border-l-2 border-[#2f4f45]/40 pl-3">
          {reasons.map((reason) => (
            <li key={reason} className="text-[0.82rem] leading-[1.7] text-[#2f4f45]">
              {reason}
            </li>
          ))}
        </ul>
      ) : null}

      <p className="mt-3 grow text-[0.9rem] leading-[1.85] text-[#4a453d]">
        {agency.summary}
      </p>

      <dl className="mt-4 space-y-1.5 text-[0.8rem] leading-[1.7] text-[#6b6459]">
        <div className="flex flex-wrap gap-x-2">
          <dt className="text-[#8b8377]">官方狀態</dt>
          <dd>{OFFICIAL_LABEL[agency.officialStatus]}</dd>
        </div>
        {agency.phone ? (
          <div className="flex flex-wrap gap-x-2">
            <dt className="text-[#8b8377]">電話</dt>
            <dd>{agency.phone}</dd>
          </div>
        ) : null}
        {agency.lastReviewedAt ? (
          <div className="flex flex-wrap gap-x-2">
            <dt className="text-[#8b8377]">資料檢視</dt>
            <dd>{agency.lastReviewedAt}</dd>
          </div>
        ) : null}
      </dl>

      {agency.relatedBenefitNames.length > 0 ? (
        <ul className="mt-4 flex flex-wrap gap-1.5">
          {agency.relatedBenefitNames.map((name) => (
            <li
              key={name}
              className="rounded-sm bg-[#f1f4f0] px-2 py-1 text-[0.75rem] text-[#2f4f45]"
            >
              {name}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 text-[0.78rem] text-[#a89f90]">尚無對應福利項目摘要</p>
      )}

      <div className="mt-5 flex flex-wrap gap-3 border-t border-[#eee7db] pt-4">
        <a
          href={agency.websiteUrl}
          target="_blank"
          rel="noreferrer noopener"
          className="text-[0.88rem] font-semibold text-[#2f4f45] underline decoration-[#a8bdb2] underline-offset-4 hover:decoration-[#2f4f45]"
        >
          官方網站
        </a>
        {agency.entryUrl ? (
          <a
            href={agency.entryUrl}
            target="_blank"
            rel="noreferrer noopener"
            className="text-[0.88rem] text-[#4a453d] underline decoration-[#d0c6b6] underline-offset-4 hover:decoration-[#2f4f45]"
          >
            相關入口
          </a>
        ) : null}
        {agency.relatedBenefitCount > 0 ? (
          <span className="text-[0.78rem] text-[#8b8377]">
            {agency.relatedBenefitCount} 項相關福利
          </span>
        ) : null}
      </div>
    </article>
  );
}

type AgenciesPageProps = {
  /** 從追蹤頁帶入的聚焦；未帶入時會依進行中案件自動推估。 */
  focus?: AgencySituationFocus | null;
  onClearFocus?: () => void;
};

export function AgenciesPage({ focus = null, onClearFocus }: AgenciesPageProps) {
  const [agencies, setAgencies] = useState<AgencyDirectoryItem[]>([]);
  const [isMock, setIsMock] = useState(true);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [jurisdiction, setJurisdiction] = useState<string>("all");
  const [autoFocus, setAutoFocus] = useState<AgencySituationFocus | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);

    Promise.all([
      listAgencies(controller.signal),
      listTrackedCases(controller.signal),
    ])
      .then(([agencyResponse, caseResponse]) => {
        if (controller.signal.aborted) {
          return;
        }
        setAgencies(agencyResponse.agencies);
        setIsMock(agencyResponse.isMock || caseResponse.isMock);
        setAutoFocus(focusFromOpenCases(caseResponse.cases));
        setLoading(false);
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setAgencies([]);
          setAutoFocus(null);
          setIsMock(true);
          setLoading(false);
        }
      });

    return () => controller.abort();
  }, []);

  const activeFocus = focus ?? autoFocus;

  const relevant = useMemo(
    () => rankAgenciesForSituation(agencies, activeFocus),
    [agencies, activeFocus],
  );

  const relevantIds = useMemo(
    () => new Set(relevant.map((item) => item.agency.agencyId)),
    [relevant],
  );

  const jurisdictions = useMemo(() => {
    const labels = [...new Set(agencies.map((a) => a.jurisdictionLabel))];
    return labels.sort((a, b) => a.localeCompare(b, "zh-Hant"));
  }, [agencies]);

  const filteredCatalog = useMemo(() => {
    const q = query.trim().toLowerCase();
    return agencies.filter((agency) => {
      if (jurisdiction !== "all" && agency.jurisdictionLabel !== jurisdiction) {
        return false;
      }
      if (!q) {
        return true;
      }
      const haystack = [
        agency.name,
        agency.organizationName,
        agency.summary,
        ...agency.relatedBenefitNames,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [agencies, jurisdiction, query]);

  const otherAgencies = useMemo(
    () => filteredCatalog.filter((agency) => !relevantIds.has(agency.agencyId)),
    [filteredCatalog, relevantIds],
  );

  const focusHeading = activeFocus?.caseTitle
    ? `與「${activeFocus.caseTitle}」相關`
    : activeFocus?.lifeEventLabel
      ? `與你目前的「${activeFocus.lifeEventLabel}」相關`
      : "與你目前情況相關";

  return (
    <div className={`${styles.page} min-h-[calc(100vh-4rem)] text-[#171513]`}>
      <main className="mx-auto w-full max-w-5xl px-5 py-10 sm:px-8 sm:py-14">
        <p className="text-[0.8rem] tracking-[0.08em] text-[#8b8377]">
          補助機關總覽
        </p>
        <h1 className="mt-2 text-[1.6rem] font-semibold leading-[1.4] text-[#171513]">
          相關機關與官方網站
        </h1>
        <p className="mt-3 max-w-2xl text-[0.95rem] leading-[1.9] text-[#5c564e]">
          會依你正在追蹤的情況，先整理可能用得到的機關；下面仍可瀏覽完整目錄。
        </p>

        {isMock ? (
          <p className="mt-5 max-w-2xl border-l-2 border-[#8a5a1a] bg-[#f6f1e6] px-4 py-3 text-[0.85rem] leading-[1.85] text-[#4a453d]">
            目前機關與案件皆為示範資料。之後會改讀資料庫與你的真實諮詢紀錄。
          </p>
        ) : null}

        {!loading && relevant.length > 0 ? (
          <section className="mt-10" aria-labelledby="relevant-agencies-heading">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2
                  id="relevant-agencies-heading"
                  className="text-[1.15rem] font-semibold text-[#2f4f45]"
                >
                  {focusHeading}
                </h2>
                <p className="mt-1 text-[0.85rem] leading-[1.8] text-[#6b6459]">
                  依你的追蹤案件中的機關與可辦項目對上的結果。
                </p>
              </div>
              {focus ? (
                <button
                  type="button"
                  onClick={onClearFocus}
                  className="text-[0.82rem] font-semibold text-[#2f4f45] underline-offset-4 hover:underline"
                >
                  改看全部進行中案件
                </button>
              ) : null}
            </div>
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              {relevant.map(({ agency, reasons }) => (
                <AgencyCard
                  key={agency.agencyId}
                  agency={agency}
                  reasons={reasons}
                  emphasized
                />
              ))}
            </div>
          </section>
        ) : null}

        {!loading && activeFocus === null ? (
          <p className="mt-8 border border-dashed border-[#d8cfc0] px-4 py-5 text-[0.9rem] leading-[1.9] text-[#6b6459]">
            目前沒有進行中的追蹤案件，所以先顯示完整機關目錄。開始諮詢並留下進度後，這裡會優先列出相關機關。
          </p>
        ) : null}

        <section className="mt-12" aria-labelledby="all-agencies-heading">
          <h2
            id="all-agencies-heading"
            className="text-[1.15rem] font-semibold text-[#171513]"
          >
            完整機關目錄
          </h2>

          <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-end">
            <label className="block min-w-0 flex-1">
              <span className="text-[0.8rem] text-[#8b8377]">搜尋機關或福利</span>
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="例如：勞保、長照、臺北…"
                className="mt-1.5 block w-full rounded-sm border border-[#cfc5b4] bg-[#fffdfa] px-3.5 py-2.5 text-[0.95rem] text-[#171513] placeholder:text-[#a89f90] focus-visible:border-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#2f4f45]"
              />
            </label>
            <label className="block sm:w-48">
              <span className="text-[0.8rem] text-[#8b8377]">行政層級／地區</span>
              <select
                value={jurisdiction}
                onChange={(event) => setJurisdiction(event.target.value)}
                className="mt-1.5 block w-full rounded-sm border border-[#cfc5b4] bg-[#fffdfa] px-3.5 py-2.5 text-[0.95rem] text-[#171513] focus-visible:border-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#2f4f45]"
              >
                <option value="all">全部</option>
                {jurisdictions.map((label) => (
                  <option key={label} value={label}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <p className="mt-4 text-[0.82rem] text-[#8b8377]" aria-live="polite">
            {loading
              ? "正在載入……"
              : relevant.length > 0
                ? `其餘 ${otherAgencies.length} 筆（相關機關已列於上方）`
                : `共 ${filteredCatalog.length} 筆`}
          </p>

          {!loading &&
          (relevant.length > 0 ? otherAgencies : filteredCatalog).length === 0 ? (
            <p className="mt-8 border border-dashed border-[#d8cfc0] px-4 py-8 text-[0.92rem] text-[#6b6459]">
              沒有符合的機關，試試其他關鍵字。
            </p>
          ) : (
            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              {(relevant.length > 0 ? otherAgencies : filteredCatalog).map(
                (agency) => (
                  <AgencyCard key={agency.agencyId} agency={agency} />
                ),
              )}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
