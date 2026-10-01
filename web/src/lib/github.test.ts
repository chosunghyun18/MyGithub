import { describe, expect, it } from 'vitest'
import { fetchAllRepos, parseNextLink } from './github'

const apiRepo = (n: string) => ({
  full_name: `me/${n}`,
  name: n,
  description: null,
  html_url: `https://github.com/me/${n}`,
  private: false,
  fork: false,
  archived: false,
  language: 'Python',
  pushed_at: '2026-09-01T00:00:00Z',
  stargazers_count: 0,
})

describe('github', () => {
  it('Link 헤더 next 파싱', () => {
    const link =
      '<https://api.github.com/user/repos?page=2>; rel="next", <https://api.github.com/user/repos?page=5>; rel="last"'
    expect(parseNextLink(link)).toBe('https://api.github.com/user/repos?page=2')
    expect(parseNextLink('<x>; rel="prev"')).toBeNull()
    expect(parseNextLink(null)).toBeNull()
  })

  it('페이지네이션을 따라 모든 레포를 모은다', async () => {
    const pages: Record<string, { body: unknown; link: string | null }> = {
      first: { body: [apiRepo('a'), apiRepo('b')], link: '<https://api.github.com/p2>; rel="next"' },
      'https://api.github.com/p2': { body: [apiRepo('c')], link: null },
    }
    const fakeFetch = (async (url: string) => {
      const p = pages[url.startsWith('https://api.github.com/user/repos') ? 'first' : url]
      return new Response(JSON.stringify(p.body), {
        status: 200,
        headers: p.link ? { Link: p.link } : {},
      })
    }) as unknown as typeof fetch
    const repos = await fetchAllRepos('t', fakeFetch)
    expect(repos.map((r) => r.id)).toEqual(['me/a', 'me/b', 'me/c'])
  })
})
