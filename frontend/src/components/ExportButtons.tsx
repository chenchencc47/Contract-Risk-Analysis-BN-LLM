import { useState } from "react";

interface Props {
  contractId: string;
  markdown: string;
}

export function ExportButtons({ contractId, markdown }: Props) {
  const [exporting, setExporting] = useState<string | null>(null);

  const downloadFile = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleExportMD = async () => {
    setExporting("md");
    try {
      const res = await fetch("/api/export/md", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          markdown,
          filename: `contract-review-${contractId}`,
        }),
      });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      downloadFile(blob, `contract-review-${contractId}.md`);
    } catch (err) {
      // Fallback: client-side download
      const blob = new Blob([markdown], { type: "text/markdown" });
      downloadFile(blob, `contract-review-${contractId}.md`);
    } finally {
      setExporting(null);
    }
  };

  const handleExportPDF = async () => {
    setExporting("pdf");
    try {
      const res = await fetch("/api/export/pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          markdown,
          filename: `contract-review-${contractId}`,
        }),
      });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      downloadFile(blob, `contract-review-${contractId}.pdf`);
    } catch {
      alert("PDF 导出失败，请确认后端服务已启动");
    } finally {
      setExporting(null);
    }
  };

  return (
    <>
      <button
        onClick={handleExportMD}
        disabled={exporting !== null}
        className="text-xs text-[#8B6F5C] hover:text-[#6B5243] font-medium
                   px-3 py-1.5 border border-[#E8E2DB] rounded-md
                   hover:border-[#8B6F5C] transition-all duration-200
                   disabled:opacity-50"
      >
        {exporting === "md" ? "⏳ 导出中..." : "⬇ Markdown"}
      </button>
      <button
        onClick={handleExportPDF}
        disabled={exporting !== null}
        className="text-xs text-white bg-[#8B6F5C] hover:bg-[#6B5243] font-medium
                   px-3 py-1.5 border border-[#8B6F5C] rounded-md
                   transition-all duration-200 disabled:opacity-50"
      >
        {exporting === "pdf" ? "⏳ 导出中..." : "📄 PDF"}
      </button>
    </>
  );
}
