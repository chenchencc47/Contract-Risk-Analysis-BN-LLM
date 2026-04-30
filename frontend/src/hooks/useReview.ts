import { useState, useCallback } from "react";
import type { ReviewResponse, ReviewState } from "../types";

export function useReview() {
  const [state, setState] = useState<ReviewState>({
    status: "idle",
    data: null,
    error: null,
  });

  const submitReview = useCallback(
    async (contractText: string, contractId: string, reviewParty: "buyer" | "seller" = "buyer") => {
      if (!contractText.trim()) return;
      setState({ status: "loading", data: null, error: null });
      try {
        const res = await fetch("/api/review", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            contract_text: contractText,
            contract_id: contractId,
            review_party: reviewParty,
            generation_mode: "v2_combined",
          }),
        });
        if (!res.ok) {
          const errBody = await res.json().catch(() => null);
          throw new Error(
            errBody?.error || `服务器错误 (${res.status})`
          );
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

  const reset = useCallback(() => {
    setState({ status: "idle", data: null, error: null });
  }, []);

  return { ...state, submitReview, reset };
}
