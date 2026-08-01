type ExamplePromptsProps = {
  labelId: string;
  prompts: readonly string[];
  onSelect: (prompt: string) => void;
};

export function ExamplePrompts({ labelId, prompts, onSelect }: ExamplePromptsProps) {
  return (
    <div role="group" aria-labelledby={labelId} className="mt-6">
      <p
        id={labelId}
        className="text-[0.85rem] leading-[1.9] tracking-[0.04em] text-[#6b6459]"
      >
        不知道怎麼寫？可以點下面句子，再改成你的情況
      </p>
      <ul className="mt-3 flex flex-col gap-2">
        {prompts.map((prompt) => (
          <li key={prompt}>
            <button
              type="button"
              onClick={() => onSelect(prompt)}
              className="group flex w-full items-start gap-2.5 rounded-sm border border-[#e0d8ca] bg-[#fdfbf7] px-3.5 py-3 text-left text-[0.9rem] leading-[1.9] text-[#3a352e] transition-colors hover:border-[#2f4f45] hover:bg-[#f4f1ea] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
            >
              <span
                aria-hidden="true"
                className="mt-[0.15rem] text-[0.95rem] leading-[1.7] text-[#a89f90] group-hover:text-[#2f4f45]"
              >
                「
              </span>
              <span className="min-w-0">{prompt}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
