import { useAuth } from '../auth/useAuth'

function DashboardPage() {
  const { user } = useAuth()

  return (
    <div className="page dashboard-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">
            Übersicht
          </p>

          <h1>Dashboard</h1>

          <p className="muted">
            Willkommen, {user?.first_name}.
          </p>
        </div>
      </header>

      <section className="dashboard-grid">
        <article className="card">
          <p className="eyebrow">
            Status
          </p>

          <h2>Web-Interface aktiv</h2>

          <p className="muted">
            Anmeldung, Sitzungsprüfung und
            geschütztes Routing funktionieren.
          </p>
        </article>

        <article className="card">
          <p className="eyebrow">
            Nächster Schritt
          </p>

          <h2>Rechnungsverwaltung</h2>

          <p className="muted">
            Als Nächstes binden wir die
            Rechnungsübersicht an das Backend an.
          </p>
        </article>
      </section>
    </div>
  )
}

export default DashboardPage
