const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

export interface AnswerResponse {
  answer: string
  cited_packages: string[]
}

export interface DependentsResponse {
  target: string
  dependents: string[]
}

export interface ProblemDetail {
  type: string
  title: string
  status: number
  detail: string
}

export class ApiError extends Error {
  problem: ProblemDetail

  constructor(problem: ProblemDetail) {
    super(problem.detail)
    this.problem = problem
  }
}

async function withAuth<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...init.headers,
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new ApiError((await response.json()) as ProblemDetail)
  }
  return (await response.json()) as T
}

export function askQuestion(token: string, question: string): Promise<AnswerResponse> {
  return withAuth<AnswerResponse>('/v1/questions', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
}

export function getDependents(token: string, packageName: string): Promise<DependentsResponse> {
  return withAuth<DependentsResponse>(
    `/v1/packages/${encodeURIComponent(packageName)}/dependents`,
    token,
  )
}
