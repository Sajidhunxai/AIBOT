"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchApi, postApi } from "@/lib/api";

export function BotControls({ running: initialRunning }: { running: boolean }) {
  const [running, setRunning] = useState(initialRunning);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const refreshStatus = useCallback(async () => {
    try {
      const status = await fetchApi<{ running: boolean }>("/status");
      setRunning(status.running);
    } catch {
      setRunning(false);
    }
  }, []);

  useEffect(() => {
    setRunning(initialRunning);
  }, [initialRunning]);

  useEffect(() => {
    void refreshStatus();
    const onChange = () => void refreshStatus();
    window.addEventListener("bot-status-changed", onChange);
    const interval = setInterval(refreshStatus, 5000);
    return () => {
      window.removeEventListener("bot-status-changed", onChange);
      clearInterval(interval);
    };
  }, [refreshStatus]);

  const notifyStatusChange = () => {
    window.dispatchEvent(new CustomEvent("bot-status-changed"));
    window.dispatchEvent(new CustomEvent("account-switched"));
  };

  const toggle = async () => {
    setBusy(true);
    setMessage("");
    try {
      if (running) {
        await postApi("/controls/stop");
        setRunning(false);
        setMessage("Stopped all trading accounts.");
      } else {
        const result = await postApi<{ status: string }>("/controls/start");
        setRunning(true);
        setMessage(
          result.status === "already_running"
            ? "Active account is already trading."
            : "Trading started on active account.",
        );
      }
      notifyStatusChange();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bot-controls">
      <button
        type="button"
        onClick={() => void toggle()}
        className={`btn ${running ? "btn-danger" : "btn-primary"}`}
        disabled={busy}
      >
        {busy ? "…" : running ? "Stop" : "Start"}
      </button>
      {message && <p className="trade-message">{message}</p>}
    </div>
  );
}
