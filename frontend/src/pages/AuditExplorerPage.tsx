import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import dayjs from 'dayjs'
import {
  Alert, Button, Drawer, Empty, Flex, Form, Input, Space, Table, Tag, Typography,
  Descriptions, Card, DatePicker, theme as antTheme,
} from 'antd'
import { TicketEvolutionD3 } from '@/components/common/TicketEvolutionD3'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import type { FilterValue, SorterResult, FilterDropdownProps } from 'antd/es/table/interface'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { listAudit, listTicketAudit, type AuditEventDto } from '@/api/tickets'

const { RangePicker } = DatePicker

function fmt(value?: string | null) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'
}

function AuditValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <Typography.Text type="secondary">null</Typography.Text>
  if (typeof value === 'object') {
    return <pre style={{ margin: 0, fontSize: 12 }}>{JSON.stringify(value, null, 2)}</pre>
  }
  return String(value)
}

function TicketEvolutionGraph({ ticketId }: { ticketId: string }) {
  const audit = useQuery({
    queryKey: ['ticketAudit', ticketId],
    queryFn: () => listTicketAudit(ticketId),
  })
  const events = audit.data?.items || []
  if (audit.isLoading) return <Typography.Text>Loading…</Typography.Text>
  if (events.length === 0) return <Empty description="No history yet" />

  return (
    <div>
      <TicketEvolutionD3 events={events} />
      <Typography.Title level={5} style={{ marginTop: 24 }}>Event log</Typography.Title>
      {events.map((e) => (
        <div key={e.id} style={{ display: 'flex', gap: 12, padding: '6px 0', borderBottom: '1px solid rgba(0,0,0,0.06)' }}>
          <Typography.Text type="secondary" style={{ minWidth: 140 }}>{fmt(e.created_at)}</Typography.Text>
          <Tag color="blue">{e.action}</Tag>
          <Typography.Text>{e.actor_username || e.actor_user_id || 'system'}</Typography.Text>
        </div>
      ))}
    </div>
  )
}

function textFilterDropdown(placeholder: string) {
  return ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: FilterDropdownProps) => (
    <div style={{ padding: 8 }} onKeyDown={(e) => e.stopPropagation()}>
      <Input
        autoFocus
        placeholder={placeholder}
        value={selectedKeys[0] as string}
        onChange={(e) => setSelectedKeys(e.target.value ? [e.target.value] : [])}
        onPressEnter={() => confirm()}
        style={{ width: 200, marginBottom: 8, display: 'block' }}
        allowClear
      />
      <Space>
        <Button type="primary" size="small" onClick={() => confirm()} icon={<SearchOutlined />}>Search</Button>
        <Button size="small" onClick={() => { clearFilters?.(); confirm() }}>Reset</Button>
      </Space>
    </div>
  )
}

const ACTION_FILTERS = [
  'ticket_created', 'ticket_updated', 'ticket_deleted',
  'ticket_assigned_to_sector', 'ticket_assigned_to_user', 'ticket_assigned_to_me', 'ticket_reassigned',
  'ticket_marked_done', 'ticket_closed', 'ticket_reopened', 'ticket_cancelled',
  'ticket_priority_changed', 'ticket_reviewed',
  'comment_created', 'comment_deleted',
  'attachment_uploaded', 'attachment_deleted',
  'ticket_metadata_set', 'ticket_metadata_deleted',
].map((v) => ({ text: v, value: v }))

interface AuditFilterState {
  action?: string
  actor_username?: string
  ticket_id?: string
  correlation_id?: string
  created_after?: string
  created_before?: string
  sort_by?: string
  sort_dir?: 'asc' | 'desc'
}

export function AuditExplorerPage() {
  const { token } = antTheme.useToken()
  const [params, setParams] = useState<AuditFilterState>({ sort_by: 'created_at', sort_dir: 'desc' })
  const [graphTicketId, setGraphTicketId] = useState<string | null>(null)
  const audit = useQuery({
    queryKey: ['audit', params],
    queryFn: () => listAudit({ ...params, limit: 200 }),
  })

  const columns: ColumnsType<AuditEventDto> = useMemo(() => [
    {
      title: 'Time',
      dataIndex: 'created_at',
      width: 190,
      render: fmt,
      sorter: { multiple: 0 },
      defaultSortOrder: 'descend' as const,
    },
    {
      title: 'Action',
      dataIndex: 'action',
      width: 230,
      render: (v) => <Tag color="blue">{v}</Tag>,
      sorter: { multiple: 0 },
      filters: ACTION_FILTERS,
      filteredValue: params.action ? [params.action] : null,
      filterMultiple: false,
      filterSearch: true,
    },
    {
      title: 'Actor',
      dataIndex: 'actor_username',
      width: 180,
      render: (v, row) => v || row.actor_user_id || '-',
      sorter: { multiple: 0 },
      filterDropdown: textFilterDropdown('Search username'),
      filteredValue: params.actor_username ? [params.actor_username] : null,
    },
    {
      title: 'Entity',
      width: 180,
      render: (_, row) => `${row.entity_type}:${row.entity_id || '-'}`,
    },
    {
      title: 'Ticket ID',
      dataIndex: 'ticket_id',
      width: 240,
      ellipsis: true,
      render: (tid) => tid ? <Link to={`/tickets/${tid}`}>{tid}</Link> : '-',
      filterDropdown: textFilterDropdown('Ticket UUID'),
      filteredValue: params.ticket_id ? [params.ticket_id] : null,
    },
    {
      title: 'Correlation',
      dataIndex: 'correlation_id',
      width: 220,
      ellipsis: true,
      filterDropdown: textFilterDropdown('Correlation ID'),
      filteredValue: params.correlation_id ? [params.correlation_id] : null,
    },
    {
      title: '',
      key: 'actions',
      width: 120,
      render: (_, row) => row.ticket_id
        ? <Button size="small" onClick={(e) => { e.stopPropagation(); setGraphTicketId(row.ticket_id!) }}>See timeline</Button>
        : null,
    },
  ], [params])

  const handleTableChange = (
    _pagination: TablePaginationConfig,
    filters: Record<string, FilterValue | null>,
    sorter: SorterResult<AuditEventDto> | SorterResult<AuditEventDto>[]
  ) => {
    const s = Array.isArray(sorter) ? sorter[0] : sorter
    setParams((prev) => {
      const next: AuditFilterState = { ...prev }
      const pickFirst = (key: string) => {
        const v = filters?.[key]
        return Array.isArray(v) && v.length ? String(v[0]) : undefined
      }
      next.action = pickFirst('action')
      next.actor_username = pickFirst('actor_username')
      next.ticket_id = pickFirst('ticket_id')
      next.correlation_id = pickFirst('correlation_id')
      if (s?.order && s.field) {
        next.sort_by = String(s.field)
        next.sort_dir = s.order === 'ascend' ? 'asc' : 'desc'
      } else if (!s?.order) {
        next.sort_by = 'created_at'
        next.sort_dir = 'desc'
      }
      return next
    })
  }

  const onFilter = (values: { range?: [dayjs.Dayjs, dayjs.Dayjs]; q?: string }) => {
    setParams((prev) => {
      const next: AuditFilterState = { ...prev }
      if (values.range) {
        next.created_after = values.range[0].startOf('day').toISOString()
        next.created_before = values.range[1].endOf('day').toISOString()
      } else {
        delete next.created_after
        delete next.created_before
      }
      // free-text search heuristic: looks like a UUID → ticket_id; else username
      const q = (values.q || '').trim()
      if (q) {
        if (/^[0-9a-f-]{20,}$/i.test(q)) next.ticket_id = q
        else next.actor_username = q
      } else {
        delete next.ticket_id
        delete next.actor_username
      }
      return next
    })
  }

  return (
    <div style={{ padding: 24, display: 'grid', gap: 16 }}>
      <Flex justify="space-between" align="center" wrap="wrap" gap={12}>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>Audit Explorer</Typography.Title>
          <Typography.Text type="secondary">Global audit ledger for admins and auditors</Typography.Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => audit.refetch()} />
      </Flex>

      <Card size="small" styles={{ body: { padding: 12 } }}>
        <Form layout="inline" onFinish={onFilter}>
          <Form.Item name="q" tooltip="Search ticket ID (UUID) or actor username">
            <Input allowClear placeholder="Quick search · ticket UUID or username"
                   prefix={<SearchOutlined />} style={{ width: 320 }} />
          </Form.Item>
          <Form.Item name="range" label="Date">
            <RangePicker />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button htmlType="submit" type="primary">Apply</Button>
              <Button onClick={() => setParams({ sort_by: 'created_at', sort_dir: 'desc' })}>Reset all</Button>
            </Space>
          </Form.Item>
        </Form>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Tip: click any column header for column-level sorting and filtering.
        </Typography.Text>
      </Card>

      {audit.error && <Alert type="error" showIcon message={audit.error.message} />}
      <div style={{ border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8, overflow: 'hidden' }}>
        <Table
          rowKey="id"
          loading={audit.isLoading}
          columns={columns}
          dataSource={audit.data?.items || []}
          onChange={handleTableChange}
          expandable={{
            expandedRowRender: (row) => (
              <Card size="small" style={{ background: token.colorBgLayout }}>
                <Descriptions bordered size="small" column={1}>
                  {row.old_value && (
                    <Descriptions.Item label="Old Value">
                      <AuditValue value={row.old_value} />
                    </Descriptions.Item>
                  )}
                  {row.new_value && (
                    <Descriptions.Item label="New Value">
                      <AuditValue value={row.new_value} />
                    </Descriptions.Item>
                  )}
                  {row.metadata && (
                    <Descriptions.Item label="Metadata">
                      <AuditValue value={row.metadata} />
                    </Descriptions.Item>
                  )}
                  <Descriptions.Item label="Request Details">
                    <Space orientation="vertical">
                      <Typography.Text type="secondary">IP: {row.request_ip || (row.metadata?.request_ip as string) || '-'}</Typography.Text>
                      <Typography.Text type="secondary" style={{ fontSize: 11 }}>Agent: {row.user_agent || (row.metadata?.user_agent as string) || '-'}</Typography.Text>
                    </Space>
                  </Descriptions.Item>
                </Descriptions>
              </Card>
            ),
          }}
          pagination={{ pageSize: 25, showSizeChanger: true }}
          locale={{ emptyText: <Empty description="No audit events" /> }}
          scroll={{ x: 1200 }}
        />
      </div>

      <Drawer
        title={graphTicketId ? `Ticket evolution · ${graphTicketId}` : 'Ticket evolution'}
        open={!!graphTicketId}
        width={720}
        onClose={() => setGraphTicketId(null)}
        extra={
          graphTicketId
            ? <Link to={`/tickets/${graphTicketId}`}><Button>Open ticket</Button></Link>
            : null
        }
      >
        {graphTicketId && <TicketEvolutionGraph ticketId={graphTicketId} />}
      </Drawer>
    </div>
  )
}
