import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Button, Card, Col, Descriptions, Empty, Flex, Form, Input, Popconfirm, Row, Select,
  Space, Tag, Typography, message, theme as antTheme,
} from 'antd'
import {
  ArrowLeftOutlined, CheckSquareOutlined, DeleteOutlined, PlusOutlined, ReloadOutlined,
  StopOutlined,
} from '@ant-design/icons'
import {
  deleteTicketMetadata, getTicket, getTicketOptions, listAssignableUsers,
  listTicketAudit, listTicketMetadata, reviewTicket, setTicketMetadata,
  type ReviewTicketPayload, type TicketDto, type TicketMetadataDto,
} from '@/api/tickets'
import { useSessionStore } from '@/stores/sessionStore'
import { StatusTag } from '@/components/common/StatusTag'
import { PriorityTag } from '@/components/common/PriorityTag'
import { fmtDateTime, fmtRelative } from '@/components/common/format'
import { AuditTimeline } from '@/components/common/AuditTimeline'

interface MetadataKeyDef {
  key: string
  label: string
  value_type?: 'string' | 'enum'
  options?: string[] | null
  description?: string | null
}

function MetadataPanel({
  ticketId, metadataKeys,
}: {
  ticketId: string
  metadataKeys: MetadataKeyDef[]
}) {
  const [adding, setAdding] = useState(false)
  const [pendingKey, setPendingKey] = useState<string | undefined>()
  const [pendingValue, setPendingValue] = useState<string>('')
  const [msg, holder] = message.useMessage()
  const queryClient = useQueryClient()

  const meta = useQuery({
    queryKey: ['ticketMetadata', ticketId],
    queryFn: () => listTicketMetadata(ticketId),
  })

  const set = useMutation({
    mutationFn: (payload: { key: string; value: string; label?: string }) =>
      setTicketMetadata(ticketId, payload),
    onSuccess: async () => {
      msg.success('Metadata saved')
      setAdding(false)
      setPendingKey(undefined)
      setPendingValue('')
      await queryClient.invalidateQueries({ queryKey: ['ticketMetadata', ticketId] })
    },
    onError: (err) => msg.error(err.message),
  })

  const remove = useMutation({
    mutationFn: (key: string) => deleteTicketMetadata(ticketId, key),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ['ticketMetadata', ticketId] }),
    onError: (err) => msg.error(err.message),
  })

  const items: TicketMetadataDto[] = meta.data?.items || []
  const used = new Set(items.map((m) => m.key))
  const available = metadataKeys.filter((k) => !used.has(k.key))
  const def = metadataKeys.find((k) => k.key === pendingKey)
  const hasOptions = !!(def?.options && def.options.length)

  return (
    <Card
      title={<Space><Typography.Text strong>Metadata</Typography.Text>{items.length > 0 && <Tag>{items.length}</Tag>}</Space>}
      extra={!adding && (
        <Button size="small" icon={<PlusOutlined />} onClick={() => setAdding(true)} disabled={available.length === 0}>
          Add
        </Button>
      )}
      styles={{ body: { padding: 12 } }}
    >
      {holder}
      {items.length === 0 && !adding && (
        <Typography.Text type="secondary">No metadata captured yet.</Typography.Text>
      )}
      {items.length > 0 && (
        <div style={{ display: 'grid', gap: 6, marginBottom: adding ? 12 : 0 }}>
          {items.map((m) => (
            <Flex key={m.key} justify="space-between" align="center" gap={8}
                  style={{ padding: '6px 10px', background: 'rgba(0,0,0,0.03)', borderRadius: 6 }}>
              <Space size={8}>
                <Tag color="blue">{m.label || m.key}</Tag>
                <Typography.Text strong>{m.value}</Typography.Text>
              </Space>
              <Button type="text" danger size="small" icon={<DeleteOutlined />} onClick={() => remove.mutate(m.key)} />
            </Flex>
          ))}
        </div>
      )}
      {adding && (
        <div style={{ display: 'grid', gap: 8 }}>
          <Flex gap={8} wrap="wrap" align="center">
            <Select
              style={{ minWidth: 200 }}
              placeholder="Select metadata key"
              value={pendingKey}
              onChange={(v) => { setPendingKey(v); setPendingValue('') }}
              showSearch
              optionFilterProp="label"
              options={available.map((k) => ({ value: k.key, label: k.label, title: k.description || undefined }))}
            />
            {hasOptions ? (
              <Select
                style={{ flex: 1, minWidth: 160 }}
                placeholder="Choose a value"
                value={pendingValue || undefined}
                onChange={setPendingValue}
                options={(def!.options as string[]).map((v) => ({ value: v, label: v }))}
              />
            ) : (
              <Input
                placeholder={def ? `Enter ${def.label.toLowerCase()}` : 'Value'}
                value={pendingValue}
                onChange={(e) => setPendingValue(e.target.value)}
                style={{ flex: 1, minWidth: 160 }}
                onPressEnter={() => {
                  if (pendingKey && pendingValue) set.mutate({ key: pendingKey, value: pendingValue, label: def?.label })
                }}
              />
            )}
            <Button type="primary" size="small" loading={set.isPending}
                    disabled={!pendingKey || !pendingValue}
                    onClick={() => set.mutate({ key: pendingKey!, value: pendingValue, label: def?.label })}>
              Save
            </Button>
            <Button size="small" onClick={() => { setAdding(false); setPendingKey(undefined); setPendingValue('') }}>
              Cancel
            </Button>
          </Flex>
          {def?.description && <Typography.Text type="secondary" style={{ fontSize: 12 }}>{def.description}</Typography.Text>}
        </div>
      )}
    </Card>
  )
}

export function ReviewTicketPage() {
  const { ticketId } = useParams<{ ticketId: string }>()
  const navigate = useNavigate()
  const [form] = Form.useForm<ReviewTicketPayload>()
  const [sectorCode, setSectorCode] = useState<string | undefined>()
  const [msg, holder] = message.useMessage()
  const queryClient = useQueryClient()
  const { token } = antTheme.useToken()
  const user = useSessionStore((s) => s.user)
  const isAdmin = !!user?.roles.includes('tickora_admin')
  const isChiefOfTarget = !!sectorCode && !!user?.sectors?.some((s) => s.sectorCode === sectorCode && s.role === 'chief')
  const canAssignUser = isAdmin || isChiefOfTarget

  const ticket = useQuery({
    queryKey: ['ticket', ticketId],
    queryFn: () => getTicket(ticketId!),
    enabled: !!ticketId,
  })

  const options = useQuery({
    queryKey: ['ticketOptions'],
    queryFn: getTicketOptions,
    staleTime: 300_000,
  })

  const users = useQuery({
    queryKey: ['assignableUsers', sectorCode],
    queryFn: () => listAssignableUsers(sectorCode),
    enabled: !!sectorCode && canAssignUser,
    staleTime: 60_000,
  })

  const audit = useQuery({
    queryKey: ['ticketAudit', ticketId],
    queryFn: () => listTicketAudit(ticketId!),
    enabled: !!ticketId,
  })

  const review = useMutation({
    mutationFn: async (values: ReviewTicketPayload) => reviewTicket(ticketId!, values),
    onSuccess: async () => {
      msg.success('Review applied')
      await queryClient.invalidateQueries({ queryKey: ['ticket', ticketId] })
      await queryClient.invalidateQueries({ queryKey: ['ticketAudit', ticketId] })
      await queryClient.invalidateQueries({ queryKey: ['reviewTickets'] })
    },
    onError: (err) => msg.error(err.message),
  })

  // Hydrate the form from ticket data once it loads
  useEffect(() => {
    if (ticket.data) {
      const t = ticket.data
      setSectorCode(t.current_sector_code || undefined)
      form.setFieldsValue({
        sector_code: t.current_sector_code || undefined,
        priority: t.priority,
        category: t.category || undefined,
        type: t.type || undefined,
        assignee_user_id: t.assignee_user_id || undefined,
      })
    }
  }, [ticket.data, form])

  if (!ticketId) return null
  if (ticket.isLoading) return <div style={{ padding: 80 }}><Empty description="Loading…" /></div>
  if (ticket.error) return <div style={{ padding: 24 }}><Alert type="error" showIcon message={ticket.error.message} /></div>
  if (!ticket.data) return <div style={{ padding: 80 }}><Empty /></div>

  const t: TicketDto = ticket.data
  const isOpen = ['pending', 'assigned_to_sector', 'in_progress', 'reopened'].includes(t.status)

  return (
    <div style={{ padding: 24, display: 'grid', gap: 16 }}>
      {holder}

      {/* Header */}
      <Flex justify="space-between" align="center" wrap="wrap" gap={12}>
        <Space size={8}>
          <Button type="link" icon={<ArrowLeftOutlined />} onClick={() => navigate('/review')} style={{ paddingLeft: 0 }}>
            Review queue
          </Button>
          <Typography.Text type="secondary">·</Typography.Text>
          <Typography.Text type="secondary" style={{ fontFamily: 'monospace' }}>{t.ticket_code}</Typography.Text>
        </Space>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => ticket.refetch()} />
          <Button onClick={() => navigate(`/tickets/${t.id}`)}>Open ticket</Button>
        </Space>
      </Flex>

      {/* Hero */}
      <Card>
        <Space size={8} style={{ marginBottom: 8 }}>
          <StatusTag status={t.status} />
          <PriorityTag priority={t.priority} />
          {t.current_sector_code && <Tag color="cyan">{t.current_sector_code}</Tag>}
          {t.beneficiary_type && <Tag>{t.beneficiary_type}</Tag>}
        </Space>
        <Typography.Title level={3} style={{ margin: 0 }}>{t.title || 'Untitled ticket'}</Typography.Title>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Created {fmtRelative(t.created_at)} · Updated {fmtRelative(t.updated_at)}
        </Typography.Text>
        <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginTop: 14, marginBottom: 0 }}>
          {t.txt}
        </Typography.Paragraph>
      </Card>

      <Row gutter={[16, 16]}>
        {/* Review form */}
        <Col xs={24} lg={14}>
          <Card title="Triage">
            {!isOpen && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 16 }}
                message="This ticket has already moved past the review queue."
                description="Triage actions may not be applicable."
              />
            )}
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
              <Row gutter={12}>
                <Col xs={24} sm={12}>
                  <Form.Item name="sector_code" label="Sector" rules={[{ required: true }]}>
                    <Select
                      showSearch
                      optionFilterProp="label"
                      options={(options.data?.sectors || []).map((s) => ({ value: s.code, label: `${s.code} · ${s.name}` }))}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12}>
                  <Form.Item name="priority" label="Priority" rules={[{ required: true }]}>
                    <Select options={(options.data?.priorities || []).map((p) => ({ value: p, label: p }))} />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={12}>
                <Col xs={24} sm={12}>
                  <Form.Item name="category" label="Category">
                    <Select allowClear showSearch optionFilterProp="label"
                            options={(options.data?.categories || []).map((v) => ({ value: v, label: v }))} />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12}>
                  <Form.Item name="type" label="Type">
                    <Select allowClear showSearch optionFilterProp="label"
                            options={(options.data?.types || []).map((v) => ({ value: v, label: v }))} />
                  </Form.Item>
                </Col>
              </Row>

              {canAssignUser ? (
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
              ) : (
                <Alert type="info" showIcon style={{ marginBottom: 12 }}
                       message="Sector-level routing only"
                       description="Distributors route tickets to a sector. The sector chief picks the operator." />
              )}

              <Form.Item name="private_comment" label="Distributor commentary">
                <Input.TextArea rows={3} placeholder="Internal notes for the operator (private)" />
              </Form.Item>
              <Form.Item name="reason" label="Routing reason">
                <Input.TextArea rows={2} />
              </Form.Item>

              <Flex justify="space-between" wrap="wrap" gap={8}>
                <Popconfirm
                  title="Close ticket prematurely?"
                  description="The ticket will be cancelled with the routing reason as justification."
                  onConfirm={() => review.mutate({ ...form.getFieldsValue(), close: true })}
                  okText="Yes, close"
                  okButtonProps={{ danger: true }}
                >
                  <Button danger icon={<StopOutlined />} loading={review.isPending}>Close ticket</Button>
                </Popconfirm>
                <Button type="primary" htmlType="submit" icon={<CheckSquareOutlined />} loading={review.isPending}>
                  Apply review
                </Button>
              </Flex>
            </Form>
          </Card>
        </Col>

        {/* Sidebar */}
        <Col xs={24} lg={10}>
          <div style={{ display: 'grid', gap: 16 }}>
            <Card title="Requester">
              <Descriptions size="small" column={1} colon={false}>
                <Descriptions.Item label="Name">
                  {[t.requester_first_name, t.requester_last_name].filter(Boolean).join(' ') || '—'}
                </Descriptions.Item>
                <Descriptions.Item label="Email">{t.requester_email || '—'}</Descriptions.Item>
                <Descriptions.Item label="Type"><Tag>{t.beneficiary_type}</Tag></Descriptions.Item>
              </Descriptions>
            </Card>

            <MetadataPanel ticketId={t.id} metadataKeys={(options.data?.metadata_keys || []) as MetadataKeyDef[]} />

            <Card title="Recent activity" styles={{ body: { padding: 12 } }}>
              <AuditTimeline events={(audit.data?.items || []).slice(0, 6)} loading={audit.isLoading} />
            </Card>
          </div>
        </Col>
      </Row>
    </div>
  )
}
