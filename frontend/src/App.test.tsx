import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import * as api from './api'

vi.mock('@auth0/auth0-react', () => ({
  useAuth0: () => ({
    isAuthenticated: true,
    isLoading: false,
    user: { email: 'acme-demo@pkgintel-app.dev', org_id: 'org_CZKzkSVB0Hbngqd9' },
    loginWithRedirect: vi.fn(),
    logout: vi.fn(),
    getAccessTokenSilently: vi.fn().mockResolvedValue('fake-token'),
  }),
}))

describe('Dashboard', () => {
  it('asks a question and shows the tenant-scoped answer', async () => {
    vi.spyOn(api, 'askQuestion').mockResolvedValue({
      answer: 'httpx is the next generation HTTP client.',
      cited_packages: ['httpx'],
    })

    const user = userEvent.setup()
    render(<App />)

    await user.type(
      screen.getByRole('textbox', { name: /ask about your tenant/i }),
      'What does httpx do?',
    )
    await user.click(screen.getByRole('button', { name: /^ask$/i }))

    expect(await screen.findByText(/next generation HTTP client/i)).toBeInTheDocument()
    expect(screen.getByText(/cited: httpx/i)).toBeInTheDocument()
    expect(api.askQuestion).toHaveBeenCalledWith('fake-token', 'What does httpx do?')
  })

  it('looks up the shared dependency graph', async () => {
    vi.spyOn(api, 'getDependents').mockResolvedValue({
      target: 'certifi',
      dependents: ['httpx', 'requests'],
    })

    const user = userEvent.setup()
    render(<App />)

    await user.type(screen.getByRole('textbox', { name: /who depends on/i }), 'certifi')
    await user.click(screen.getByRole('button', { name: /^look up$/i }))

    await waitFor(() =>
      expect(screen.getByText(/httpx, requests depend on certifi/i)).toBeInTheDocument(),
    )
  })
})
