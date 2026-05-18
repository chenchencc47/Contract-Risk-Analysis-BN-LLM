import { useState, useEffect } from "react";

interface RedlineItem {
  id: number;
  contract_type: string;
  category: string;
  rule_id: string;
  label: string;
  description: string;
  severity: string | null;
  is_active: number;
  created_at: string;
}

const CONTRACT_TYPES = ["通用", "销售合同", "采购合同", "煤炭合同", "NDA", "软件许可"];
const CATEGORIES = ["hard_rules", "reasoning_hints"];
const SEVERITIES = ["企业红线", "高", "中"];

const CATEGORY_LABEL: Record<string, string> = {
  hard_rules: "硬红线",
  reasoning_hints: "推理指引",
};

interface Props {
  onBack: () => void;
}

export function RedlineManager({ onBack }: Props) {
  const [redlines, setRedlines] = useState<RedlineItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [editId, setEditId] = useState<number | null>(null);
  const [showAdd, setShowAdd] = useState(false);

  // Form state
  const [form, setForm] = useState({
    contract_type: "通用",
    category: "hard_rules",
    rule_id: "",
    label: "",
    description: "",
    severity: "",
    is_active: 1,
  });

  const fetchRedlines = (showSpinner = true) => {
    if (showSpinner) {
      setLoading(true);
    }
    fetch("/api/redlines")
      .then((r) => r.json())
      .then((data) => {
        setRedlines(data.redlines || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => {
    fetch("/api/redlines")
      .then((r) => r.json())
      .then((data) => {
        setRedlines(data.redlines || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const resetForm = () => {
    setForm({ contract_type: "通用", category: "hard_rules", rule_id: "", label: "", description: "", severity: "", is_active: 1 });
    setEditId(null);
    setShowAdd(false);
  };

  const handleSubmit = async () => {
    if (!form.rule_id.trim() || !form.label.trim() || !form.description.trim()) return;
    try {
      const res = await fetch("/api/redlines", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (res.ok) {
        fetchRedlines();
        resetForm();
      }
    } catch {
      return;
    }
  };

  const handleEdit = (r: RedlineItem) => {
    setForm({
      contract_type: r.contract_type,
      category: r.category,
      rule_id: r.rule_id,
      label: r.label,
      description: r.description,
      severity: r.severity || "",
      is_active: r.is_active,
    });
    setEditId(r.id);
    setShowAdd(true);
  };

  const handleDelete = async (id: number) => {
    if (!confirm("确定删除这条红线规则？")) return;
    try {
      await fetch(`/api/redlines/${id}`, { method: "DELETE" });
      fetchRedlines();
    } catch {
      return;
    }
  };

  const grouped = redlines.reduce<Record<string, RedlineItem[]>>((acc, r) => {
    (acc[r.contract_type] ||= []).push(r);
    return acc;
  }, {});

  return (
    <div className="max-w-5xl mx-auto px-6 pb-20 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 pt-6">
        <div>
          <button onClick={onBack} className="text-sm text-[#8B6F5C] hover:text-[#6B5243] font-medium
            transition-colors duration-200 flex items-center gap-1.5">
            <span className="text-lg leading-none">←</span> 返回
          </button>
          <h2 className="font-serif text-2xl text-[#2C2416] mt-2">企业红线管理</h2>
        </div>
        <button
          onClick={() => { resetForm(); setShowAdd(true); }}
          className="text-sm text-white bg-[#8B6F5C] hover:bg-[#6B5243] font-medium
                     px-4 py-2 rounded-lg transition-colors"
        >
          + 新增规则
        </button>
      </div>

      {/* Add/Edit Modal */}
      {showAdd && (
        <div className="fixed inset-0 bg-black/30 z-20 flex items-center justify-center">
          <div className="bg-white rounded-xl p-6 w-full max-w-lg mx-4 shadow-lg max-h-[80vh] overflow-y-auto">
            <h3 className="font-serif text-[#2C2416] text-lg mb-4">
              {editId ? "编辑红线规则" : "新增红线规则"}
            </h3>
            <div className="space-y-3 text-sm">
              <div>
                <label className="text-[#9B8E83] text-xs">合同类型</label>
                <select value={form.contract_type} onChange={(e) => setForm({ ...form, contract_type: e.target.value })}
                  className="w-full border border-[#E8E2DB] rounded-lg px-3 py-2 mt-1">
                  {CONTRACT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[#9B8E83] text-xs">类别</label>
                <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}
                  className="w-full border border-[#E8E2DB] rounded-lg px-3 py-2 mt-1">
                  {CATEGORIES.map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c]} ({c})</option>)}
                </select>
              </div>
              <div>
                <label className="text-[#9B8E83] text-xs">规则ID（英文标识）</label>
                <input value={form.rule_id} onChange={(e) => setForm({ ...form, rule_id: e.target.value })}
                  placeholder="no_unlimited_liability" disabled={!!editId}
                  className="w-full border border-[#E8E2DB] rounded-lg px-3 py-2 mt-1 disabled:bg-[#F5F0EB]" />
              </div>
              <div>
                <label className="text-[#9B8E83] text-xs">标签</label>
                <input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })}
                  placeholder="禁止无限责任" className="w-full border border-[#E8E2DB] rounded-lg px-3 py-2 mt-1" />
              </div>
              <div>
                <label className="text-[#9B8E83] text-xs">详细描述</label>
                <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
                  rows={3} placeholder="规则的具体内容..."
                  className="w-full border border-[#E8E2DB] rounded-lg px-3 py-2 mt-1 resize-none" />
              </div>
              {form.category === "hard_rules" && (
                <div>
                  <label className="text-[#9B8E83] text-xs">严重级别</label>
                  <select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}
                    className="w-full border border-[#E8E2DB] rounded-lg px-3 py-2 mt-1">
                    <option value="">无</option>
                    {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
              )}
              <div className="flex items-center gap-2">
                <input type="checkbox" checked={form.is_active === 1}
                  onChange={(e) => setForm({ ...form, is_active: e.target.checked ? 1 : 0 })} />
                <label className="text-[#9B8E83] text-xs">启用</label>
              </div>
            </div>
            <div className="flex gap-2 mt-5">
              <button onClick={handleSubmit}
                className="flex-1 text-sm text-white bg-[#8B6F5C] hover:bg-[#6B5243] font-medium
                           px-4 py-2 rounded-lg transition-colors">保存</button>
              <button onClick={resetForm}
                className="text-sm text-[#9B8E83] hover:text-[#6B5E53] px-4 py-2">取消</button>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-center text-[#9B8E83] py-12">加载中...</div>
      ) : Object.keys(grouped).length === 0 ? (
        <div className="text-center text-[#9B8E83] py-12">暂无红线规则。点击"+ 新增规则"开始添加。</div>
      ) : (
        <div className="space-y-6">
          {Object.entries(grouped).map(([contractType, items]) => (
            <div key={contractType} className="bg-white border border-[#E8E2DB] rounded-xl overflow-hidden shadow-sm">
              <h3 className="font-serif text-[#8B6F5C] text-sm px-4 py-3 bg-[#F5F0EB] border-b border-[#E8E2DB]">
                {contractType}
                <span className="text-[#9B8E83] ml-2 font-normal text-xs">{items.length} 条规则</span>
              </h3>
              <table className="w-full text-sm">
                <tbody>
                  {items.map((r) => (
                    <tr key={r.id} className="border-t border-[#F5F0EB] hover:bg-[#FAF8F5]">
                      <td className="px-4 py-3 w-24">
                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium
                          ${r.category === "hard_rules"
                            ? r.severity === "企业红线" ? "bg-red-50 text-red-700" : "bg-orange-50 text-orange-700"
                            : "bg-blue-50 text-blue-700"}`}>
                          {CATEGORY_LABEL[r.category] || r.category}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-medium text-[#2C2416]">{r.label}</div>
                        <div className="text-xs text-[#9B8E83] mt-0.5">{r.description}</div>
                      </td>
                      <td className="px-4 py-3 w-20">
                        {r.severity && (
                          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded
                            ${r.severity === "企业红线" ? "bg-red-50 text-red-700" : "bg-orange-50 text-orange-600"}`}>
                            {r.severity}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 w-16 text-center">
                        <span className={`text-[10px] ${r.is_active ? "text-green-600" : "text-[#C4B8AC]"}`}>
                          {r.is_active ? "启用" : "停用"}
                        </span>
                      </td>
                      <td className="px-4 py-3 w-24 text-right">
                        <button onClick={() => handleEdit(r)}
                          className="text-xs text-[#7B8B6F] hover:text-[#5A6B4F] mr-2">编辑</button>
                        <button onClick={() => handleDelete(r.id)}
                          className="text-xs text-red-400 hover:text-red-600">删除</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
