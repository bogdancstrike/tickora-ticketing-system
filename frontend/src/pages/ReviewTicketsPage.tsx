import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Empty, Flex, Space, Table, Tag, Typography, theme as antTheme } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ReloadOutlined } from '@ant-design/icons'
import { listTickets, type TicketDto } from '@/api/tickets'
import { StatusTag } from '@/components/common/StatusTag'
import { PriorityTag } from '@/components/common/PriorityTag'
import { fmtDateTime, fmtRelative } from '@/components/common/format'

export function ReviewTicketsPage() {
  const navigate = useNavigate()
  const { token } = antTheme.useToken()

  const queue = useQuery({
    queryKey: ['reviewTickets'],
    queryFn: async () => {
      const [pending, assigned] = await Promise.all([
        listTickets({ status: 'pending', limit: 100 }),
        listTickets({ status: 'assigned_to_sector', limit: 100 }),
      ])
      const byId = new Map<string, TicketDto>()
      for (const ticket of [...pending.items, ...assigned.items]) byId.set(ticket.id, ticket)
      return [...byId.values()].sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''))
    },
  })

  const columns: ColumnsType<TicketDto> = useMemo(() => [
    {
      title: 'Code',
      dataIndex: 'ticket_code',
      width: 150,
      render: (value) => <Typography.Text strong>{value}</Typography.Text>,
      sorter: (a, b) => (a.ticket_code || '').localeCompare(b.ticket_code || ''),
    },
    {
      title: 'Title',
      dataIndex: 'title',
      ellipsis: true,
      render: (value, row) => value || row.txt?.slice(0, 90) || '-',
      sorter: (a, b) => (a.title || a.txt || '').localeCompare(b.title || b.txt || ''),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      width: 180,
      render: (value) => <StatusTag status={value} />,
      sorter: (a, b) => a.status.localeCompare(b.status),
      filters: [
        { text: 'Pending', value: 'pending' },
        { text: 'Assigned to sector', value: 'assigned_to_sector' },
      ],
      onFilter: (val, row) => row.status === val,
    },
    {
      title: 'Priority',
      dataIndex: 'priority',
      width: 130,
      render: (value) => <PriorityTag priority={value} />,
      sorter: (a, b) => {
        const order = { low: 0, medium: 1, high: 2, critical: 3 } as Record<string, number>
        return (order[a.priority] || 0) - (order[b.priority] || 0)
      },
      filters: ['low', 'medium', 'high', 'critical'].map((v) => ({ text: v, value: v })),
      onFilter: (val, row) => row.priority === val,
    },
    {
      title: 'Sector',
      dataIndex: 'current_sector_code',
      width: 140,
      render: (value) => value ? <Tag>{value}</Tag> : '-',
      sorter: (a, b) => (a.current_sector_code || '').localeCompare(b.current_sector_code || ''),
      filterSearch: true,
      filters: Array.from(new Set((queue.data || []).map(t => t.current_sector_code).filter(Boolean) as string[]))
        .map((v) => ({ text: v as string, value: v as string })),
      onFilter: (val, row) => row.current_sector_code === val,
    },
    {
      title: 'Updated',
      dataIndex: 'updated_at',
      width: 180,
      render: (v) => (
        <Space direction="vertical" size={0}>
          <span>{fmtDateTime(v)}</span>
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>{fmtRelative(v)}</Typography.Text>
        </Space>
      ),
      sorter: (a, b) => (a.updated_at || '').localeCompare(b.updated_at || ''),
      defaultSortOrder: 'descend',
    },
  ], [queue.data])

  return (
    <div style={{ padding: 24, display: 'grid', gap: 16 }}>
      <Flex justify="space-between" align="center" wrap="wrap" gap={12}>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>Review Queue</Typography.Title>
          <Typography.Text type="secondary">Tickets awaiting triage and routing</Typography.Text>
        </div>
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={() => queue.refetch()} />
        </Space>
      </Flex>

      {queue.error && <Alert type="error" message={queue.error.message} showIcon />}

      <div style={{ border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8, overflow: 'hidden' }}>
        <Table
          rowKey="id"
          loading={queue.isLoading}
          columns={columns}
          dataSource={queue.data || []}
          pagination={{ pageSize: 25, showSizeChanger: true }}
          onRow={(record) => ({ onClick: () => navigate(`/review/${record.id}`) })}
          locale={{ emptyText: <Empty description="No tickets waiting for review" /> }}
          rowClassName={() => 'tickora-row-clickable'}
          scroll={{ x: 860 }}
        />
      </div>
    </div>
  )
}
