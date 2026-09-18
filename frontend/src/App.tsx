import { useCallback, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { ApiError, askQuestion, getDependents, getUsage, type UsageResponse } from './api'

const ACME_ORG_ID = import.meta.env.VITE_AUTH0_ACME_ORG_ID
const GLOBEX_ORG_ID = import.meta.env.VITE_AUTH0_GLOBEX_ORG_ID

function initialsOf(name: string | undefined): string {
  if (!name) return '?'
  return name.slice(0, 1).toUpperCase()
}

function Header() {
  const { isAuthenticated, isLoading, user, loginWithRedirect, logout } = useAuth0()

  return (
    <header className="header">
      <div className="brand">
        <div className="brand-mark" aria-hidden="true" />
        <div className="brand-text">
          <span className="brand-name">PkgIntel</span>
          <span className="brand-tag">package dependency intelligence, per tenant</span>
        </div>
      </div>
      <div className="header-actions">
        {isAuthenticated && (
          <div className="user-chip">
            <span className="avatar">{initialsOf(user?.name ?? user?.email)}</span>
            <span>{user?.email}</span>
            {typeof user?.org_id === 'string' && (
              <span className="badge badge-no_action">{user.org_id === ACME_ORG_ID ? 'Acme' : 'Globex'}</span>
            )}
          </div>
        )}
        {!isLoading && isAuthenticated && (
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
          >
            Log out
          </button>
        )}
        {!isLoading && !isAuthenticated && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => loginWithRedirect()}
          >
            Sign in
          </button>
        )}
      </div>
    </header>
  )
}

function QuestionForm({ onUsage }: { onUsage: (usage: UsageResponse) => void }) {
  const { getAccessTokenSilently } = useAuth0()
  const [question, setQuestion] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [answer, setAnswer] = useState<
    { answer: string; citedPackages: string[]; cached: boolean; costUsd: number } | null
  >(null)

  const handleSubmit = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault()
      if (!question.trim()) return

      setSubmitting(true)
      setError(null)
      setAnswer(null)
      try {
        const token = await getAccessTokenSilently()
        if (!token) throw new Error('No access token available.')
        const result = await askQuestion(token, question.trim())
        setAnswer({
          answer: result.answer,
          citedPackages: result.cited_packages,
          cached: result.cached,
          costUsd: result.cost_usd,
        })
        // A cache hit or miss both change this tenant's own usage
        // ledger (chapter 15), a hit just adds a zero-cost call to it.
        onUsage(await getUsage(token))
      } catch (err) {
        setError(err instanceof ApiError ? err.problem.detail : 'The question could not be sent.')
      } finally {
        setSubmitting(false)
      }
    },
    [question, getAccessTokenSilently, onUsage],
  )

  return (
    <form className="card request-form" onSubmit={handleSubmit}>
      <label htmlFor="question">Ask about your tenant's packages</label>
      <div className="request-row">
        <input
          id="question"
          type="text"
          placeholder="What does httpx do?"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          disabled={submitting}
        />
        <button type="submit" className="btn btn-primary" disabled={submitting || !question.trim()}>
          {submitting && <span className="spinner" aria-hidden="true" />}
          {submitting ? 'Asking' : 'Ask'}
        </button>
      </div>
      {error && <p className="form-error">{error}</p>}
      {answer && (
        <div className="queue-answer">
          <p>{answer.answer}</p>
          {answer.citedPackages.length > 0 && (
            <p className="thread-id">Cited: {answer.citedPackages.join(', ')}</p>
          )}
          <p className="thread-id">
            {answer.cached
              ? 'Served from cache, $0.0000'
              : `Real model call, $${answer.costUsd.toFixed(6)}`}
          </p>
        </div>
      )}
    </form>
  )
}

function UsagePanel({ usage }: { usage: UsageResponse | null }) {
  if (usage === null) return null
  return (
    <div className="card queue-item">
      <div className="queue-item-top">
        <div className="queue-question">This tenant's usage</div>
        <span className="badge badge-no_action">
          {usage.cache_hit_count}/{usage.call_count} cached
        </span>
      </div>
      <p className="queue-answer">Total real spend so far: ${usage.total_cost_usd.toFixed(6)}</p>
    </div>
  )
}

function DependentsLookup() {
  const { getAccessTokenSilently } = useAuth0()
  const [packageName, setPackageName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ target: string; dependents: string[] } | null>(null)

  const handleSubmit = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault()
      if (!packageName.trim()) return

      setBusy(true)
      setError(null)
      setResult(null)
      try {
        const token = await getAccessTokenSilently()
        if (!token) throw new Error('No access token available.')
        const response = await getDependents(token, packageName.trim())
        setResult(response)
      } catch (err) {
        setError(err instanceof ApiError ? err.problem.detail : 'The lookup failed.')
      } finally {
        setBusy(false)
      }
    },
    [packageName, getAccessTokenSilently],
  )

  return (
    <form className="card request-form" onSubmit={handleSubmit}>
      <label htmlFor="package">Who depends on this package? (shared graph, every tenant)</label>
      <div className="request-row">
        <input
          id="package"
          type="text"
          placeholder="certifi"
          value={packageName}
          onChange={(event) => setPackageName(event.target.value)}
          disabled={busy}
        />
        <button type="submit" className="btn btn-primary" disabled={busy || !packageName.trim()}>
          {busy && <span className="spinner" aria-hidden="true" />}
          {busy ? 'Looking up' : 'Look up'}
        </button>
      </div>
      {error && <p className="form-error">{error}</p>}
      {result && (
        <div className="queue-answer">
          {result.dependents.length === 0 ? (
            <p>Nothing in the graph depends on {result.target}.</p>
          ) : (
            <p>{result.dependents.join(', ')} depend on {result.target}.</p>
          )}
        </div>
      )}
    </form>
  )
}

function Dashboard() {
  const [usage, setUsage] = useState<UsageResponse | null>(null)

  return (
    <main className="main">
      <div className="page-heading">
        <h1>Package intelligence</h1>
        <p>Questions reach only your own tenant's collection. The dependency graph is shared.</p>
      </div>
      <QuestionForm onUsage={setUsage} />
      <UsagePanel usage={usage} />
      <DependentsLookup />
    </main>
  )
}

function SignedOutGate() {
  const { loginWithRedirect } = useAuth0()
  return (
    <main className="main">
      <div className="gate">
        <div className="brand-mark" aria-hidden="true" style={{ width: 44, height: 44 }} />
        <h1 className="gate-title">Sign in to your organization</h1>
        <p className="gate-subtitle">
          Each organization only ever sees its own ingested packages. Pick the one you belong to.
        </p>
        <div className="header-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() =>
              loginWithRedirect({ authorizationParams: { organization: ACME_ORG_ID } })
            }
          >
            Sign in to Acme
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() =>
              loginWithRedirect({ authorizationParams: { organization: GLOBEX_ORG_ID } })
            }
          >
            Sign in to Globex
          </button>
        </div>
      </div>
    </main>
  )
}

function App() {
  const { isAuthenticated, isLoading } = useAuth0()

  return (
    <div className="shell">
      <Header />
      {isLoading ? null : isAuthenticated ? <Dashboard /> : <SignedOutGate />}
    </div>
  )
}

export default App
