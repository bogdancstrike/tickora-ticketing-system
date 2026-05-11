import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Empty, Flex, Modal, Space, Statistic, Table, Tag, Typography, theme as antTheme, Spin } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ReloadOutlined, UserOutlined } from '@ant-design/icons'
import { listTickets, type TicketDto } from '@/api/tickets'
import { StatusTag } from '@/components/common/StatusTag'
import { PriorityTag } from '@/components/common/PriorityTag'
import { BeneficiaryTypeTag, BENEFICIARY_TYPE_OPTIONS } from '@/components/common/BeneficiaryTypeTag'
import { fmtDateTime, fmtRelative } from '@/components/common/format'
import { ProductTour, TourInfoButton } from '@/components/common/ProductTour'
import { useTranslation } from 'react-i18next'

export function ReviewTicketsPage() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { token } = antTheme.useToken()
  const [modalUsers, setModalUsers] = useState<string[] | null>(null)
  
  const [pendingPage, setPendingPage] = useState({ current: 1, pageSize: 10 })
  const [reviewedPage, setReviewedPage] = useState({ current: 1, pageSize: 10 })

  const pendingQueue = useQuery({
    queryKey: ['reviewTicketsPending', pendingPage],
    queryFn: () => listTickets({ 
        status: 'pending', 
        limit: pendingPage.pageSize, 
        offset: (pendingPage.current - 1) * pendingPage.pageSize 
    }),
    staleTime: 30_000,
  })

  const reviewedQueue = useQuery({
    queryKey: ['reviewTicketsReviewed', reviewedPage],
    queryFn: () => listTickets({ 
        status: 'assigned_to_sector', 
        limit: reviewedPage.pageSize, 
        offset: (reviewedPage.current - 1) * reviewedPage.pageSize 
    }),
    staleTime: 30_000,
  })

  const allTickets = useMemo(() => [
    ...(pendingQueue.data?.items || []),
    ...(reviewedQueue.data?.items || []),
  ], [pendingQueue.data, reviewedQueue.data])

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
      title: t('beneficiary_type.label'),
      dataIndex: 'beneficiary_type',
      width: 130,
      render: (value: string) => <BeneficiaryTypeTag type={value} />,
      filters: BENEFICIARY_TYPE_OPTIONS.map(o => ({ text: t(`beneficiary_type.${o.value}`), value: o.value })),
      onFilter: (val, row) => row.beneficiary_type === val,
      filterMultiple: false,
    },
    {
      title: 'Sector',
      dataIndex: 'sector_codes',
      width: 180,
      render: (values: string[], row) => {
        const codes = values?.length ? values : (row.current_sector_code ? [row.current_sector_code] : [])
        if (!codes.length) return '-'
        return (
          <Space wrap size={[0, 4]}>
            {codes.map(code => <Tag key={code} color="blue">{code}</Tag>)}
          </Space>
        )
      },
      filterSearch: true,
      filters: Array.from(new Set(allTickets.flatMap(t => t.sector_codes || (t.current_sector_code ? [t.current_sector_code] : [])).filter(Boolean) as string[]))
        .map((v) => ({ text: v as string, value: v as string })),
      onFilter: (val, row) => (row.sector_codes || (row.current_sector_code ? [row.current_sector_code] : [])).includes(val as string),
    },
    {
      title: 'Assigned users',
      dataIndex: 'assignee_usernames',
      width: 200,
      render: (values: string[], row) => {
        const names = values?.length ? values : (row.assignee_user_id ? [row.assignee_user_id.slice(0, 8)] : [])
        if (!names.length) return <Typography.Text type="secondary" style={{ fontSize: 12 }}>Unassigned</Typography.Text>
        
        const limit = 2
        const visible = names.slice(0, limit)
        const extra = names.length - limit

        return (
          <Space wrap size={[0, 4]} onClick={(e) => e.stopPropagation()}>
            {visible.map((name, idx) => <Tag key={idx} color="cyan">{name}</Tag>)}
            {extra > 0 && (
              <Button type="link" size="small" onClick={() => setModalUsers(names)} style={{ padding: 0 }}>
                +{extra} more
              </Button>
            )}
          </Space>
        )
      },
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
  ], [allTickets, t])

  const tablePanel = (
    title: string, 
    description: string, 
    query: any, 
    pagination: { current: number, pageSize: number }, 
    setPagination: any,
    emptyText: string,
    tourId: string
  ) => (
    <div style={{
      background: token.colorBgContainer,
      border: `1px solid ${token.colorBorderSecondary}`,
      borderRadius: 8,
      overflow: 'hidden',
      boxShadow: token.boxShadowTertiary,
    }} data-tour-id={tourId}>
      <Flex justify="space-between" align="center" wrap="wrap" gap={12} style={{ padding: '14px 16px', borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
        <div>
          <Typography.Title level={5} style={{ margin: 0 }}>{title}</Typography.Title>
          <Typography.Text type="secondary">{description}</Typography.Text>
        </div>
        <Statistic value={query.data?.total ?? 0} suffix="tickets" />
      </Flex>
      <Table
        rowKey="id"
        loading={query.isLoading}
        columns={columns}
        dataSource={query.data?.items || []}
        pagination={{ 
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: query.data?.total || 0,
            showSizeChanger: true,
            showTotal: (total) => `Total ${total} items`
        }}
        onChange={(p) => setPagination({ current: p.current || 1, pageSize: p.pageSize || 10 })}
        onRow={(record) => ({ onClick: () => navigate(`/review/${record.id}`) })}
        locale={{ emptyText: <Empty description={emptyText} /> }}
        rowClassName={() => 'tickora-row-clickable'}
        scroll={{ x: 860 }}
      />
    </div>
  )

  if (pendingQueue.isLoading || reviewedQueue.isLoading) return <div style={{ padding: 100, textAlign: 'center' }}><Spin size="large" /></div>

  return (
    <div style={{ padding: 24, display: 'grid', gap: 16 }}>
      <Flex justify="space-between" align="center" wrap="wrap" gap={12}>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>Review Queue</Typography.Title>
          <Typography.Text type="secondary">Tickets split by review/routing status</Typography.Text>
        </div>
        <Space wrap>
          <TourInfoButton pageKey="review-queue" />
          <Button icon={<ReloadOutlined />} onClick={() => { pendingQueue.refetch(); reviewedQueue.refetch() }} />
        </Space>
      </Flex>

      {pendingQueue.error && <Alert type="error" message={(pendingQueue.error as any).message} showIcon />}
      {reviewedQueue.error && <Alert type="error" message={(reviewedQueue.error as any).message} showIcon />}

      {tablePanel(
        'Not Yet Reviewed',
        'Pending tickets that still need triage, metadata review, and sector routing.',
        pendingQueue,
        pendingPage,
        setPendingPage,
        'No tickets waiting for review',
        'review-pending',
      )}

      {tablePanel(
        'Already Reviewed',
        'Tickets already routed to a sector and visible to that sector queue.',
        reviewedQueue,
        reviewedPage,
        setReviewedPage,
        'No reviewed tickets in the queue',
        'review-reviewed',
      )}
      <ProductTour
        pageKey="review-queue"
        steps={[
          { target: '[data-tour-id="review-pending"]', content: 'These tickets still need triage. Open one to set sector, priority, metadata, and assignment before it enters normal work queues.' },
          { target: '[data-tour-id="review-reviewed"]', content: 'This section shows tickets already routed by distribution, so you can quickly check recent review decisions and assignments.' },
        ]}
      />

      <Modal
        title="Assigned Users"
        open={!!modalUsers}
        onCancel={() => setModalUsers(null)}
        footer={null}
        width={400}
      >
        <div style={{ display: 'grid', gap: 8, maxHeight: 400, overflowY: 'auto', padding: '4px 0' }}>
          {(modalUsers || []).map((name, idx) => (
            <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', background: 'rgba(0,0,0,0.02)', borderRadius: 6 }}>
              <UserOutlined style={{ color: token.colorTextSecondary }} />
              <Typography.Text strong>{name}</Typography.Text>
            </div>
          ))}
        </div>
      </Modal>
    </div>
  )
}
