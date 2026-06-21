import dynamic from "next/dynamic";

const TopoAuditDashboard = dynamic(() => import("./components/TopoAuditDashboard"), { ssr: false });

export default function Home() {
  return <TopoAuditDashboard />;
}
