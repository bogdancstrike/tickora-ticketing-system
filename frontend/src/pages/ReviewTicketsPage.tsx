import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import {
  Alert, Button, Drawer, Empty, Flex, Form, Input, Select, Space, Table, Tag, Typography,
  message, theme as antTheme, Popconfirm,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { CheckSquareOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons'
import {
  getTicketOptions, listAssignableUsers, listTickets, reviewTicket,
  type ReviewTicketPayload, type TicketDto,
} from '@/api/tickets'

const STATUS_COLORS: Record<string, string> = {
  pending: 'default',
  assigned_to_sector: 'processing',
  in_progress: 'blue',
}

const PRIORITY_COLORS: Record<string, string> = {
  low: 'default',
  medium: 'blue',
  high: 'orange',
  critical: 'red',
}

function fmt(value?: string | null) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-'
}

export function ReviewTicketsPage() {
  const [selected, setSelected] = useState<TicketDto | null>(null)
  const [sectorCode, setSectorCode] = useState<string | undefined>()
  const [form] = Form.useForm<ReviewTicketPayload>()
  const [msg, holder] = message.useMessage()
  const queryClient = useQueryClient()
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

  const options = useQuery({
    queryKey: ['ticketOptions'],
    queryFn: getTicketOptions,
    staleTime: 300_000,
  })

  const users = useQuery({
    queryKey: ['assignableUsers', sectorCode],
    queryFn: () => listAssignableUsers(sectorCode),
    enabled: !!sectorCode,
    staleTime: 60_000,
  })

  const review = useMutation({
    mutationFn: async (values: ReviewTicketPayload) => {
      if (!selected) throw new Error('Select a ticket first')
      return reviewTicket(selected.id, values)
    },
    onSuccess: async (ticket) => {
      msg.success(`${ticket.ticket_code} reviewed`)
      setSelected(null)
      form.resetFields()
      setSectorCode(undefined)
      await queryClient.invalidateQueries({ queryKey: ['reviewTickets'] })
      await queryClient.invalidateQueries({ queryKey: ['tickets'] })
    },
    onError: (err) => msg.error(err.message),
  })

  const openReview = (ticket: TicketDto) => {
    setSelected(ticket)
    setSectorCode(ticket.current_sector_code || undefined)
    form.setFieldsValue({
      sector_code: ticket.current_sector_code || undefined,
      priority: ticket.priority,
      category: ticket.category || undefined,
      type: ticket.type || undefined,
      assignee_user_id: ticket.assignee_user_id || undefined,
    })
  }

  const columns: ColumnsType<TicketDto> = useMemo(() => [
    {
      title: 'Code',
      dataIndex: 'ticket_code',
      width: 150,
      render: (value) => <Typography.Text strong>{value}</Typography.Text>,
    },
    {
      title: 'Title',
      dataIndex: 'title',
      ellipsis: true,
      render: (value, row) => value || row.txt?.slice(0, 90) || '-',
    },
    {
      title: 'Status',
      dataIndex: 'status',
      width: 170,
      render: (value) => <Tag color={STATUS_COLORS[value]}>{value}</Tag>,
    },
    {
      title: 'Priority',
      dataIndex: 'priority',
      width: 120,
      render: (value) => <Tag color={PRIORITY_COLORS[value]}>{value}</Tag>,
    },
    {
      title: 'Sector',
      dataIndex: 'current_sector_code',
      width: 130,
      render: (value) => value ? <Tag>{value}</Tag> : '-',
    },
    {
      title: 'Updated',
      dataIndex: 'updated_at',
      width: 170,
      render: fmt,
    },
  ], [])

  return (
    <div style={{ padding: 24, display: 'grid', gap: 16 }}>
      {holder}
      <Flex justify="space-between" align="center" wrap="wrap" gap={12}>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>Review Tickets</Typography.Title>
          <Typography.Text type="secondary">Triage metadata, routing, and distributor notes</Typography.Text>
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
          pagination={false}
          onRow={(record) => ({ onClick: () => openReview(record) })}
          locale={{ emptyText: <Empty description="No tickets waiting for review" /> }}
          rowClassName={() => 'tickora-row-clickable'}
          scroll={{ x: 860 }}
        />
      </div>

      <Drawer
        title={selected ? `${selected.ticket_code} · ${selected.title || 'Ticket review'}` : 'Review ticket'}
        open={!!selected}
        width={560}
        onClose={() => {
          setSelected(null)
          form.resetFields()
          setSectorCode(undefined)
        }}
      >
        {selected && (
          <div style={{ display: 'grid', gap: 16 }}>
            <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
              {selected.txt}
            </Typography.Paragraph>
            <Form
              form={form}
              layout="vertical"
              onFinish={(values) => review.mutate(values)}
              onValuesChange={(changed) => {
                if ('sector_code' in changed) {
                  setSectorCode(changed.sector_code)
                  form.setFieldValue('assignee_user_id', undefined)
                }
              }}
            >
              <Form.Item name="sector_code" label="Sector" rules={[{ required: true }]}>
                <Select
                  showSearch
                  optionFilterProp="label"
                  options={(options.data?.sectors || []).map((s) => ({
                    value: s.code,
                    label: `${s.code} · ${s.name}`,
                  }))}
                />
              </Form.Item>
              <Form.Item name="assignee_user_id" label="Assignee">
                <Select
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  loading={users.isLoading}
                  disabled={!sectorCode}
                  options={(users.data?.items || []).map((u) => ({
                    value: u.id,
                    label: `${u.username || u.email || u.id} · ${u.membership_role}`,
                  }))}
                />
              </Form.Item>
              <Flex gap={12} wrap="wrap">
                <Form.Item name="priority" label="Priority" rules={[{ required: true }]} style={{ minWidth: 170, flex: 1 }}>
                  <Select options={(options.data?.priorities || []).map((p) => ({ value: p, label: p }))} />
                </Form.Item>
                <Form.Item name="category" label="Category" style={{ minWidth: 190, flex: 1 }}>
                  <Select
                    allowClear
                    showSearch
                    optionFilterProp="label"
                    options={(options.data?.categories || []).map((value) => ({ value, label: value }))}
                  />
                </Form.Item>
              </Flex>
              <Form.Item name="type" label="Type">
                <Select
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  options={(options.data?.types || []).map((value) => ({ value, label: value }))}
                />
              </Form.Item>
              <Form.Item name="private_comment" label="Distributor commentary">
                <Input.TextArea rows={4} />
              </Form.Item>
              <Form.Item name="reason" label="Routing reason">
                <Input.TextArea rows={3} />
              </Form.Item>
              <Flex justify="space-between" gap={8}>
                <Button onClick={() => navigate(`/tickets/${selected.id}`)}>Open Ticket</Button>
                <Space>
                  <Popconfirm
                    title="Close ticket prematurely?"
                    description="This will cancel the ticket with the provided reason."
                    onConfirm={() => {
                      const values = form.getFieldsValue()
                      review.mutate({ ...values, close: true })
                    }}
                    okText="Yes, Close"
                    okButtonProps={{ danger: true }}
                  >
                    <Button danger icon={<StopOutlined />} loading={review.isPending}>
                      Close Ticket
                    </Button>
                  </Popconfirm>
                  <Button type="primary" htmlType="submit" icon={<CheckSquareOutlined />} loading={review.isPending}>
                    Apply Review
                  </Button>
                </Space>
              </Flex>
            </Form>
          </div>
        )}
      </Drawer>
    </div>
  )
}
