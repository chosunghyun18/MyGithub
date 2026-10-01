import { describe, expect, it } from 'vitest'
import {
  INBOX_ID,
  addColumn,
  applyGrouping,
  createBoard,
  groupRepos,
  moveColumn,
  moveRepo,
  parseBoard,
  removeColumn,
  serializeBoard,
  syncRepos,
  type RepoMeta,
} from './board'

const ids = (b: ReturnType<typeof createBoard>, col: string) =>
  b.columns.find((c) => c.id === col)!.repoIds

describe('board', () => {
  it('새 보드는 모든 레포를 미분류에 중복 없이 둔다', () => {
    const b = createBoard(['a/x', 'a/y', 'a/x'])
    expect(b.columns).toHaveLength(1)
    expect(ids(b, INBOX_ID)).toEqual(['a/x', 'a/y'])
  })

  it('다른 컬럼으로 이동 + 위치 지정', () => {
    let b = addColumn(createBoard(['a/1', 'a/2', 'a/3']), 'work', '업무')
    b = moveRepo(b, 'a/2', 'work', 0)
    b = moveRepo(b, 'a/3', 'work', 0)
    expect(ids(b, INBOX_ID)).toEqual(['a/1'])
    expect(ids(b, 'work')).toEqual(['a/3', 'a/2'])
  })

  it('같은 컬럼 내 재정렬, 인덱스는 clamp', () => {
    const b0 = createBoard(['a/1', 'a/2', 'a/3'])
    expect(ids(moveRepo(b0, 'a/1', INBOX_ID, 99), INBOX_ID)).toEqual(['a/2', 'a/3', 'a/1'])
    expect(ids(moveRepo(b0, 'a/3', INBOX_ID, -5), INBOX_ID)).toEqual(['a/3', 'a/1', 'a/2'])
  })

  it('입력 보드는 변경되지 않는다 (불변)', () => {
    const b0 = createBoard(['a/1', 'a/2'])
    const snapshot = JSON.stringify(b0)
    moveRepo(addColumn(b0, 'x', 'X'), 'a/1', 'x', 0)
    expect(JSON.stringify(b0)).toBe(snapshot)
  })

  it('없는 컬럼으로 이동하면 에러, 중복 컬럼 id도 에러', () => {
    const b = createBoard(['a/1'])
    expect(() => moveRepo(b, 'a/1', 'nope', 0)).toThrow()
    expect(() => addColumn(b, INBOX_ID, 'dup')).toThrow()
  })

  it('컬럼 삭제 시 레포는 미분류로 돌아간다', () => {
    let b = addColumn(createBoard(['a/1', 'a/2']), 'w', 'W')
    b = moveRepo(b, 'a/1', 'w', 0)
    b = removeColumn(b, 'w')
    expect(b.columns.map((c) => c.id)).toEqual([INBOX_ID])
    expect(ids(b, INBOX_ID)).toEqual(['a/2', 'a/1'])
    expect(() => removeColumn(b, INBOX_ID)).toThrow()
  })

  it('컬럼 순서 변경', () => {
    let b = addColumn(addColumn(createBoard(), 'a', 'A'), 'b', 'B')
    b = moveColumn(b, 'b', 0)
    expect(b.columns.map((c) => c.id)).toEqual(['b', INBOX_ID, 'a'])
  })

  it('sync: 신규 레포는 미분류 끝, 삭제된 레포는 제거, 배치 유지', () => {
    let b = addColumn(createBoard(['a/1', 'a/2', 'a/3']), 'w', 'W')
    b = moveRepo(b, 'a/1', 'w', 0)
    b = syncRepos(b, ['a/1', 'a/3', 'a/new'])
    expect(ids(b, 'w')).toEqual(['a/1'])
    expect(ids(b, INBOX_ID)).toEqual(['a/3', 'a/new'])
  })
})

describe('groupRepos / applyGrouping', () => {
  const now = new Date('2026-10-01T00:00:00Z')
  const repos: RepoMeta[] = [
    { id: 'a/ts', language: 'TypeScript', archived: false, fork: false, pushedAt: '2026-09-20T00:00:00Z' },
    { id: 'a/py', language: 'Python', archived: false, fork: true, pushedAt: '2026-01-01T00:00:00Z' },
    { id: 'a/old', language: null, archived: true, fork: false, pushedAt: '2020-01-01T00:00:00Z' },
  ]

  it('언어별', () => {
    expect(groupRepos(repos, 'language', now)).toEqual({
      '(없음)': ['a/old'],
      Python: ['a/py'],
      TypeScript: ['a/ts'],
    })
  })

  it('활동성/종류별', () => {
    const act = groupRepos(repos, 'activity', now)
    expect(Object.values(act)).toEqual([['a/ts'], ['a/py'], ['a/old']])
    expect(groupRepos(repos, 'kind', now)).toEqual({
      archived: ['a/old'],
      fork: ['a/py'],
      source: ['a/ts'],
    })
  })

  it('그룹 제안을 보드에 적용하면 컬럼이 생성되고 레포가 이동한다', () => {
    const b = applyGrouping(createBoard(repos.map((r) => r.id)), groupRepos(repos, 'kind', now))
    expect(b.columns.map((c) => c.title)).toEqual(['미분류', 'archived', 'fork', 'source'])
    expect(b.columns[0].repoIds).toEqual([])
  })
})

describe('serialize / parse', () => {
  it('왕복 변환', () => {
    const b = moveRepo(addColumn(createBoard(['a/1', 'a/2']), 'w', 'W'), 'a/2', 'w', 0)
    expect(parseBoard(serializeBoard(b))).toEqual(b)
  })

  it('잘못된 형식 거부, 중복 레포 정리', () => {
    expect(() => parseBoard('{"version":2,"columns":[]}')).toThrow()
    expect(() => parseBoard('{"version":1,"columns":[]}')).toThrow()
    const b = parseBoard(
      JSON.stringify({
        version: 1,
        columns: [
          { id: INBOX_ID, title: '미분류', repoIds: ['a/1'] },
          { id: 'w', title: 'W', repoIds: ['a/1', 'a/2'] },
        ],
      }),
    )
    expect(b.columns[1].repoIds).toEqual(['a/2'])
  })
})
