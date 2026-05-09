import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Empty, Flex, Space, Statistic, Table, Tag, Typography, theme as antTheme } from 'antd'
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
      const sortByUpdated = (items: TicketDto[]) =>
        [...items].sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''))
      return {
        pending: sortByUpdated(pending.items),
        reviewed: sortByUpdated(assigned.items),
      }
    },
  })
  const allTickets = useMemo(
    () => [...(queue.data?.pending || []), ...(queue.data?.reviewed || [])],
    [queue.data],
  )

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
      filters: Array.from(new Set(allTickets.map(t => t.current_sector_code).filter(Boolean) as string[]))
        .map((v) => ({ text: v as string, value: v as string })),
      onFilter: (val, row) => row.current_sector_code === val,
    },
    {
      title: 'Updated',
      dataIndex: 'updated_at',
      width: 180,
      render: (v) => (
        <Space orientation="vertical" size={0}>
          <span>{fmtDateTime(v)}</span>
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>{fmtRelative(v)}</Typography.Text>
        </Space>
      ),
      sorter: (a, b) => (a.updated_at || '').localeCompare(b.updated_at || ''),
      defaultSortOrder: 'descend',
    },
  ], [allTickets])

  const tablePanel = (title: string, description: string, items: TicketDto[], emptyText: string) => (
    <div style={{
      background: token.colorBgContainer,
      border: `1px solid ${token.colorBorderSecondary}`,
      borderRadius: 8,
      overflow: 'hidden',
      boxShadow: token.boxShadowTertiary,
    }}>
      <Flex justify="space-between" align="center" wrap="wrap" gap={12} style={{ padding: '14px 16px', borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
        <div>
          <Typography.Title level={5} style={{ margin: 0 }}>{title}</Typography.Title>
          <Typography.Text type="secondary">{description}</Typography.Text>
        </div>
        <Statistic value={items.length} suffix="tickets" />
      </Flex>
      <Table
        rowKey="id"
        loading={queue.isLoading}
        columns={columns}
        dataSource={items}
        pagination={{ pageSize: 10, showSizeChanger: true }}
        onRow={(record) => ({ onClick: () => navigate(`/review/${record.id}`) })}
        locale={{ emptyText: <Empty description={emptyText} /> }}
        rowClassName={() => 'tickora-row-clickable'}
        scroll={{ x: 860 }}
      />
    </div>
  )

  return (
    <div style={{ padding: 24, display: 'grid', gap: 16 }}>
      <Flex justify="space-between" align="center" wrap="wrap" gap={12}>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>Review Queue</Typography.Title>
          <Typography.Text type="secondary">Tickets split by review/routing status</Typography.Text>
        </div>
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={() => queue.refetch()} />
        </Space>
      </Flex>

      {queue.error && <Alert type="error" message={queue.error.message} showIcon />}

      {tablePanel(
        'Not Yet Reviewed',
        'Pending tickets that still need triage, metadata review, and sector routing.',
        queue.data?.pending || [],
        'No tickets waiting for review',
      )}

      {tablePanel(
        'Already Reviewed',
        'Tickets already routed to a sector and visible to that sector queue.',
        queue.data?.reviewed || [],
        'No reviewed tickets in the queue',
      )}
    </div>
  )
}
