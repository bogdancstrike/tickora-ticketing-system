import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Button, Card, Col, Descriptions, Empty, Flex, Form, Input, Popconfirm, Row, Select,
  Space, Steps, Tag, Tooltip, Typography, message, theme as antTheme,
} from 'antd'
import {
  ArrowLeftOutlined, CheckSquareOutlined, DeleteOutlined, InfoCircleOutlined,
  PlusOutlined, ReloadOutlined, StopOutlined,
} from '@ant-design/icons'
import {
  deleteTicketMetadata, getTicket, getTicketOptions, listAssignableUsers,
  listTicketAudit, listTicketMetadata, removeSector, reviewTicket, setTicketMetadata,
  type ReviewTicketPayload, type TicketDto, type TicketMetadataDto,
} from '@/api/tickets'
import { useSessionStore } from '@/stores/sessionStore'
import { StatusTag } from '@/components/common/StatusTag'
import { PriorityTag } from '@/components/common/PriorityTag'
import { fmtRelative } from '@/components/common/format'
import { AuditTimeline } from '@/components/common/AuditTimeline'
import { ProductTour, TourInfoButton } from '@/components/common/ProductTour'

interface MetadataKeyDef {
  key: string
  label: string
  value_type?: 'string' | 'enum'
  options?: string[] | null
  description?: string | null
}

/**
 * Compact metadata editor used in the right-side sidebar. Lets a
 * distributor capture the few extra fields that don't fit the structured
 * sector/priority/category/type form (e.g. SLA tier, customer tier).
 */
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
      title={<Space size={6}><Typography.Text strong>Metadata</Typography.Text>{items.length > 0 && <Tag>{items.length}</Tag>}</Space>}
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


/**
 * Distributor review page (`/review/:ticketId`).
 *
 * UX principles applied (2026-05-10 redesign):
 *   - **One primary action**: the green "Apply review" button is the only
 *     visually-promoted CTA. "Close ticket" is demoted to a quiet link.
 *   - **Progressive disclosure**: routing fields (Where does this go?)
 *     come first; classification (What is it?) second; notes last. The
 *     three-step `Steps` strip at the top advertises this so the user
 *     doesn't feel a wall of fields.
 *   - **Hero stays scannable**: title + description + a single status/
 *     priority/sector row. No densely packed metadata.
 *   - **Sidebar persistence**: requester / metadata / audit don't move,
 *     so the user can refer to them while editing the form.
 *   - **Inline guidance**: sector field gets a tooltip explaining the
 *     distributor → chief hand-off rule (BRD §10).
 */
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
  const isDistributor = !!user?.roles.includes('tickora_distributor')
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

  const unassignSector = useMutation({
    mutationFn: (code: string) => removeSector(ticketId!, code),
    onSuccess: async () => {
      msg.success('Sector removed')
      await queryClient.invalidateQueries({ queryKey: ['ticket', ticketId] })
      await queryClient.invalidateQueries({ queryKey: ['reviewTickets'] })
    },
    onError: (err) => msg.error(err.message),
  })

  const review = useMutation({
    mutationFn: async (values: ReviewTicketPayload) => reviewTicket(ticketId!, values),
    onSuccess: async () => {
      msg.success('Review applied')
      await queryClient.invalidateQueries({ queryKey: ['ticket', ticketId] })
      await queryClient.invalidateQueries({ queryKey: ['ticketAudit', ticketId] })
      await queryClient.invalidateQueries({ queryKey: ['reviewTickets'] })
      await queryClient.invalidateQueries({ queryKey: ['monitorOverview'] })
      // Give the toast a beat to land before navigating away.
      setTimeout(() => navigate('/review'), 800)
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

  // Compute step progression so the Steps indicator shows real progress
  // as the distributor fills out the form.
  const stepValues = Form.useWatch([], form)
  const currentStep = useMemo(() => {
    if (!stepValues) return 0
    if (!stepValues.sector_code) return 0
    if (!stepValues.priority) return 1
    return 2
  }, [stepValues])

  if (!ticketId) return null
  if (ticket.isLoading) return <div style={{ padding: 80 }}><Empty description="Loading…" /></div>
  if (ticket.error) return <div style={{ padding: 24 }}><Alert type="error" showIcon message={ticket.error.message} /></div>
  if (!ticket.data) return <div style={{ padding: 80 }}><Empty /></div>

  const t: TicketDto = ticket.data
  const isOpen = ['pending', 'assigned_to_sector', 'in_progress', 'reopened'].includes(t.status)
  const sectors = Array.from(new Set([t.current_sector_code, ...(t.sector_codes || [])].filter(Boolean) as string[]))

  return (
    <div style={{ padding: 24, display: 'grid', gap: 16, maxWidth: 1280, margin: '0 auto' }}>
      {holder}

      {/* Top breadcrumb-style nav. Quiet, single line. */}
      <Flex justify="space-between" align="center" wrap="wrap" gap={12}>
        <Space size={8}>
          <Button type="link" icon={<ArrowLeftOutlined />} onClick={() => navigate('/review')} style={{ paddingLeft: 0 }}>
            Review queue
          </Button>
          <Typography.Text type="secondary">·</Typography.Text>
          <Typography.Text type="secondary" style={{ fontFamily: 'monospace' }}>{t.ticket_code}</Typography.Text>
        </Space>
        <Space>
          <TourInfoButton pageKey="review-ticket" />
          <Button icon={<ReloadOutlined />} onClick={() => ticket.refetch()} />
          <Button onClick={() => navigate(`/tickets/${t.id}`)}>Open ticket</Button>
        </Space>
      </Flex>

      {/* Hero — the *thing being reviewed*. Title front-and-center;
          status / priority / one-line meta on a single secondary row. */}
      <Card styles={{ body: { padding: 24 } }} data-tour-id="review-ticket-summary">
        <Typography.Title level={3} style={{ margin: 0, lineHeight: 1.25 }}>
          {t.title || 'Untitled ticket'}
        </Typography.Title>
        <Flex align="center" gap={8} wrap="wrap" style={{ marginTop: 10 }}>
          <StatusTag status={t.status} />
          <PriorityTag priority={t.priority} />
          {t.beneficiary_type && (
            <Tag color={t.beneficiary_type === 'external' ? 'orange' : 'default'}>
              {t.beneficiary_type}
            </Tag>
          )}
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Created {fmtRelative(t.created_at)} · Updated {fmtRelative(t.updated_at)}
          </Typography.Text>
        </Flex>
        {sectors.length > 0 && (
          <Flex align="center" gap={6} style={{ marginTop: 8 }} wrap="wrap">
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>Sectors:</Typography.Text>
            {sectors.map((code) => {
              const isPrimary = code === t.current_sector_code
              const canRemove = !isPrimary && (isAdmin || isDistributor || !!user?.sectors?.some(s => s.sectorCode === code && s.role === 'chief'))
              return (
                <Tag
                  key={code}
                  color={isPrimary ? 'blue' : undefined}
                  closable={canRemove}
                  onClose={() => unassignSector.mutate(code)}
                >
                  {code}{isPrimary && ' · primary'}
                </Tag>
              )
            })}
          </Flex>
        )}
        <Typography.Paragraph
          style={{
            whiteSpace: 'pre-wrap',
            marginTop: 16,
            marginBottom: 0,
            color: token.colorTextSecondary,
            background: token.colorFillAlter,
            borderRadius: 8,
            padding: 14,
          }}
        >
          {t.txt}
        </Typography.Paragraph>
      </Card>

      {/* Closed tickets show a banner — the form below is read-only ish. */}
      {!isOpen && (
        <Alert
          type="warning"
          showIcon
          message="This ticket has already moved past the review queue."
          description="Triage actions may not be applicable."
        />
      )}

      <Row gutter={[16, 16]}>
        {/* Triage form — three logical steps + one big primary CTA. */}
        <Col xs={24} lg={15} data-tour-id="review-ticket-form">
          <Card
            title={
              <Space size={8}>
                <CheckSquareOutlined />
                <span>Triage</span>
              </Space>
            }
            styles={{ body: { padding: 20 } }}
          >
            <Steps
              size="small"
              current={currentStep}
              items={[
                { title: 'Where does this go?' },
                { title: 'What is it?' },
                { title: 'Notes & decision' },
              ]}
              style={{ marginBottom: 24 }}
            />

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
              {/* Step 1 — routing target. */}
              <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
                Routing
              </Typography.Text>
              <Row gutter={12}>
                <Col xs={24} sm={12}>
                  <Form.Item
                    name="sector_code"
                    label={
                      <Space size={4}>
                        Sector
                        <Tooltip title="Distributors hand the ticket to a sector. The sector chief picks the operator unless you're an admin or chief yourself.">
                          <InfoCircleOutlined style={{ color: token.colorTextSecondary }} />
                        </Tooltip>
                      </Space>
                    }
                    rules={[{ required: true, message: 'Pick a sector to route this ticket' }]}
                  >
                    <Select
                      showSearch
                      placeholder="Choose a sector"
                      optionFilterProp="label"
                      options={(options.data?.sectors || []).map((s) => ({ value: s.code, label: `${s.code} · ${s.name}` }))}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12}>
                  <Form.Item
                    name="assignee_user_id"
                    label="Assignee (optional)"
                    extra={!canAssignUser ? "You can route to a sector; the chief assigns the operator." : undefined}
                  >
                    <Select
                      allowClear
                      showSearch
                      placeholder={canAssignUser ? "Pick an operator" : "Sector chief decides"}
                      optionFilterProp="label"
                      loading={users.isLoading}
                      disabled={!canAssignUser || !sectorCode}
                      options={(users.data?.items || []).map((u) => ({
                        value: u.id,
                        label: `${u.username || u.email || u.id} · ${u.membership_role}`,
                      }))}
                    />
                  </Form.Item>
                </Col>
              </Row>

              {/* Step 2 — classification. */}
              <Typography.Text strong style={{ display: 'block', margin: '12px 0 8px' }}>
                Classification
              </Typography.Text>
              <Row gutter={12}>
                <Col xs={24} sm={8}>
                  <Form.Item name="priority" label="Priority" rules={[{ required: true }]}>
                    <Select
                      options={(options.data?.priorities || []).map((p) => ({ value: p, label: p }))}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={8}>
                  <Form.Item name="category" label="Category">
                    <Select allowClear showSearch optionFilterProp="label" placeholder="—"
                            options={(options.data?.categories || []).map((v) => ({ value: v, label: v }))} />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={8}>
                  <Form.Item name="type" label="Type">
                    <Select allowClear showSearch optionFilterProp="label" placeholder="—"
                            options={(options.data?.types || []).map((v) => ({ value: v, label: v }))} />
                  </Form.Item>
                </Col>
              </Row>

              {/* Step 3 — notes. */}
              <Typography.Text strong style={{ display: 'block', margin: '12px 0 8px' }}>
                Notes
              </Typography.Text>
              <Form.Item
                name="private_comment"
                label="Distributor commentary"
                extra="Private — only staff working on the ticket will see this."
              >
                <Input.TextArea rows={3} placeholder="What should the operator know?" />
              </Form.Item>
              <Form.Item name="reason" label="Routing reason (optional)">
                <Input.TextArea rows={2} placeholder="Why this sector / priority?" />
              </Form.Item>

              {/* Decision — one promoted CTA, one quiet escape hatch. */}
              <Flex justify="space-between" align="center" wrap="wrap" gap={12} style={{ marginTop: 8 }}>
                <Popconfirm
                  title="Close this ticket without routing?"
                  description="Use this when the request isn't actionable. The routing reason becomes the cancellation justification."
                  onConfirm={() => review.mutate({ ...form.getFieldsValue(), close: true })}
                  okText="Close ticket"
                  okButtonProps={{ danger: true }}
                >
                  <Button type="text" danger icon={<StopOutlined />} loading={review.isPending}>
                    Close without routing
                  </Button>
                </Popconfirm>
                <Button
                  type="primary"
                  htmlType="submit"
                  size="large"
                  icon={<CheckSquareOutlined />}
                  loading={review.isPending}
                  disabled={!isOpen}
                >
                  Apply review
                </Button>
              </Flex>
            </Form>
          </Card>
        </Col>

        {/* Sidebar — context the distributor refers to while editing. */}
        <Col xs={24} lg={9} data-tour-id="review-ticket-sidebar">
          <div style={{ display: 'grid', gap: 16 }}>
            <Card title="Requester" styles={{ body: { padding: 16 } }}>
              <Descriptions size="small" column={1} colon={false}>
                <Descriptions.Item label="Name">
                  {[t.requester_first_name, t.requester_last_name].filter(Boolean).join(' ') || '—'}
                </Descriptions.Item>
                <Descriptions.Item label="Email">{t.requester_email || '—'}</Descriptions.Item>
                <Descriptions.Item label="Type">
                  <Tag color={t.beneficiary_type === 'external' ? 'orange' : 'default'}>
                    {t.beneficiary_type}
                  </Tag>
                </Descriptions.Item>
              </Descriptions>
            </Card>

            <MetadataPanel ticketId={t.id} metadataKeys={(options.data?.metadata_keys || []) as MetadataKeyDef[]} />

            <Card title="Recent activity" styles={{ body: { padding: 12 } }}>
              <AuditTimeline events={(audit.data?.items || []).slice(0, 6)} loading={audit.isLoading} />
            </Card>
          </div>
        </Col>
      </Row>
      <ProductTour
        pageKey="review-ticket"
        steps={[
          { target: '[data-tour-id="review-ticket-summary"]', content: 'This summary shows the request being reviewed, including status, priority, beneficiary type, timestamps, and current routing.' },
          { target: '[data-tour-id="review-ticket-form"]', content: 'Use the review form to route the ticket to the right sector, set priority/category/type, add a private decision note, and optionally close clear non-actionable requests.' },
          { target: '[data-tour-id="review-ticket-sidebar"]', content: 'The sidebar keeps supporting context close by: metadata fields, requester details, and recent audit activity used to justify the routing decision.' },
        ]}
      />
    </div>
  )
}
