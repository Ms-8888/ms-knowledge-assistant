import { useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, ask } from './api'
import type { AskResponse } from './api'

const EXAMPLES = [
  'Hoeveel vakantiedagen heb ik per jaar?',
  'Mag ik van thuis werken?',
  'Wat moet ik doen bij phishing?',
]

export default function Ask() {
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AskResponse | null>(null)

  async function submit(text: string) {
    const trimmed = text.trim()
    if (trimmed.length < 3) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      setResult(await ask(trimmed))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Er ging iets mis.')
    } finally {
      setLoading(false)
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    void submit(question)
  }

  return (
    <section>
      <form onSubmit={onSubmit} className="ask-form">
        <label htmlFor="question">Stel een vraag over de bedrijfsdocumenten</label>
        <div className="row">
          <input
            id="question"
            value={question}
            maxLength={500}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Bijvoorbeeld: Hoeveel vakantiedagen heb ik?"
            autoComplete="off"
          />
          <button type="submit" disabled={loading || question.trim().length < 3}>
            {loading ? 'Bezig…' : 'Vraag'}
          </button>
        </div>
      </form>

      <div className="examples">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            className="chip"
            disabled={loading}
            onClick={() => {
              setQuestion(example)
              void submit(example)
            }}
          >
            {example}
          </button>
        ))}
      </div>

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      {result && (
        <article className={result.answered ? 'answer' : 'answer unknown'}>
          {result.answered && result.backend === 'extractive' && (
            <p className="meta">Meest relevante passage (zonder taalmodel, dus geen samengesteld antwoord):</p>
          )}
          <p className="answer-text">{result.answer}</p>
          {result.answered && (
            <p className="meta">
              Zekerheid (zoekscore): {Math.round(result.confidence * 100)}% · modus: {result.backend}
            </p>
          )}
          {result.citations.length > 0 && (
            <>
              <h2>Bronnen</h2>
              <ul className="citations">
                {result.citations.map((c, index) => (
                  <li key={`${c.source}-${index}`}>
                    <strong>{c.source}</strong>
                    {c.heading ? ` · ${c.heading}` : ''}
                    {c.page ? ` · pagina ${c.page}` : ''}
                    <span className="score"> ({Math.round(c.score * 100)}%)</span>
                    <p>{c.text}</p>
                  </li>
                ))}
              </ul>
            </>
          )}
        </article>
      )}
    </section>
  )
}
