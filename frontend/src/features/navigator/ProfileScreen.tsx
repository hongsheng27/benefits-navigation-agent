import { useState } from "react";

import { MY_DATA_SOURCE_SETS } from "../../mocks/profileData";
import type { ProfileField, ProfileSectionKey } from "../../types/navigator";
import { ConfirmDialog } from "./ConfirmDialog";
import { EditFieldModal } from "./EditFieldModal";
import { useNavigator } from "./NavigatorContext";

const SOURCE_LABEL: Record<string, { label: string; className: string }> = {
  self: { label: "自行填寫", className: "bg-[#eaf0f5] text-[#3f5b73]" },
  mydata: { label: "MyData", className: "bg-[#eeecf8] text-[#54479c]" },
  calc: { label: "系統推算", className: "bg-[#e6f2ef] text-[#27756c]" },
};

type ActiveTab = ProfileSectionKey | "mydata" | "privacy";

export function ProfileScreen() {
  const {
    state,
    closeProfile,
    editProfileField,
    authorizeMyData,
    revokeMyData,
    resetAllData,
    showToast,
  } = useNavigator();
  const { profile, mydata, answers } = state;

  const [activeTab, setActiveTab] = useState<ActiveTab>("basic");
  const [editingCode, setEditingCode] = useState<string | null>(null);
  const [confirmingWipe, setConfirmingWipe] = useState(false);

  const sectionKeys = Object.keys(profile) as ProfileSectionKey[];
  const allFields = sectionKeys.flatMap((key) => profile[key].fields);
  const filledCount = allFields.filter((f) => f.value).length;
  const mydataCount = allFields.filter((f) => f.source === "mydata").length;
  const completeness = allFields.length
    ? Math.round((filledCount / allFields.length) * 100)
    : 0;

  const editingField: ProfileField | undefined = editingCode
    ? allFields.find((f) => f.code === editingCode)
    : undefined;

  return (
    <div className="space-y-6">
      <button
        className="text-sm font-bold text-slate-500 transition hover:text-[#27756c]"
        onClick={closeProfile}
        type="button"
      >
        ← 回到流程
      </button>

      <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <span className="grid size-12 place-items-center rounded-full bg-[#eaf0f5] text-lg font-bold text-[#3f5b73]">
          李
        </span>
        <div>
          <p className="text-base font-bold text-slate-900">李○芳</p>
          <p className="text-xs text-slate-400">接住帳戶</p>
        </div>
        <span className="ml-auto rounded-full bg-[#e6f2ef] px-3 py-1.5 text-xs font-bold text-[#27756c]">
          ✓ 已儲存至你的帳戶
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="已填寫欄位" value={`${filledCount} / ${allFields.length}`} />
        <Stat label="MyData 帶入" value={String(mydata.authorized ? mydataCount : 0)} valueClassName="text-[#54479c]" />
        <Stat label="資料完整度" value={`${completeness}%`} valueClassName="text-[#27756c]" />
        <Stat label="本次已答問題" value={String(Object.keys(answers).length)} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[13rem_minmax(0,1fr)]">
        <nav className="h-fit rounded-2xl border border-slate-200 bg-white p-2 shadow-sm">
          {sectionKeys.map((key) => (
            <NavButton
              active={activeTab === key}
              key={key}
              label={profile[key].title}
              onClick={() => setActiveTab(key)}
            />
          ))}
          <NavButton
            active={activeTab === "mydata"}
            label="MyData 授權"
            onClick={() => setActiveTab("mydata")}
          />
          <NavButton
            active={activeTab === "privacy"}
            label="隱私與資料管理"
            onClick={() => setActiveTab("privacy")}
          />
        </nav>

        <div>
          {sectionKeys.includes(activeTab as ProfileSectionKey) && (
            <SectionPanel
              onEdit={(code) => setEditingCode(code)}
              section={profile[activeTab as ProfileSectionKey]}
            />
          )}
          {activeTab === "mydata" && (
            <MyDataPanel
              authorized={mydata.authorized}
              authorizedAt={mydata.authorizedAt}
              expiresAt={mydata.expiresAt}
              onAuthorize={authorizeMyData}
              onRevoke={revokeMyData}
              profile={profile}
            />
          )}
          {activeTab === "privacy" && (
            <PrivacyPanel
              lastUpdatedHint="任何欄位變更都會即時同步"
              mydataExpiresAt={mydata.expiresAt}
              onExportData={() => showToast("（示範）已匯出個人資料 JSON")}
              onViewUsageLog={() => showToast("（示範）已產生資料使用紀錄")}
              onWipe={() => setConfirmingWipe(true)}
            />
          )}
        </div>
      </div>

      {editingField && (
        <EditFieldModal
          field={editingField}
          onClose={() => setEditingCode(null)}
          onSave={(value) => {
            editProfileField(editingField.code, value);
            setEditingCode(null);
          }}
        />
      )}

      {confirmingWipe && (
        <ConfirmDialog
          confirmLabel="永久刪除"
          description="會清空你填寫的所有個人資料、MyData 帶入內容與本次的對話與作答紀錄。此動作無法復原。"
          onCancel={() => setConfirmingWipe(false)}
          onConfirm={() => {
            resetAllData();
            setConfirmingWipe(false);
          }}
          title="確定要永久刪除我的資料嗎？"
        />
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  valueClassName,
}: {
  label: string;
  value: string;
  valueClassName?: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className={`text-xl font-bold ${valueClassName ?? "text-slate-900"}`}>{value}</p>
      <p className="text-xs text-slate-400">{label}</p>
    </div>
  );
}

function NavButton({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className={`block w-full rounded-xl px-4 py-2.5 text-left text-sm transition ${
        active ? "bg-[#e6f2ef] font-bold text-[#27756c]" : "text-slate-600 hover:bg-slate-50"
      }`}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  );
}

function SectionPanel({
  section,
  onEdit,
}: {
  section: { title: string; description: string; fields: ProfileField[] };
  onEdit: (code: string) => void;
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h3 className="text-base font-bold text-slate-900">{section.title}</h3>
      <p className="mt-1 text-xs leading-6 text-slate-400">{section.description}</p>
      <div className="mt-4 divide-y divide-slate-100">
        {section.fields.map((field) => {
          const src = SOURCE_LABEL[field.source];
          return (
            <div className="flex flex-wrap items-center gap-3 py-3" key={field.code}>
              <div className="min-w-[160px] flex-1">
                <p className="text-sm font-medium text-slate-800">{field.label}</p>
                <p className="text-xs text-slate-400">{field.why}</p>
              </div>
              <span className={field.value ? "text-sm font-bold text-slate-900" : "text-sm italic text-slate-400"}>
                {field.value || "尚未填寫"}
              </span>
              <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${src.className}`}>
                {src.label}
              </span>
              {field.source !== "calc" && (
                <button
                  className="rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-500 transition hover:border-[#74a9a3] hover:text-[#27756c]"
                  onClick={() => onEdit(field.code)}
                  type="button"
                >
                  修改
                </button>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function MyDataPanel({
  authorized,
  authorizedAt,
  expiresAt,
  profile,
  onAuthorize,
  onRevoke,
}: {
  authorized: boolean;
  authorizedAt: string | null;
  expiresAt: string | null;
  profile: Record<ProfileSectionKey, { fields: ProfileField[] }>;
  onAuthorize: () => void;
  onRevoke: () => void;
}) {
  const findFieldLabel = (code: string) => {
    for (const key of Object.keys(profile) as ProfileSectionKey[]) {
      const field = profile[key].fields.find((f) => f.code === code);
      if (field) return field.label;
    }
    return code;
  };

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="flex items-center gap-2 text-base font-bold text-slate-900">
          MyData 授權狀態
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-bold ${
              authorized ? "bg-[#eeecf8] text-[#54479c]" : "bg-slate-100 text-slate-500"
            }`}
          >
            {authorized ? "已授權" : "尚未授權"}
          </span>
        </h3>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          {authorized
            ? `授權時間 ${authorizedAt}　·　有效期至 ${expiresAt}。資料已存入你的帳戶，下次諮詢不需重填。`
            : "授權後可自動取得所得、財產、勞保、戶籍等官方資料，省去臨櫃調閱，也讓備妥率大幅提升。"}
        </p>
        <div className="mt-4 divide-y divide-slate-100">
          {MY_DATA_SOURCE_SETS.map((set) => (
            <div className="flex flex-wrap items-center gap-3 py-2.5" key={set.fieldCode}>
              <div className="min-w-[160px] flex-1">
                <p className="text-sm font-medium text-slate-800">{set.name}</p>
                <p className="text-xs text-slate-400">
                  {set.org}　→　{findFieldLabel(set.fieldCode)}
                </p>
              </div>
              <span
                className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${
                  authorized ? "bg-[#eeecf8] text-[#54479c]" : "bg-[#eaf0f5] text-[#3f5b73]"
                }`}
              >
                {authorized ? "已取得" : "未取得"}
              </span>
            </div>
          ))}
        </div>
        <div className="mt-4 flex gap-2">
          {authorized ? (
            <>
              <button
                className="rounded-xl border border-[#d9d3f0] bg-white px-4 py-2 text-sm font-bold text-[#54479c]"
                onClick={onAuthorize}
                type="button"
              >
                重新授權更新資料
              </button>
              <button
                className="rounded-xl bg-[#9e3a4e] px-4 py-2 text-sm font-bold text-white transition hover:bg-[#873041]"
                onClick={onRevoke}
                type="button"
              >
                撤回授權並刪除帶入資料
              </button>
            </>
          ) : (
            <button
              className="rounded-xl bg-[#54479c] px-4 py-2 text-sm font-bold text-white transition hover:bg-[#463b85]"
              onClick={onAuthorize}
              type="button"
            >
              前往 MyData 授權
            </button>
          )}
        </div>
      </section>
      <div className="flex gap-3 rounded-2xl border border-[#d7e1ea] bg-[#eaf0f5] px-5 py-4 text-sm leading-6 text-[#3a4d5e]">
        <span>🔐</span>
        <p>
          接住以<strong>服務提供者</strong>身分介接 MyData，所有資料都由你本人在官方平台單次同意後傳送。
          我們不會、也無法主動查詢你的任何資料。
        </p>
      </div>
    </div>
  );
}

function PrivacyPanel({
  mydataExpiresAt,
  lastUpdatedHint,
  onExportData,
  onViewUsageLog,
  onWipe,
}: {
  mydataExpiresAt: string | null;
  lastUpdatedHint: string;
  onExportData: () => void;
  onViewUsageLog: () => void;
  onWipe: () => void;
}) {
  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-base font-bold text-slate-900">你的資料存在哪裡</h3>
        <p className="mt-1 text-xs leading-6 text-slate-400">
          為了讓你下次不用重填、也能追蹤準備進度，這些資料儲存在接住的資料庫中，與你的帳戶綁定。
        </p>
        <div className="mt-3 divide-y divide-slate-100 text-sm">
          <Row label="儲存位置" value="接住服務資料庫（加密儲存）" />
          <Row hint="任何欄位變更都會即時同步" label="最後更新" value={lastUpdatedHint} />
          <Row label="MyData 資料有效期" value={mydataExpiresAt ? `至 ${mydataExpiresAt}` : "無"} />
        </div>
      </section>
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-base font-bold text-slate-900">你可以做的事</h3>
        <p className="mt-1 text-xs leading-6 text-slate-400">資料是你的，隨時可以帶走或刪除。</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-bold text-slate-600 transition hover:border-[#74a9a3] hover:text-[#27756c]"
            onClick={onExportData}
            type="button"
          >
            下載我的所有資料
          </button>
          <button
            className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-bold text-slate-600 transition hover:border-[#74a9a3] hover:text-[#27756c]"
            onClick={onViewUsageLog}
            type="button"
          >
            查看資料使用紀錄
          </button>
        </div>
      </section>
      <section className="rounded-2xl border border-[#f0d3da] bg-[#fbeef1] p-6">
        <h3 className="text-base font-bold text-[#9e3a4e]">刪除我的資料</h3>
        <p className="mt-1 text-sm leading-6 text-[#7a3546]">
          會從資料庫永久刪除你填寫的所有個人資料、MyData 帶入內容與歷次諮詢紀錄。此動作無法復原。
        </p>
        <button
          className="mt-3 rounded-xl bg-[#9e3a4e] px-4 py-2 text-sm font-bold text-white transition hover:bg-[#873041]"
          onClick={onWipe}
          type="button"
        >
          永久刪除我的資料
        </button>
      </section>
    </div>
  );
}

function Row({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 py-2.5">
      <div>
        <p className="font-medium text-slate-800">{label}</p>
        {hint && <p className="text-xs text-slate-400">{hint}</p>}
      </div>
      <span className="font-bold text-slate-900">{value}</span>
    </div>
  );
}
