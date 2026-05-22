import { describe, it, expect, vi, afterEach } from 'vitest'
import { fetchConfig, DEFAULT_CONFIG } from '../api.js'

describe('fetchConfig', () => {
  afterEach(() => vi.restoreAllMocks())

  it('returns DEFAULT_CONFIG on 404', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }))
    const config = await fetchConfig('widget-id', 'http://localhost:8000')
    expect(config).toEqual(DEFAULT_CONFIG)
  })

  it('returns DEFAULT_CONFIG when fetch throws', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')))
    const config = await fetchConfig('widget-id', 'http://localhost:8000')
    expect(config).toEqual(DEFAULT_CONFIG)
  })

  it('returns parsed config on 200', async () => {
    const mockConfig = { theme: 'light', greeting: 'Hi', enabled_tools: [] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue(mockConfig),
    }))
    const config = await fetchConfig('widget-id', 'http://localhost:8000')
    expect(config).toEqual(mockConfig)
  })
})
