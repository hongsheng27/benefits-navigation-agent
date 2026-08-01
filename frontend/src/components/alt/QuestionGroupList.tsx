import { useState } from "react";

import type {
  AttributeValue,
  QuestionGroupView,
  QuestionView,
} from "../../types/session";
import { fieldLabel, optionLabel, purposeText, topicTitle } from "./copy";

type QuestionGroupListProps = {
  groups: QuestionGroupView[];
  disabled: boolean;
  onSubmit: (answers: Record<string, AttributeValue>) => void;
  /** 示範／復原時預填的答案。 */
  initialAnswers?: Record<string, AttributeValue>;
  /** 唯讀：顯示答案但不可更改、不可送出。 */
  readOnly?: boolean;
};

/**
 * 畫出後端給的問題卡並收集答案。
 *
 * 後端只給欄位代號、型別與選項代號，題目與選項文字全部來自 `copy.ts`。送出時整組一起
 * 送 —— 後端對 attribute_answers 是整筆驗證，部分接受會讓畫面無法表達「有一個沒收到」。
 */
export function QuestionGroupList({
  groups,
  disabled,
  onSubmit,
  initialAnswers = {},
  readOnly = false,
}: QuestionGroupListProps) {
  const [answers, setAnswers] =
    useState<Record<string, AttributeValue>>(initialAnswers);

  const questions = groups.flatMap((group) => group.questions);
  const requiredIds = questions.filter((q) => q.required).map((q) => q.fieldId);
  const canSubmit =
    !disabled &&
    !readOnly &&
    requiredIds.every((fieldId) => answers[fieldId] !== undefined);

  function setAnswer(fieldId: string, value: AttributeValue) {
    if (readOnly || disabled) {
      return;
    }
    setAnswers((current) => ({ ...current, [fieldId]: value }));
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (!canSubmit) {
          return;
        }
        onSubmit(answers);
      }}
      noValidate
    >
      {groups.map((group) => (
        <fieldset key={group.topicId} className="mt-6 first:mt-0" disabled={readOnly}>
          <legend className="text-[0.9rem] leading-[1.9] font-semibold tracking-[0.04em] text-[#2f4f45]">
            {topicTitle(group.topicId)}
            <span className="ml-2 text-[0.78rem] font-normal tracking-[0.08em] text-[#6b6459]">
              {group.groupIndex} / {group.groupTotal}
            </span>
          </legend>

          {group.questions.map((question) => (
            <QuestionField
              key={question.fieldId}
              disabled={disabled || readOnly}
              onChange={(value) => setAnswer(question.fieldId, value)}
              question={question}
              value={answers[question.fieldId]}
            />
          ))}
        </fieldset>
      ))}

      <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-3">
        <button
          type="submit"
          disabled={!canSubmit}
          className="rounded-sm bg-[#2f4f45] px-6 py-3 text-[0.95rem] leading-[1.8] font-semibold tracking-[0.04em] text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed disabled:bg-[#ddd5c7] disabled:text-[#6b6459]"
        >
          繼續
        </button>
        <p className="text-[0.82rem] leading-[1.9] text-[#6b6459]">
          {readOnly
            ? "目前無法送出答案；若在回看稍早步驟，請按「回到目前進度」。"
            : canSubmit
              ? "送出後我們會依你的回答整理結果。"
              : "請先回答上面的問題。"}
        </p>
      </div>
    </form>
  );
}

type QuestionFieldProps = {
  question: QuestionView;
  value: AttributeValue | undefined;
  disabled: boolean;
  onChange: (value: AttributeValue) => void;
};

function QuestionField({ question, value, disabled, onChange }: QuestionFieldProps) {
  const purpose = purposeText(question.purposeId);
  const purposeElementId = `${question.fieldId}-purpose`;

  return (
    <div className="mt-5" role="group" aria-labelledby={`${question.fieldId}-label`}>
      <p
        id={`${question.fieldId}-label`}
        className="text-[0.95rem] leading-[1.9] font-semibold text-[#171513]"
      >
        {fieldLabel(question.fieldId)}
      </p>
      {purpose ? (
        <p
          id={purposeElementId}
          className="mt-1 text-[0.82rem] leading-[2] text-[#6b6459]"
        >
          為什麼要問：{purpose}
        </p>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-2">
        {question.valueKind === "boolean" ? (
          <>
            <ChoiceButton
              disabled={disabled}
              label="是"
              onSelect={() => onChange(true)}
              selected={value === true}
            />
            <ChoiceButton
              disabled={disabled}
              label="否"
              onSelect={() => onChange(false)}
              selected={value === false}
            />
          </>
        ) : (
          question.optionIds.map((optionId) => (
            <ChoiceButton
              key={optionId}
              disabled={disabled}
              label={optionLabel(optionId)}
              onSelect={() => onChange(optionId)}
              selected={value === optionId}
            />
          ))
        )}
      </div>
    </div>
  );
}

type ChoiceButtonProps = {
  label: string;
  selected: boolean;
  disabled: boolean;
  onSelect: () => void;
};

function ChoiceButton({ label, selected, disabled, onSelect }: ChoiceButtonProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      disabled={disabled}
      onClick={onSelect}
      className={[
        "rounded-sm border px-4 py-2.5 text-[0.9rem] leading-[1.8] transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed",
        selected
          ? "border-[#2f4f45] bg-[#2f4f45] font-semibold text-[#f7f4ee] disabled:opacity-90"
          : "border-[#cfc5b4] bg-[#fffdfa] text-[#3a352e] hover:border-[#2f4f45] hover:text-[#2f4f45] disabled:hover:border-[#cfc5b4] disabled:hover:text-[#3a352e] disabled:opacity-70",
      ].join(" ")}
    >
      {label}
    </button>
  );
}
