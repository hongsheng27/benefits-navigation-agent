/**
 * 結果列「查看詳情」用的前端形狀。
 * 示範資料；之後可與追蹤項目／官方來源對齊，不進 session 契約。
 */

export type ItemDetail = {
  itemId: string;
  /** 申請／辦理地點 */
  location: string;
  /** 金額範圍或計算方式說明 */
  amountLabel: string;
  /** 補助／手續完整說明 */
  summary: string;
  /** 主管機關 */
  agency: string;
  /** 資格條件摘要 */
  eligibilityNotes: string[];
  /** 申請步驟 */
  steps: string[];
  /** 應備文件 */
  documents: string[];
  /** 官方說明或申請入口；沒有則 null */
  officialUrl: string | null;
};
