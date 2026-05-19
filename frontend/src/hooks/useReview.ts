import { useState, useCallback } from "react";
import type { ReviewResponse, ReviewState } from "../types";

interface DualData {
  buyer: Record<string, unknown> | null;
  seller: Record<string, unknown> | null;
  comparison: Record<string, unknown> | null;
}

export function useReview() {
  const [state, setState] = useState<ReviewState>({
    status: "idle",
    data: null,
    error: null,
  });
  const [dualData, setDualData] = useState<DualData | null>(null);

  const submitReview = useCallback(
    async (contractText: string, contractId: string, reviewParty: "buyer" | "seller" = "buyer", dual = false, partyRoleLabel?: string) => {
      if (!contractText.trim()) return;
      setState({ status: "loading", data: null, error: null });
      setDualData(null);
      try {
        const res = await fetch("/api/v2/review", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            contract_text: contractText,
            contract_id: contractId,
            review_party: reviewParty,
            party_role_label: partyRoleLabel || undefined,
          }),
        });
        if (!res.ok) {
          const errBody = await res.json().catch(() => null);
          throw new Error(errBody?.error || `服务器错误 (${res.status})`);
        }
        const data: ReviewResponse = await res.json();
        setState({ status: "success", data, error: null });
      } catch (err) {
        setState({
          status: "error",
          data: null,
          error: err instanceof Error ? err.message : "未知错误",
        });
      }
    },
    []
  );

  const submitDualReview = useCallback(
    async (contractText: string, contractId: string) => {
      if (!contractText.trim()) return;
      setState({ status: "loading", data: null, error: null });
      setDualData(null);
      try {
        // Run buyer review first (for the main report display)
        const buyerRes = await fetch("/api/v2/review", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            contract_text: contractText,
            contract_id: contractId,
            review_party: "buyer",
          }),
        });
        if (!buyerRes.ok) throw new Error("买方视角审查失败");
        const data: ReviewResponse = await buyerRes.json();

        // Fetch dual comparison
        const dualRes = await fetch("/api/v2/review/dual", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            contract_text: contractText,
            contract_id: contractId,
          }),
        });
        if (dualRes.ok) {
          const dual = await dualRes.json();
          setDualData({
            buyer: dual.buyer || null,
            seller: dual.seller || null,
            comparison: dual.comparison || null,
          });
        }

        setState({ status: "success", data, error: null });
      } catch (err) {
        setState({
          status: "error",
          data: null,
          error: err instanceof Error ? err.message : "未知错误",
        });
      }
    },
    []
  );

  const loadDemo = useCallback(async () => {
    setState({ status: "loading", data: null, error: null });
    setDualData(null);
    try {
      const res = await fetch("/api/demo");
      if (!res.ok) throw new Error("Demo 加载失败");
      const data: ReviewResponse = await res.json();
      setState({ status: "success", data, error: null });
    } catch (err) {
      setState({
        status: "error",
        data: null,
        error: err instanceof Error ? err.message : "Demo 加载失败",
      });
    }
  }, []);

  const reset = useCallback(() => {
    setState({ status: "idle", data: null, error: null });
    setDualData(null);
  }, []);

  return { ...state, dualData, submitReview, submitDualReview, loadDemo, reset };
}
