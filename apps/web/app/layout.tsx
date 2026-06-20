import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "TopoAudit Bénin",
  description: "Prototype SaaS local pour audit préliminaire de plans topographiques."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
