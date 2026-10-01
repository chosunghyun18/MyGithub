import {
  DndContext,
  PointerSensor,
  closestCorners,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { useEffect, useMemo, useState } from 'react'
import {
  addColumn,
  applyGrouping,
  createBoard,
  findColumnOf,
  groupRepos,
  moveRepo,
  parseBoard,
  removeColumn,
  serializeBoard,
  syncRepos,
  INBOX_ID,
  type Board,
  type GroupKey,
} from './lib/board'
import { fetchAllRepos, type Repo } from './lib/github'

const BOARD_KEY = 'mygithub.board'
const TOKEN_KEY = 'mygithub.token'

function loadBoard(): Board {
  try {
    const raw = localStorage.getItem(BOARD_KEY)
    return raw ? parseBoard(raw) : createBoard()
  } catch {
    return createBoard()
  }
}

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) ?? '')
  const [repos, setRepos] = useState<Record<string, Repo>>({})
  const [board, setBoard] = useState<Board>(loadBoard)
  const [status, setStatus] = useState('')
  const [filter, setFilter] = useState('')

  useEffect(() => {
    localStorage.setItem(BOARD_KEY, serializeBoard(board))
  }, [board])

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))

  async function load() {
    setStatus('불러오는 중…')
    try {
      localStorage.setItem(TOKEN_KEY, token)
      const list = await fetchAllRepos(token)
      setRepos(Object.fromEntries(list.map((r) => [r.id, r])))
      setBoard((b) => syncRepos(b, list.map((r) => r.id)))
      setStatus(`${list.length}개 레포`)
    } catch (e) {
      setStatus(String(e))
    }
  }

  function onDragEnd(e: DragEndEvent) {
    const activeId = String(e.active.id)
    const overId = e.over ? String(e.over.id) : null
    if (!overId || activeId === overId) return
    // over 대상이 컬럼이면 끝으로, 레포면 그 레포 위치로
    const overCol = board.columns.find((c) => c.id === overId) ?? findColumnOf(board, overId)
    if (!overCol) return
    const idx = overCol.id === overId ? overCol.repoIds.length : overCol.repoIds.indexOf(overId)
    setBoard((b) => moveRepo(b, activeId, overCol.id, idx))
  }

  function newColumn() {
    const title = prompt('폴더 이름')
    if (!title) return
    setBoard((b) => addColumn(b, `col-${Date.now()}`, title))
  }

  function autoGroup(key: GroupKey) {
    const inbox = board.columns.find((c) => c.id === INBOX_ID)!.repoIds
    const metas = inbox.map((id) => repos[id]).filter(Boolean)
    setBoard((b) => applyGrouping(b, groupRepos(metas, key)))
  }

  function exportJson() {
    const blob = new Blob([serializeBoard(board)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'mygithub-board.json'
    a.click()
  }

  const q = filter.trim().toLowerCase()
  const visible = useMemo(
    () => (id: string) => !q || id.toLowerCase().includes(q) || (repos[id]?.description ?? '').toLowerCase().includes(q),
    [q, repos],
  )

  return (
    <div className="app">
      <header>
        <h1>MyGithub</h1>
        <input
          type="password"
          placeholder="GitHub fine-grained PAT (Metadata: read)"
          value={token}
          onChange={(e) => setToken(e.target.value)}
        />
        <button onClick={load} disabled={!token}>레포 불러오기</button>
        <button onClick={newColumn}>+ 폴더</button>
        <button onClick={() => autoGroup('language')}>미분류 → 언어별</button>
        <button onClick={() => autoGroup('activity')}>미분류 → 활동성별</button>
        <button onClick={exportJson}>JSON 내보내기</button>
        <input placeholder="검색" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <span className="status">{status}</span>
      </header>
      <DndContext sensors={sensors} collisionDetection={closestCorners} onDragEnd={onDragEnd}>
        <main className="board">
          {board.columns.map((col) => (
            <ColumnView
              key={col.id}
              id={col.id}
              title={col.title}
              repoIds={col.repoIds.filter(visible)}
              repos={repos}
              onRemove={col.id === INBOX_ID ? undefined : () => setBoard((b) => removeColumn(b, col.id))}
            />
          ))}
        </main>
      </DndContext>
    </div>
  )
}

function ColumnView(props: {
  id: string
  title: string
  repoIds: string[]
  repos: Record<string, Repo>
  onRemove?: () => void
}) {
  const { setNodeRef } = useDroppable({ id: props.id })
  return (
    <section className="column" ref={setNodeRef}>
      <h2>
        {props.title} <small>{props.repoIds.length}</small>
        {props.onRemove && <button onClick={props.onRemove} title="폴더 삭제 (레포는 미분류로)">×</button>}
      </h2>
      <SortableContext items={props.repoIds} strategy={verticalListSortingStrategy}>
        {props.repoIds.map((id) => (
          <RepoCard key={id} id={id} repo={props.repos[id]} />
        ))}
      </SortableContext>
    </section>
  )
}

function RepoCard({ id, repo }: { id: string; repo?: Repo }) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id })
  return (
    <article
      ref={setNodeRef}
      className={`card${repo?.archived ? ' archived' : ''}`}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      {...attributes}
      {...listeners}
    >
      <a href={repo?.htmlUrl ?? `https://github.com/${id}`} target="_blank" rel="noreferrer">
        {id}
      </a>
      {repo && (
        <div className="meta">
          {repo.language ?? '-'} · {repo.pushedAt.slice(0, 10)}
          {repo.private && ' · private'}
        </div>
      )}
    </article>
  )
}
