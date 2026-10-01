// 보드(폴더) 그룹핑/재정렬 순수 로직.
// React·브라우저 API에 의존하지 않는다 → vitest로 단독 테스트.
// 모든 함수는 불변(immutable): 입력 보드를 수정하지 않고 새 보드를 반환한다.

export const INBOX_ID = 'inbox'

export interface Column {
  id: string
  title: string
  /** 레포 식별자 (`owner/name`) — 표시 순서 그대로 */
  repoIds: string[]
}

export interface Board {
  version: 1
  columns: Column[]
}

export function createBoard(repoIds: string[] = []): Board {
  return {
    version: 1,
    columns: [{ id: INBOX_ID, title: '미분류', repoIds: dedupe(repoIds) }],
  }
}

function dedupe(ids: string[]): string[] {
  return [...new Set(ids)]
}

export function findColumnOf(board: Board, repoId: string): Column | undefined {
  return board.columns.find((c) => c.repoIds.includes(repoId))
}

export function addColumn(board: Board, id: string, title: string): Board {
  if (board.columns.some((c) => c.id === id)) {
    throw new Error(`이미 존재하는 컬럼: ${id}`)
  }
  return { ...board, columns: [...board.columns, { id, title, repoIds: [] }] }
}

export function renameColumn(board: Board, id: string, title: string): Board {
  return {
    ...board,
    columns: board.columns.map((c) => (c.id === id ? { ...c, title } : c)),
  }
}

/** 컬럼 삭제. 안에 있던 레포는 사라지지 않고 미분류(inbox) 끝으로 이동한다. */
export function removeColumn(board: Board, id: string): Board {
  if (id === INBOX_ID) throw new Error('미분류 컬럼은 삭제할 수 없음')
  const target = board.columns.find((c) => c.id === id)
  if (!target) return board
  return {
    ...board,
    columns: board.columns
      .filter((c) => c.id !== id)
      .map((c) =>
        c.id === INBOX_ID ? { ...c, repoIds: [...c.repoIds, ...target.repoIds] } : c,
      ),
  }
}

/**
 * 레포를 `toColumnId` 컬럼의 `toIndex` 위치로 이동 (같은 컬럼 내 재정렬 포함).
 * toIndex는 이동 후 기준 인덱스이며 범위를 벗어나면 끝/처음으로 clamp.
 */
export function moveRepo(
  board: Board,
  repoId: string,
  toColumnId: string,
  toIndex: number,
): Board {
  if (!board.columns.some((c) => c.id === toColumnId)) {
    throw new Error(`없는 컬럼: ${toColumnId}`)
  }
  if (!findColumnOf(board, repoId)) return board
  const columns = board.columns.map((c) => ({
    ...c,
    repoIds: c.repoIds.filter((r) => r !== repoId),
  }))
  return {
    ...board,
    columns: columns.map((c) => {
      if (c.id !== toColumnId) return c
      const idx = Math.max(0, Math.min(toIndex, c.repoIds.length))
      const repoIds = [...c.repoIds]
      repoIds.splice(idx, 0, repoId)
      return { ...c, repoIds }
    }),
  }
}

/** 컬럼 자체의 순서 변경 */
export function moveColumn(board: Board, columnId: string, toIndex: number): Board {
  const from = board.columns.findIndex((c) => c.id === columnId)
  if (from < 0) return board
  const columns = [...board.columns]
  const [col] = columns.splice(from, 1)
  const idx = Math.max(0, Math.min(toIndex, columns.length))
  columns.splice(idx, 0, col)
  return { ...board, columns }
}

/**
 * GitHub에서 가져온 최신 레포 목록과 보드를 동기화.
 * - 새로 생긴 레포 → 미분류 끝에 추가
 * - GitHub에서 사라진(삭제/이전) 레포 → 보드에서 제거
 * - 기존 배치·순서는 유지
 */
export function syncRepos(board: Board, currentRepoIds: string[]): Board {
  const current = new Set(currentRepoIds)
  const placed = new Set(board.columns.flatMap((c) => c.repoIds))
  const added = dedupe(currentRepoIds).filter((r) => !placed.has(r))
  return {
    ...board,
    columns: board.columns.map((c) => {
      const kept = c.repoIds.filter((r) => current.has(r))
      return c.id === INBOX_ID ? { ...c, repoIds: [...kept, ...added] } : { ...c, repoIds: kept }
    }),
  }
}

// ---- 자동 그룹 제안 (드래그 전에 1차 정리용) ----

export interface RepoMeta {
  id: string
  language: string | null
  archived: boolean
  fork: boolean
  /** ISO8601 */
  pushedAt: string
}

export type GroupKey = 'language' | 'activity' | 'kind'

/** 메타데이터 기준으로 레포를 그룹으로 나눈다. 결과는 그룹명 오름차순, 그룹 내부는 입력 순서 유지. */
export function groupRepos(
  repos: RepoMeta[],
  key: GroupKey,
  now: Date = new Date(),
): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  for (const r of repos) {
    const g = groupLabel(r, key, now)
    ;(out[g] ??= []).push(r.id)
  }
  return Object.fromEntries(Object.entries(out).sort(([a], [b]) => a.localeCompare(b)))
}

const DAY_MS = 24 * 60 * 60 * 1000

function groupLabel(r: RepoMeta, key: GroupKey, now: Date): string {
  switch (key) {
    case 'language':
      return r.language ?? '(없음)'
    case 'kind':
      return r.archived ? 'archived' : r.fork ? 'fork' : 'source'
    case 'activity': {
      const days = (now.getTime() - new Date(r.pushedAt).getTime()) / DAY_MS
      if (days <= 30) return '1-active (30일 이내)'
      if (days <= 365) return '2-recent (1년 이내)'
      return '3-stale (1년 초과)'
    }
  }
}

/** 그룹 제안을 보드에 적용: 그룹마다 컬럼을 만들고 레포를 이동 (기존 컬럼 이름과 겹치면 재사용). */
export function applyGrouping(board: Board, groups: Record<string, string[]>): Board {
  let next = board
  for (const [title, ids] of Object.entries(groups)) {
    let col = next.columns.find((c) => c.title === title)
    if (!col) {
      const id = `col-${slug(title)}`
      next = addColumn(next, id, title)
      col = next.columns.find((c) => c.id === id)!
    }
    for (const id of ids) {
      next = moveRepo(next, id, col.id, Number.MAX_SAFE_INTEGER)
    }
  }
  return next
}

function slug(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9가-힣]+/g, '-').replace(/^-|-$/g, '') || 'group'
}

// ---- 직렬화 (localStorage / JSON 내보내기·가져오기) ----

export function serializeBoard(board: Board): string {
  return JSON.stringify(board, null, 2)
}

export function parseBoard(json: string): Board {
  const data = JSON.parse(json) as Partial<Board>
  if (data.version !== 1 || !Array.isArray(data.columns)) {
    throw new Error('지원하지 않는 보드 형식')
  }
  if (!data.columns.some((c) => c.id === INBOX_ID)) {
    throw new Error('미분류(inbox) 컬럼이 없음')
  }
  // 같은 레포가 여러 컬럼에 있으면 첫 번째만 남긴다
  const seen = new Set<string>()
  const columns = data.columns.map((c) => ({
    id: String(c.id),
    title: String(c.title),
    repoIds: c.repoIds.filter((r) => (seen.has(r) ? false : (seen.add(r), true))),
  }))
  return { version: 1, columns }
}
