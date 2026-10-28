import { useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, getStats, listQuestions } from './api'
import type { QuestionFilter, QuestionRow, Stats } from './api'

const FILTERS: { value: QuestionFilter; label: string }[] = [
  { value: 'all', label: 'Alle' },
  { value: 'unanswered', label: 'Onbeantwoord' },
  { value: 'low_confidence', label: 'Lage zekerheid' },
]

export default function Admin() {
  const [adminKey, setAdminKey] = useState('')
  const [connected, setConnected] = useState(false)
  const [filter, setFilter] = useState<QuestionFilter>('unanswered')
  const [rows, setRows] = useState<QuestionRow[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function load(key: string, chosen: QuestionFilter) {
    setLoading(true)
    setError(null)
    try {
      const [list, summary] = await Promise.all([listQuestions(key, chosen), getStats(key)])
      setRows(list)
      setStats(summary)
      setConnected(true)
    } catch (e) {
      setConnected(false)
      setError(e instanceof ApiError ? e.message : 'Er ging iets mis.')
    } finally {
      setLoading(false)
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    void load(adminKey, filter)
  }

  function choose(value: QuestionFilter) {
    setFilter(value)
    if (connected) void load(adminKey, value)
  }

  return (
    <section>
      <form onSubmit={onSubmit} className="ask-form">
        <label htmlFor="admin-key">Admin-sleutel</label>
        <div className="row">
          <input
            id="admin-key"
            type="password"
            value={adminKey}
            onChange={(e) => setAdminKey(e.target.value)}
            autoComplete="off"
          />
          <button type="submit" disabled={loading || adminKey.length === 0}>
            {loading ? 'Bezig…' : 'Openen'}
          </button>
        </div>
      </form>

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      {connected && stats && (
        <>
          <p className="meta">
            {stats.total} vragen · {stats.answered} beantwoord · {stats.unanswered} onbeantwoord ·{' '}
            {stats.low_confidence} met lage zekerheid
          </p>
          <div className="examples">
            {FILTERS.map((f) => (
              <button
                key={f.value}
                type="button"
                className={f.value === filter ? 'chip active' : 'chip'}
                onClick={() => choose(f.value)}
              >
                {f.label}
              </button>
            ))}
          </div>
          {rows.length === 0 ? (
            <p className="meta">Geen vragen gevonden voor dit filter.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Vraag</th>
                  <th>Status</th>
                  <th>Score</th>
                  <th>Tijd</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.question}</td>
                    <td>{row.answered ? 'Beantwoord' : 'Onbeantwoord'}</td>
                    <td>{Math.round(row.confidence * 100)}%</td>
                    <td>{new Date(row.created_at).toLocaleString('nl-BE')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  )
}
