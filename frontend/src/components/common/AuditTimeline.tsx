import { useMemo, useState } from 'react'
import { Card, Descriptions, Empty, Space, Tag, Typography, theme as antTheme, Tooltip } from 'antd'
import { CaretRightOutlined, CaretDownOutlined } from '@ant-design/icons'
import type { AuditEventDto } from '@/api/tickets'
import { fmtDateTime, fmtRelative } from './format'

const ACTION_COLORS: Record<string, string> = {
  ticket_created: 'green',
  ticket_updated: 'blue',
  ticket_deleted: 'red',
  ticket_assigned_to_sector: 'cyan',
  ticket_assigned_to_user: 'cyan',
  ticket_assigned_to_me: 'cyan',
  ticket_reassigned: 'cyan',
  ticket_marked_done: 'green',
  ticket_closed: 'green',
  ticket_reopened: 'purple',
  ticket_cancelled: 'red',
  ticket_priority_changed: 'orange',
  comment_created: 'geekblue',
  comment_deleted: 'red',
  attachment_uploaded: 'geekblue',
  attachment_deleted: 'red',
  ticket_metadata_set: 'gold',
  ticket_metadata_deleted: 'red',
  ticket_reviewed: 'magenta',
}

function actionLabel(action: string): string {
  return action.split('_').map(s => s.charAt(0).toUpperCase() + s.slice(1)).join(' ')
}

function valueDiff(old?: Record<string, unknown> | null, next?: Record<string, unknown> | null) {
  if (!old && !next) return null
  if (!old && next) {
    return Object.entries(next).filter(([, v]) => v !== null && v !== undefined).map(([k, v]) => ({ key: k, old: undefined, next: v }))
  }
  if (old && !next) {
    return Object.entries(old).filter(([, v]) => v !== null && v !== undefined).map(([k, v]) => ({ key: k, old: v, next: undefined }))
  }
  const keys = new Set([...Object.keys(old || {}), ...Object.keys(next || {})])
  const diffs: Array<{ key: string; old: unknown; next: unknown }> = []
  keys.forEach(k => {
    const a = (old as any)?.[k]
    const b = (next as any)?.[k]
    if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ key: k, old: a, next: b })
  })
  return diffs
}

function fmtVal(v: unknown): string {
  if (v === null || v === undefined) return '∅'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

function AuditDiff({ event }: { event: AuditEventDto }) {
  const diffs = useMemo(() => valueDiff(event.old_value, event.new_value), [event])
  if (!diffs || diffs.length === 0) return <Typography.Text type="secondary">No field changes recorded.</Typography.Text>
  return (
    <Descriptions size="small" column={1} bordered>
      {diffs.slice(0, 12).map(d => (
        <Descriptions.Item key={d.key} label={d.key}>
          {d.old !== undefined && <Typography.Text delete type="secondary">{fmtVal(d.old)}</Typography.Text>}
          {d.old !== undefined && d.next !== undefined && <Typography.Text type="secondary"> → </Typography.Text>}
          {d.next !== undefined && <Typography.Text strong>{fmtVal(d.next)}</Typography.Text>}
        </Descriptions.Item>
      ))}
    </Descriptions>
  )
}

function AuditCard({ event, expanded, onToggle }: { event: AuditEventDto; expanded: boolean; onToggle: () => void }) {
  const { token } = antTheme.useToken()
  const color = ACTION_COLORS[event.action] || 'default'
  return (
    <Card
      size="small"
      style={{
        marginBottom: 12,
        borderLeft: `3px solid ${token.colorPrimary}`,
        cursor: 'pointer',
      }}
      onClick={onToggle}
      styles={{ body: { padding: 12 } }}
    >
      <Space style={{ width: '100%', justifyContent: 'space-between' }} align="start">
        <Space orientation="vertical" size={4} style={{ flex: 1 }}>
          <Space wrap>
            <Tag color={color}>{actionLabel(event.action)}</Tag>
            <Typography.Text type="secondary">{event.actor_username || event.actor_user_id || 'system'}</Typography.Text>
          </Space>
          <Tooltip title={fmtDateTime(event.created_at)}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>{fmtRelative(event.created_at)}</Typography.Text>
          </Tooltip>
        </Space>
        {expanded ? <CaretDownOutlined /> : <CaretRightOutlined />}
      </Space>
      {expanded && (
        <div style={{ marginTop: 12 }}>
          <AuditDiff event={event} />
          {event.metadata && Object.keys(event.metadata).length > 0 && (
            <div style={{ marginTop: 8 }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                Metadata: {JSON.stringify(event.metadata)}
              </Typography.Text>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

export function AuditTimeline({ events, loading }: { events: AuditEventDto[]; loading?: boolean }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  if (!loading && events.length === 0) {
    return <Empty description="No audit events" image={Empty.PRESENTED_IMAGE_SIMPLE} />
  }
  return (
    <div style={{ position: 'relative' }}>
      {loading && <div style={{ textAlign: 'center', padding: 20 }}><Typography.Text type="secondary">Loading...</Typography.Text></div>}
      {events.map((e) => (
        <AuditCard
          key={e.id}
          event={e}
          expanded={expanded.has(e.id)}
          onToggle={() =>
            setExpanded(prev => {
              const next = new Set(prev)
              if (next.has(e.id)) next.delete(e.id)
              else next.add(e.id)
              return next
            })
          }
        />
      ))}
    </div>
  )
}
