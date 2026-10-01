// GitHub REST 클라이언트 (읽기 전용).
// 인증: fine-grained PAT — Repository access "All repositories", 권한 Metadata: Read-only 만으로 충분.
// 토큰은 브라우저 localStorage에만 보관하고 외부로 보내지 않는다 (api.github.com 제외).

import type { RepoMeta } from './board'

export interface Repo extends RepoMeta {
  name: string
  fullName: string
  description: string | null
  htmlUrl: string
  private: boolean
  stars: number
}

interface ApiRepo {
  full_name: string
  name: string
  description: string | null
  html_url: string
  private: boolean
  fork: boolean
  archived: boolean
  language: string | null
  pushed_at: string
  stargazers_count: number
}

export function toRepo(r: ApiRepo): Repo {
  return {
    id: r.full_name,
    name: r.name,
    fullName: r.full_name,
    description: r.description,
    htmlUrl: r.html_url,
    private: r.private,
    fork: r.fork,
    archived: r.archived,
    language: r.language,
    pushedAt: r.pushed_at,
    stars: r.stargazers_count,
  }
}

/** Link 헤더에서 rel="next" URL 추출 (없으면 null) */
export function parseNextLink(link: string | null): string | null {
  if (!link) return null
  for (const part of link.split(',')) {
    const m = part.match(/<([^>]+)>;\s*rel="next"/)
    if (m) return m[1]
  }
  return null
}

/** 인증 사용자의 모든 레포 (소유 + 협업 + 조직) — 페이지네이션 처리 */
export async function fetchAllRepos(token: string, fetchImpl: typeof fetch = fetch): Promise<Repo[]> {
  const out: Repo[] = []
  let url: string | null =
    'https://api.github.com/user/repos?per_page=100&sort=pushed&affiliation=owner,collaborator,organization_member'
  while (url) {
    const res: Response = await fetchImpl(url, {
      headers: {
        Accept: 'application/vnd.github+json',
        Authorization: `Bearer ${token}`,
        'X-GitHub-Api-Version': '2022-11-28',
      },
    })
    if (!res.ok) throw new Error(`GitHub API ${res.status}: ${await res.text()}`)
    out.push(...((await res.json()) as ApiRepo[]).map(toRepo))
    url = parseNextLink(res.headers.get('Link'))
  }
  return out
}
