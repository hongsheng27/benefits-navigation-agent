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
}: QuestionGroupListProps) {
  const [answers, setAnswers] = useState<Record<string, AttributeValue>>({});

  const questions = groups.flatMap((group) => group.questions);
  const requiredIds = questions.filter((q) => q.required).map((q) => q.fieldId);
  const canSubmit =
    !disabled && requiredIds.every((fieldId) => answers[fieldId] !== undefined);

  function setAnswer(fieldId: string, value: AttributeValue) {
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
        <fieldset key={group.topicId} className="mt-6 first:mt-0">
          <legend className="text-[0.9rem] leading-[1.9] font-semibold tracking-[0.04em] text-[#2f4f45]">
            {topicTitle(group.topicId)}
            <span className="ml-2 text-[0.78rem] font-normal tracking-[0.08em] text-[#6b6459]">
              {group.groupIndex} / {group.groupTotal}
            </span>
          </legend>

          {group.questions.map((question) => (
            <QuestionField
              key={question.fieldId}
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
          送出這組答案
        </button>
        <p className="text-[0.82rem] leading-[1.9] text-[#6b6459]">
          {canSubmit ? "答案會送到後端重新評估。" : "請先回答必填的題目。"}
        </p>
      </div>
    </form>
  );
}

type QuestionFieldProps = {
  question: QuestionView;
  value: AttributeValue | undefined;
  onChange: (value: AttributeValue) => void;
};

function QuestionField({ question, value, onChange }: QuestionFieldProps) {
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
          為什麼問這個：{purpose}
        </p>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-2">
        {question.valueKind === "boolean" ? (
          <>
            <ChoiceButton
              label="是"
              onSelect={() => onChange(true)}
              selected={value === true}
            />
            <ChoiceButton
              label="否"
              onSelect={() => onChange(false)}
              selected={value === false}
            />
          </>
        ) : (
          question.optionIds.map((optionId) => (
            <ChoiceButton
              key={optionId}
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
  onSelect: () => void;
};

function ChoiceButton({ label, selected, onSelect }: ChoiceButtonProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      className={[
        "rounded-sm border px-4 py-2.5 text-[0.9rem] leading-[1.8] transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]",
        selected
          ? "border-[#2f4f45] bg-[#2f4f45] font-semibold text-[#f7f4ee]"
          : "border-[#cfc5b4] bg-[#fffdfa] text-[#3a352e] hover:border-[#2f4f45] hover:text-[#2f4f45]",
      ].join(" ")}
    >
      {label}
    </button>
  );
}
