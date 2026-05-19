interface Props {
  html: string;
}

export function ReportDocument({ html }: Props) {
  return (
    <article
      className="report-document bg-white border border-[#E8E2DB] rounded-xl p-6 md:p-10 shadow-sm w-full !max-w-full"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
