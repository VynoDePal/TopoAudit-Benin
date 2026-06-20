const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

export default function Home() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">Prototype local</p>
        <h1>TopoAudit Bénin</h1>
        <p>
          Importez un plan topographique scanné, validez les coordonnées extraites,
          puis générez un audit préliminaire de cohérence technique.
        </p>
        <div className="cards">
          <a href={`${apiBaseUrl}/docs`} className="card">
            <span>Backend FastAPI</span>
            <strong>Swagger sur :8000/api/docs</strong>
          </a>
          <div className="card">
            <span>Frontend Next.js</span>
            <strong>Disponible sur :3000</strong>
          </div>
        </div>
      </section>
    </main>
  );
}
