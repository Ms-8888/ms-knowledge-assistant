import { useState } from 'react'
import Admin from './Admin'
import Ask from './Ask'

type Tab = 'ask' | 'admin'

export default function App() {
  const [tab, setTab] = useState<Tab>('ask')

  return (
    <main>
      <header>
        <h1>Kennisassistent</h1>
        <p className="meta">Demo met fictieve bedrijfsdocumenten van Brouwer &amp; Zonen NV.</p>
        <nav>
          <button
            type="button"
            className={tab === 'ask' ? 'tab active' : 'tab'}
            onClick={() => setTab('ask')}
          >
            Vragen
          </button>
          <button
            type="button"
            className={tab === 'admin' ? 'tab active' : 'tab'}
            onClick={() => setTab('admin')}
          >
            Beheer
          </button>
        </nav>
      </header>
      {tab === 'ask' ? <Ask /> : <Admin />}
    </main>
  )
}
