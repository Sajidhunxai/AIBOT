import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AIBotTrade Dashboard",
  description: "Binance Futures Trading Bot Dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav className="navbar">
          <div className="nav-brand">AIBotTrade</div>
          <div className="nav-links">
            <a href="/">Dashboard</a>
          </div>
        </nav>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
