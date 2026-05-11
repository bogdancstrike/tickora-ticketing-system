import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Button, Empty, Flex, Form, Input, Modal, Space, Statistic, Table, Tag, Typography,
  message, theme as antTheme,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { CheckCircleOutlined, CloseCircleOutlined, ReloadOutlined, UserOutlined } from '@ant-design/icons'
import {
  listEndorsementInbox, decideEndorsement, claimEndorsement,
  type EndorsementDto, type EndorsementStatus,
} from '@/api/endorsements'
import { StatusTag } from '@/components/common/StatusTag'
import { PriorityTag } from '@/components/common/PriorityTag'
import { fmtDateTime } from '@/components/common/format'

const STATUS_TABS: { key: EndorsementStatus | 'all'; label: string }[] = [
  { key: 'pending',  label: 'Pending' },
  { key: 'approved', label: 'Approved' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'all',      label: 'All' },
]

export function AvizatorPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { token } = antTheme.useToken()
  const [tab, setTab] = useState<EndorsementStatus | 'all'>('pending')
  const [pending, setPending] = useState<EndorsementDto | null>(null)
  const [decision, setDecision] = useState<'approved' | 'rejected'>('approved')
  const [form] = Form.useForm<{ reason: string }>()
  const [msg, holder] = message.useMessage()

  const inbox = useQuery({
    queryKey: ['endorsementInbox', tab],
    queryFn: () => listEndorsementInbox(tab === 'all' ? {} : { status: tab }),
    staleTime: 30_000,
  })

  const decide = useMutation({
    mutationFn: async (vars: { id: string; decision: 'approved' | 'rejected'; reason?: string }) =>
      decideEndorsement(vars.id, { decision: vars.decision, reason: vars.reason }),
    onSuccess: async (_data, vars) => {
      msg.success(`Endorsement ${vars.decision}`)
      setPending(null)
      form.resetFields()
      await queryClient.invalidateQueries({ queryKey: ['endorsementInbox'] })
      if (pending) {
        await queryClient.invalidateQueries({ queryKey: ['endorsements', pending.ticket_id] })
        await queryClient.invalidateQueries({ queryKey: ['ticket', pending.ticket_id] })
      }
    },
    onError: (err) => msg.error(err.message),
  })

  const claim = useMutation({
    mutationFn: (id: string) => claimEndorsement(id),
    onSuccess: async () => {
      msg.success('Endorsement claimed')
      await queryClient.invalidateQueries({ queryKey: ['endorsementInbox'] })
    },
    onError: (err) => msg.error(err.message),
  })

  const openDecideModal = (row: EndorsementDto, kind: 'approved' | 'rejected') => {
    setDecision(kind)
    setPending(row)
  }

  const columns: ColumnsType<EndorsementDto> = [
    {
      title: 'Ticket',
      dataIndex: 'ticket_code',
      render: (code, row) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{code || row.ticket_id.slice(0, 8)}</Typography.Text>
          <Typography.Text type="secondary" ellipsis style={{ maxWidth: 320 }}>
            {row.ticket_title || ''}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: 'Ticket status',
      dataIndex: 'ticket_status',
      width: 160,
      render: (value) => value ? <StatusTag status={value} /> : '—',
    },
    {
      title: 'Priority',
      dataIndex: 'ticket_priority',
      width: 120,
      render: (value) => value ? <PriorityTag priority={value} /> : '—',
    },
    {
      title: 'Target',
      dataIndex: 'assigned_to_user_id',
      width: 140,
      render: (value) => value ? <Tag color="blue">direct</Tag> : <Tag color="purple">pool</Tag>,
    },
    {
      title: 'Reason',
      dataIndex: 'request_reason',
      ellipsis: true,
      render: (v) => v || <Typography.Text type="secondary">—</Typography.Text>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      width: 130,
      render: (s: EndorsementStatus) => {
        const colors = { pending: 'gold', approved: 'green', rejected: 'red' } as const
        return <Tag color={colors[s]}>{s}</Tag>
      },
    },
    {
      title: 'Requested',
      dataIndex: 'created_at',
      width: 170,
      render: (v) => fmtDateTime(v),
    },
    {
      title: '',
      width: 310,
      render: (_, row) => {
        if (row.status !== 'pending') return null
        return (
          <Space size={4} onClick={(e) => e.stopPropagation()}>
            {!row.assigned_to_user_id && (
              <Button size="small" icon={<UserOutlined />} loading={claim.isPending}
                      onClick={() => claim.mutate(row.id)}>
                Claim
              </Button>
            )}
            <Button size="small" type="primary" icon={<CheckCircleOutlined />}
                    onClick={() => openDecideModal(row, 'approved')}>
              Approve
            </Button>
            <Button size="small" danger icon={<CloseCircleOutlined />}
                    onClick={() => openDecideModal(row, 'rejected')}>
              Reject
            </Button>
          </Space>
        )
      },
    },
  ]

  return (
    <div style={{ padding: 24, display: 'grid', gap: 16 }}>
      {holder}
      <Flex justify="space-between" align="center" wrap="wrap" gap={12}>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>Avizator inbox</Typography.Title>
          <Typography.Text type="secondary">
            Supplementary endorsement requests targeted at you (direct) or open to the pool.
          </Typography.Text>
        </div>
        <Space>
          <Statistic
            value={(inbox.data?.items || []).filter(i => i.status === 'pending').length}
            suffix="pending"
            styles={{ content: { fontSize: 18 } }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => inbox.refetch()} />
        </Space>
      </Flex>

      <Flex gap={8} wrap="wrap">
        {STATUS_TABS.map((s) => (
          <Button
            key={s.key}
            type={tab === s.key ? 'primary' : 'default'}
            onClick={() => setTab(s.key)}
          >
            {s.label}
          </Button>
        ))}
      </Flex>

      {inbox.error && <Alert type="error" showIcon message={(inbox.error as Error).message} />}

      <div style={{ border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8, overflow: 'hidden' }}>
        <Table
          rowKey="id"
          loading={inbox.isLoading}
          columns={columns}
          dataSource={inbox.data?.items || []}
          onRow={(record) => ({ onClick: () => navigate(`/tickets/${record.ticket_id}`) })}
          rowClassName={() => 'tickora-row-clickable'}
          locale={{ emptyText: <Empty description="No endorsements" /> }}
          scroll={{ x: 1080 }}
          pagination={{ pageSize: 20, showSizeChanger: true }}
        />
      </div>

      <Modal
        title={decision === 'approved' ? 'Approve endorsement' : 'Reject endorsement'}
        open={!!pending}
        okText={decision === 'approved' ? 'Approve' : 'Reject'}
        okButtonProps={{ danger: decision === 'rejected', type: 'primary' }}
        confirmLoading={decide.isPending}
        onCancel={() => { setPending(null); form.resetFields() }}
        onOk={async () => {
          const values = await form.validateFields()
          decide.mutate({ id: pending!.id, decision, reason: values.reason?.trim() || undefined })
        }}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="reason"
            label="Reason (optional)"
            extra="Recorded on the endorsement decision."
          >
            <Input.TextArea rows={3} placeholder="Short rationale for the operator." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
