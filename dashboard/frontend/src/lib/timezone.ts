import type { Time } from "lightweight-charts";
import { TickMarkType } from "lightweight-charts";

export const PAKISTAN_TIMEZONE = "Asia/Karachi";
export const PAKISTAN_LOCALE = "en-PK";

export function timeToDate(time: Time): Date {
  if (typeof time === "number") {
    return new Date(time * 1000);
  }
  if (typeof time === "string") {
    return new Date(time);
  }
  return new Date(Date.UTC(time.year, time.month - 1, time.day));
}

export function formatPakistanTime(
  value: string | Date | number,
  options?: Intl.DateTimeFormatOptions,
): string {
  const date =
    typeof value === "number"
      ? new Date(value > 1e12 ? value : value * 1000)
      : new Date(value);
  return new Intl.DateTimeFormat(PAKISTAN_LOCALE, {
    timeZone: PAKISTAN_TIMEZONE,
    ...options,
  }).format(date);
}

export function formatPakistanDate(value: string | Date | number): string {
  return formatPakistanTime(value, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatPakistanClock(value: string | Date | number): string {
  return formatPakistanTime(value, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function chartLocalization() {
  return {
    locale: PAKISTAN_LOCALE,
    timeFormatter: (time: Time) =>
      formatPakistanTime(timeToDate(time), {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }),
    dateFormat: "dd MMM 'yy",
  };
}

export function chartTickMarkFormatter() {
  return (time: Time, tickMarkType: TickMarkType): string | null => {
    const date = timeToDate(time);
    switch (tickMarkType) {
      case TickMarkType.Year:
        return formatPakistanTime(date, { year: "numeric" });
      case TickMarkType.Month:
        return formatPakistanTime(date, { month: "short", year: "2-digit" });
      case TickMarkType.DayOfMonth:
        return formatPakistanTime(date, { day: "numeric", month: "short" });
      case TickMarkType.TimeWithSeconds:
        return formatPakistanTime(date, {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
        });
      case TickMarkType.Time:
      default:
        return formatPakistanTime(date, {
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        });
    }
  };
}

const TIMEFRAME_MS: Record<string, number> = {
  "1m": 60_000,
  "5m": 5 * 60_000,
  "15m": 15 * 60_000,
  "1h": 60 * 60_000,
  "4h": 4 * 60 * 60_000,
};

export function timeframeToMs(timeframe: string): number {
  return TIMEFRAME_MS[timeframe] ?? 15 * 60_000;
}

export function getNextCandleCloseMs(timeframe: string, now = new Date()): number {
  const intervalMs = timeframeToMs(timeframe);
  const nowMs = now.getTime();
  return Math.ceil(nowMs / intervalMs) * intervalMs;
}

export function getMsUntilCandleClose(timeframe: string, now = new Date()): number {
  return getNextCandleCloseMs(timeframe, now) - now.getTime();
}

export function formatCountdown(totalMs: number): string {
  const totalSec = Math.max(0, Math.ceil(totalMs / 1000));
  const hours = Math.floor(totalSec / 3600);
  const minutes = Math.floor((totalSec % 3600) / 60);
  const seconds = totalSec % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}
