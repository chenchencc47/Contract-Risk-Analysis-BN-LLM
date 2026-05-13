import { useState, useRef, useCallback } from "react";

interface Props {
  onSubmit: (text: string, id: string, reviewParty: "buyer" | "seller", dual: boolean, strategy: boolean) => void;
  isLoading: boolean;
}

const SAMPLE = `采购合同

甲方（买方）：深圳市华创科技有限公司
乙方（卖方）：广州市明达电子有限公司

一、产品规格与交付
乙方向甲方提供工业级温度传感器模组 TSM-200，数量 5000 件。交货日期为合同签订后 45 日内，由乙方负责运输至甲方指定仓库。

二、验收标准
货物送达后 5 个工作日内，由甲方质检部门按双方确认的技术规格书进行验收。验收合格的，出具验收确认书；不合格的，甲方有权拒收并要求乙方在 10 日内更换。

三、价款与支付
合同总金额为人民币 1,250,000 元。甲方于合同签订后 7 日内支付 30% 预付款，验收合格后 15 日内支付 65% 尾款，剩余 5% 作为质量保证金于交付后 12 个月支付。

四、违约责任
乙方逾期交货的，每逾期一日按未交货物金额的 0.5‰ 支付违约金；逾期超过 15 日的，甲方有权解除合同并要求乙方退还已付款项并支付合同总额 10% 的违约金。

五、争议解决
因本合同引起的任何争议，双方应友好协商解决；协商不成的，任何一方均可向乙方所在地人民法院提起诉讼。

六、合同期限
本合同自双方签字盖章之日起生效，至全部货物交付验收且质量保证期满之日终止。`;

interface FileInfo {
  name: string;
  content: string;
}

export function ContractInput({ onSubmit, isLoading }: Props) {
  const [text, setText] = useState("");
  const [id, setId] = useState("contract-001");
  const [reviewParty, setReviewParty] = useState<"buyer" | "seller">("buyer");
  const [dualMode, setDualMode] = useState(false);
  const [strategyMode, setStrategyMode] = useState(false);
  const [file, setFile] = useState<FileInfo | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [uploading, setUploading] = useState(false);

  const handleFile = useCallback(async (f: File) => {
    const suffix = f.name.split(".").pop()?.toLowerCase() || "";
    // Text files: read locally
    if (suffix === "md" || suffix === "txt") {
      const reader = new FileReader();
      reader.onload = (e) => {
        const content = e.target?.result as string;
        setFile({ name: f.name, content });
        setId(f.name.replace(/\.(md|txt)$/i, "") || "contract-001");
      };
      reader.readAsText(f);
      return;
    }
    if (suffix === "doc") {
      alert("暂不支持旧版 .doc 文件，请另存为 .docx 后上传");
      return;
    }
    // PDF/Word: upload to server for extraction
    if (suffix === "pdf" || suffix === "docx") {
      setUploading(true);
      try {
        const form = new FormData();
        form.append("file", f);
        const res = await fetch("/api/upload", { method: "POST", body: form });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ error: "上传失败" }));
          alert(err.error || "文件解析失败");
          return;
        }
        const data = await res.json();
        setFile({ name: f.name, content: data.text });
        setId(f.name.replace(/\.(pdf|docx)$/i, "") || "contract-001");
      } catch {
        alert("文件上传失败，请检查网络连接");
      } finally {
        setUploading(false);
      }
      return;
    }
    alert("不支持的文件格式，支持 .pdf / .docx / .md / .txt；旧版 .doc 请另存为 .docx 后上传");
  }, []);

  const removeFile = () => {
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  };

  const handleSubmit = () => {
    if (file) {
      onSubmit(file.content, id.trim() || "contract-001", reviewParty, dualMode, strategyMode);
    } else {
      const finalText = text.trim() || SAMPLE;
      onSubmit(finalText, id.trim() || "contract-001", reviewParty, dualMode, strategyMode);
    }
  };

  return (
    <section className="max-w-3xl mx-auto px-6 pt-12 pb-8 animate-fade-in">
      <div className="mb-8">
        <h2 className="font-serif text-3xl text-[#8B6F5C] mb-2">
          合同风险审查
        </h2>
        <p className="text-[#9B8E83] text-sm leading-relaxed max-w-lg">
          上传合同文件或粘贴文本，系统将通过{" "}
          <span className="text-[#6B5E53] font-medium">LLM 抽取</span> →{" "}
          <span className="text-[#6B5E53] font-medium">贝叶斯网络推理</span> →{" "}
          <span className="text-[#6B5E53] font-medium">智能报告生成</span>{" "}
          三步流程，输出可解释的风险评估。
        </p>
      </div>

      <div className="mb-5">
        <label className="block text-xs font-medium text-[#6B5E53] mb-1.5 tracking-wide">
          合同编号
        </label>
        <input
          type="text"
          value={id}
          onChange={(e) => setId(e.target.value)}
          className="w-48 px-3 py-2 text-sm border border-[#E8E2DB] rounded-md
                     bg-white focus:outline-none focus:ring-2 focus:ring-[#8B6F5C]/30
                     focus:border-[#8B6F5C] transition-all duration-200
                     placeholder:text-[#9B8E83]"
          placeholder="contract-001"
        />
      </div>

      {/* ── File Upload ── */}
      {!file ? (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => !uploading && fileInputRef.current?.click()}
          className={`relative border-2 border-dashed rounded-xl p-8 text-center
            transition-all duration-200 mb-4
            ${uploading ? "cursor-wait opacity-70" : "cursor-pointer"}
            ${dragOver
              ? "border-[#8B6F5C] bg-[#F5F0EB]"
              : "border-[#E0D8CE] bg-[#FAF8F5] hover:border-[#D4A574] hover:bg-[#FDFCFA]"
            }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.doc,.md,.txt"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
            }}
            className="hidden"
            disabled={uploading}
          />
          {uploading ? (
            <>
              <span className="w-8 h-8 border-2 border-[#E8E2DB] border-t-[#8B6F5C] rounded-full animate-spin mx-auto mb-2" />
              <p className="text-sm text-[#8B6F5C] font-medium">正在解析文件...</p>
            </>
          ) : (
            <>
              <span className="text-3xl block mb-2 select-none">📄</span>
              <p className="text-sm text-[#6B5E53] font-medium mb-1">
                点击上传或拖拽合同文件到此处
              </p>
              <p className="text-xs text-[#9B8E83]">
                支持 PDF / Word / Markdown / 纯文本
              </p>
            </>
          )}
        </div>
      ) : (
        /* ── File loaded state ── */
        <div className="flex items-center justify-between bg-[#F2F5EF] border border-[#7B8B6F]/30
                        rounded-lg px-4 py-3 mb-4 animate-fade-in">
          <div className="flex items-center gap-3 min-w-0">
            <span className="text-xl shrink-0">📄</span>
            <div className="min-w-0">
              <p className="text-sm font-medium text-[#2C2416] truncate">
                {file.name}
              </p>
              <p className="text-[10px] text-[#9B8E83] font-mono">
                {file.content.length.toLocaleString()} 字符
              </p>
            </div>
          </div>
          <button
            onClick={(e) => { e.stopPropagation(); removeFile(); }}
            className="text-xs text-[#9B8E83] hover:text-[var(--color-risk-high)]
                       transition-colors duration-200 shrink-0 ml-3
                       px-2 py-1 rounded hover:bg-[var(--color-risk-high)]/10"
          >
            移除
          </button>
        </div>
      )}

      {/* ── Textarea fallback ── */}
      {!file && (
        <div className="relative group">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={SAMPLE}
            rows={14}
            className="w-full px-4 py-3.5 text-sm leading-relaxed font-mono
                       border border-[#E8E2DB] rounded-lg bg-white
                       focus:outline-none focus:ring-2 focus:ring-[#8B6F5C]/30
                       focus:border-[#8B6F5C] transition-all duration-200
                       resize-y placeholder:text-[#C4B8AC] placeholder:font-sans
                       placeholder:text-xs"
          />
          {!text.trim() && (
            <span className="absolute top-3 right-4 text-[10px] text-[#C4B8AC] bg-[#FAF8F5]
                             px-2 py-0.5 rounded-full font-medium pointer-events-none">
              示例合同
            </span>
          )}
        </div>
      )}

      {/* ── Review Party Selector ── */}
      <div className="flex items-center gap-3 mt-5 flex-wrap">
        <span className="text-xs font-medium text-[#6B5E53] tracking-wide">审查立场</span>
        <div className="flex bg-[#F0EBE4] rounded-lg p-0.5">
          <button
            onClick={() => { setReviewParty("buyer"); setDualMode(false); }}
            className={`px-4 py-1.5 text-xs font-medium rounded-md transition-all duration-200 ${
              reviewParty === "buyer" && !dualMode
                ? "bg-white text-[#8B6F5C] shadow-sm"
                : "text-[#9B8E83] hover:text-[#6B5E53]"
            }`}
          >
            甲方（买方）
          </button>
          <button
            onClick={() => { setReviewParty("seller"); setDualMode(false); }}
            className={`px-4 py-1.5 text-xs font-medium rounded-md transition-all duration-200 ${
              reviewParty === "seller" && !dualMode
                ? "bg-white text-[#8B6F5C] shadow-sm"
                : "text-[#9B8E83] hover:text-[#6B5E53]"
            }`}
          >
            乙方（卖方）
          </button>
          <button
            onClick={() => setDualMode(true)}
            className={`px-4 py-1.5 text-xs font-medium rounded-md transition-all duration-200 ${
              dualMode
                ? "bg-white text-[#7B8B6F] shadow-sm"
                : "text-[#9B8E83] hover:text-[#6B5E53]"
            }`}
          >
            🔄 双视角对比
          </button>
        </div>
        <label className="flex items-center gap-1.5 cursor-pointer ml-3">
          <input
            type="checkbox"
            checked={strategyMode}
            onChange={(e) => setStrategyMode(e.target.checked)}
            className="rounded"
          />
          <span className="text-xs text-[#6B5E53]">♟ 谈判策略</span>
        </label>
      </div>

      <button
        onClick={handleSubmit}
        disabled={isLoading || uploading}
        className="mt-5 w-full sm:w-auto px-8 py-3 bg-[#8B6F5C] text-white text-sm
                   font-medium rounded-lg tracking-wide
                   hover:bg-[#6B5243] active:scale-[0.98]
                   disabled:opacity-50 disabled:cursor-not-allowed
                   transition-all duration-200 ease-out
                   shadow-sm hover:shadow-md"
      >
        {isLoading ? (
          <span className="flex items-center justify-center gap-2">
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            正在审查...
          </span>
        ) : file ? (
          `审查 ${file.name}`
        ) : (
          "开始审查"
        )}
      </button>
    </section>
  );
}
