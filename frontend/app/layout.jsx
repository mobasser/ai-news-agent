import "./globals.css";

export const metadata = { title: "Daily AI Briefing" };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
