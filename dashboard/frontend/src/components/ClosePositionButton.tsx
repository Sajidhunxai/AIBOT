"use client";

import { postApi } from "@/lib/api";

export function ClosePositionButton({
  positionId,
  symbol,
}: {
  positionId: string;
  symbol: string;
}) {
  const close = async () => {
    try {
      const body = positionId ? { position_id: positionId } : { symbol };
      const result = await postApi<{
        message: string;
        balance: number;
        total_pnl: number;
      }>("/controls/close", body);
      alert(`${result.message}\nNew balance: $${result.balance.toFixed(2)}`);
      window.location.reload();
    } catch (e) {
      alert(`Close failed: ${e instanceof Error ? e.message : "Unknown error"}`);
    }
  };

  return (
    <button onClick={close} className="btn btn-danger btn-sm">
      Close
    </button>
  );
}
