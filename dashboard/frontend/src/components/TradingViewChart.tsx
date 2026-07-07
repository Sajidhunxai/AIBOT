"use client";

import { useEffect, useRef, useState } from "react";
import { buildTradingViewConfig, TRADINGVIEW_WIDGET_SCRIPT } from "@/lib/tradingview";

interface TradingViewChartProps {
  symbol: string;
  timeframe: string;
}

export function TradingViewChart({ symbol, timeframe }: TradingViewChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted || !containerRef.current) return;

    const container = containerRef.current;
    container.innerHTML = "";

    const wrapper = document.createElement("div");
    wrapper.className = "tradingview-widget-container";
    wrapper.style.height = "100%";
    wrapper.style.width = "100%";

    const widget = document.createElement("div");
    widget.className = "tradingview-widget-container__widget";
    widget.style.height = "100%";
    widget.style.width = "100%";
    wrapper.appendChild(widget);

    const script = document.createElement("script");
    script.type = "text/javascript";
    script.src = TRADINGVIEW_WIDGET_SCRIPT;
    script.async = true;
    script.textContent = JSON.stringify(buildTradingViewConfig(symbol, timeframe));
    wrapper.appendChild(script);

    container.appendChild(wrapper);

    return () => {
      container.innerHTML = "";
    };
  }, [mounted, symbol, timeframe]);

  if (!mounted) {
    return <div className="tradingview-chart-container tradingview-chart-loading">Loading chart…</div>;
  }

  return <div ref={containerRef} className="tradingview-chart-container" />;
}
