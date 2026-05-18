interface Props {
  html: string;
}

export function ReportDocument({ html }: Props) {
  return (
    <article
      className="report-document bg-white border border-[#E8E2DB] rounded-xl p-6 md:p-10 shadow-sm max-w-none
        prose prose-stone
        prose-headings:font-sans prose-headings:font-bold
        prose-p:text-[#1D2129] prose-p:leading-[1.6] prose-p:text-[14px]
        prose-li:text-[#1D2129] prose-li:text-[14px]
        prose-code:bg-[#F2F3F5] prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded
        prose-code:text-xs prose-code:font-mono prose-a:text-[#165DFF] prose-a:underline"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
