/**
 * Ticket-link panel for the detail page.
 *
 * Shows incoming + outgoing links, grouped by relation. The "Add link"
 * row lets the user paste a target ticket code (e.g. `TK-2026-000123`)
 * and pick a relation. Backend resolves the code → id and enforces:
 *   - source-side modify permission
 *   - target-side view permission
 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Button, Card, Empty, Flex, Input, Popconfirm, Select, Space, Tag, Tooltip,
  Typography, message, theme as antTheme,
} from 'antd'
import { DeleteOutlined, LinkOutlined, PlusOutlined } from '@ant-design/icons'
import { Link as RouterLink } from 'react-router-dom'

import {
  addTicketLink, listTicketLinks, listTickets, removeTicketLink,
  type TicketLinkDto,
} from '@/api/tickets'

const RELATION_LABELS: Record<string, string> = {
  parent_of:     'Parent of',
  child_of:      'Child of',
  blocks:        'Blocks',
  blocked_by:    'Blocked by',
  duplicates:    'Duplicates',
  duplicate_of:  'Duplicate of',
  relates_to:    'Relates to',
}

const ADDABLE_RELATIONS = [
  { value: 'parent_of',  label: 'Parent of' },
  { value: 'blocks',     label: 'Blocks' },
  { value: 'duplicates', label: 'Duplicates' },
  { value: 'relates_to', label: 'Relates to' },
] as const

export function TicketLinksPanel({ ticketId }: { ticketId: string }) {
  const { token } = antTheme.useToken()
  const queryClient = useQueryClient()
  const [msg, holder] = message.useMessage()

  const links = useQuery({
    queryKey: ['ticketLinks', ticketId],
    queryFn: () => listTicketLinks(ticketId),
    staleTime: 10_000,
  })

  // Group by relation for clean visual blocks.
  const grouped = useMemo(() => {
    const m = new Map<string, TicketLinkDto[]>()
    for (const l of links.data?.items ?? []) {
      const key = l.relation
      const arr = m.get(key) ?? []
      arr.push(l)
      m.set(key, arr)
    }
    return Array.from(m.entries())
  }, [links.data])

  // Add-form state
  const [adding, setAdding] = useState(false)
  const [search, setSearch] = useState('')
  const [pickedTargetId, setPickedTargetId] = useState<string | undefined>()
  const [relation, setRelation] = useState<typeof ADDABLE_RELATIONS[number]['value']>('relates_to')

  // Search results — debounced via TanStack Query's stale time.
  const targetSearch = useQuery({
    queryKey: ['ticketSearch', search],
    queryFn: () => listTickets({ search, limit: 8 }),
    enabled: search.trim().length >= 3,
    staleTime: 5_000,
  })

  const add = useMutation({
    mutationFn: () => addTicketLink(ticketId, {
      target_ticket_id: pickedTargetId!,
      link_type: relation,
    }),
    onSuccess: async () => {
      msg.success('Link added')
      setAdding(false)
      setSearch('')
      setPickedTargetId(undefined)
      await queryClient.invalidateQueries({ queryKey: ['ticketLinks', ticketId] })
    },
    onError: (err) => msg.error(err.message),
  })

  const remove = useMutation({
    mutationFn: (linkId: string) => removeTicketLink(linkId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['ticketLinks', ticketId] })
    },
    onError: (err) => msg.error(err.message),
  })

  const total = links.data?.items.length ?? 0

  return (
    <Card
      title={<Space size={6}><LinkOutlined /><Typography.Text strong>Links</Typography.Text>{total > 0 && <Tag>{total}</Tag>}</Space>}
      extra={!adding && (
        <Button size="small" icon={<PlusOutlined />} onClick={() => setAdding(true)}>Add link</Button>
      )}
      styles={{ body: { padding: 12 } }}
    >
      {holder}

      {adding && (
        <div style={{ background: token.colorFillAlter, padding: 12, borderRadius: 8, marginBottom: 12 }}>
          <Flex gap={8} wrap="wrap" align="center">
            <Select<string>
              style={{ minWidth: 150 }}
              value={relation}
              onChange={(v) => setRelation(v as typeof relation)}
              options={ADDABLE_RELATIONS as unknown as Array<{value: string; label: string}>}
            />
            <Select<string>
              style={{ flex: 1, minWidth: 240 }}
              showSearch
              filterOption={false}
              value={pickedTargetId}
              onSearch={setSearch}
              onChange={(v) => setPickedTargetId(v)}
              loading={targetSearch.isLoading}
              placeholder="Search by code, title, or body…"
              options={(targetSearch.data?.items ?? [])
                .filter((t) => t.id !== ticketId)
                .map((t) => ({
                  value: t.id,
                  label: `${t.ticket_code} · ${t.title || '(no title)'}`,
                }))}
            />
            <Button
              type="primary"
              size="small"
              loading={add.isPending}
              disabled={!pickedTargetId}
              onClick={() => add.mutate()}
            >
              Add
            </Button>
            <Button size="small" onClick={() => { setAdding(false); setPickedTargetId(undefined); setSearch('') }}>
              Cancel
            </Button>
          </Flex>
        </div>
      )}

      {total === 0 && !adding && (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No links yet" />
      )}

      {grouped.map(([relation, rows]) => (
        <div key={relation} style={{ marginBottom: 8 }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {RELATION_LABELS[relation] ?? relation}
          </Typography.Text>
          <div style={{ display: 'grid', gap: 4, marginTop: 4 }}>
            {rows.map((l) => (
              <Flex key={l.id} justify="space-between" align="center" gap={8}
                    style={{ padding: '6px 10px', background: 'rgba(0,0,0,0.03)', borderRadius: 6 }}>
                <Space size={6} style={{ minWidth: 0 }}>
                  <Tooltip title={l.direction === 'outgoing' ? 'Outgoing link' : 'Incoming link'}>
                    <Tag style={{ margin: 0 }}>{l.other.ticket_code}</Tag>
                  </Tooltip>
                  <RouterLink to={`/tickets/${l.other.id}`}>
                    <Typography.Text ellipsis style={{ maxWidth: 320 }}>
                      {l.other.title || '(no title)'}
                    </Typography.Text>
                  </RouterLink>
                  <Tag color="default">{l.other.status}</Tag>
                </Space>
                <Popconfirm
                  title="Remove this link?"
                  okText="Remove"
                  okButtonProps={{ danger: true }}
                  onConfirm={() => remove.mutate(l.id)}
                >
                  <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </Flex>
            ))}
          </div>
        </div>
      ))}
    </Card>
  )
}
