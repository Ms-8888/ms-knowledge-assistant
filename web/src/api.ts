export type Citation = {
  source: string
  heading: string | null
  page: number | null
  score: number
  text: string
}

export type AskResponse = {
  answered: boolean
  answer: string
  confidence: number
  backend: string
  citations: Citation[]
}

export type QuestionRow = {
  id: number
  question: string
  answered: boolean
  confidence: number
  backend: string
  created_at: string
}

export type Stats = {
  total: number
  answered: number
  unanswered: number
  low_confidence: number
}

export type QuestionFilter = 'all' | 'unanswered' | 'low_confidence'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, init)
  } catch {
    throw new ApiError(0, 'De server is niet bereikbaar.')
  }
  if (!response.ok) {
    let detail = 'Er ging iets mis.'
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // keep the generic message
    }
    throw new ApiError(response.status, detail)
  }
  return response.json() as Promise<T>
}

export function ask(question: string): Promise<AskResponse> {
  return request<AskResponse>('/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
}

export function listQuestions(adminKey: string, filter: QuestionFilter): Promise<QuestionRow[]> {
  return request<QuestionRow[]>(`/admin/questions?filter=${filter}`, {
    headers: { 'X-Admin-Key': adminKey },
  })
}

export function getStats(adminKey: string): Promise<Stats> {
  return request<Stats>('/admin/stats', { headers: { 'X-Admin-Key': adminKey } })
}
