import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import {
  Alert, Button, Descriptions, Drawer, Empty, Flex, Form, Input, List, Modal, Select,
  Space, Table, Tabs, Tag, Typography, message, theme as antTheme,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  CheckCircleOutlined, CloseCircleOutlined, EditOutlined, PlayCircleOutlined,
  PaperClipOutlined, ReloadOutlined, RetweetOutlined, StopOutlined, UserSwitchOutlined,
} from '@ant-design/icons'
import {
  assignSector, assignToMe, assignToUser, cancelTicket, changePriority, closeTicket,
  createComment, deleteAttachment, deleteComment, downloadAttachmentUrl, getMe,
  getTicket, listAttachments, listComments, listTicketAudit, listTickets, markDone,
  registerAttachment, reopenTicket, requestAttachmentUpload, type AttachmentDto,
  type AuditEventDto, type CommentDto, type TicketDto,
} from '@/api/tickets'
import { useSessionStore } from '@/stores/sessionStore'

const STATUS_COLORS: Record<string, string> = {
  pending: 'default',
  assigned_to_sector: 'processing',
  in_progress: 'blue',
  waiting_for_user: 'gold',
  on_hold: 'orange',
  done: 'green',
  closed: 'success',
  reopened: 'purple',
  cancelled: 'red',
  duplicate: 'red',
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

function bytes(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function useSessionBootstrap() {
  const setUser = useSessionStore((s) => s.setUser)
  const query = useQuery({
    queryKey: ['me'],
    queryFn: getMe,
    staleTime: 60_000,
    retry: 1,
  })
  useEffect(() => {
    if (query.data) {
      setUser({
        id: query.data.user_id,
        username: query.data.username,
        email: query.data.email,
        firstName: query.data.first_name,
        lastName: query.data.last_name,
        roles: query.data.roles,
        sectors: query.data.sectors.map((s) => ({ sectorCode: s.sector_code, role: s.role })),
      })
    }
  }, [query.data, setUser])
  return query
}

function canAssignToMe(ticket: TicketDto, user: ReturnType<typeof useSessionStore.getState>['user']) {
  if (!user) return false
  const isAdmin = user.roles.includes('tickora_admin')
  const inSector = !!user.sectors?.some((s) => s.sectorCode === ticket.current_sector_code)
  return (isAdmin || inSector)
    && !ticket.assignee_user_id
    && ['pending', 'assigned_to_sector', 'reopened'].includes(ticket.status)
}

function canAssignToUser(ticket: TicketDto, user: ReturnType<typeof useSessionStore.getState>['user']) {
  if (!user) return false
  const isAdmin = user.roles.includes('tickora_admin')
  const isChief = !!user.sectors?.some((s) => s.sectorCode === ticket.current_sector_code && s.role === 'chief')
  return (isAdmin || isChief)
    && ['pending', 'assigned_to_sector', 'in_progress', 'reopened', 'on_hold'].includes(ticket.status)
}

function canAssignSector(ticket: TicketDto, user: ReturnType<typeof useSessionStore.getState>['user']) {
  if (!user) return false
  const isAdmin = user.roles.includes('tickora_admin')
  const isDistributor = user.roles.includes('tickora_distributor')
  const isChief = !!user.sectors?.some((s) => s.sectorCode === ticket.current_sector_code && s.role === 'chief')
  return (isAdmin || isDistributor || isChief) && ['pending', 'assigned_to_sector'].includes(ticket.status)
}

function canMarkDone(ticket: TicketDto, user: ReturnType<typeof useSessionStore.getState>['user']) {
  if (!user) return false
  const isAdmin = user.roles.includes('tickora_admin')
  const isChief = !!user.sectors?.some((s) => s.sectorCode === ticket.current_sector_code && s.role === 'chief')
  const isAssignee = ticket.assignee_user_id === user.id
  return (isAdmin || isChief || isAssignee)
    && ['in_progress', 'reopened', 'waiting_for_user', 'on_hold'].includes(ticket.status)
}

function canClose(ticket: TicketDto, user: ReturnType<typeof useSessionStore.getState>['user']) {
  if (!user) return false
  return ticket.status === 'done'
    && (user.roles.includes('tickora_admin') || ticket.created_by_user_id === user.id)
}

function canReopen(ticket: TicketDto, user: ReturnType<typeof useSessionStore.getState>['user']) {
  if (!user) return false
  return ['done', 'closed'].includes(ticket.status)
    && (user.roles.includes('tickora_admin') || ticket.created_by_user_id === user.id)
}

function canCancel(ticket: TicketDto, user: ReturnType<typeof useSessionStore.getState>['user']) {
  if (!user) return false
  const isAdmin = user.roles.includes('tickora_admin')
  const isDistributor = user.roles.includes('tickora_distributor')
  const isChief = !!user.sectors?.some((s) => s.sectorCode === ticket.current_sector_code && s.role === 'chief')
  return (isAdmin || isDistributor || isChief) && ['pending', 'assigned_to_sector'].includes(ticket.status)
}

function WorkflowActions({ ticket }: { ticket: TicketDto }) {
  const [form] = Form.useForm()
  const [modal, setModal] = useState<string | null>(null)
  const [msg, holder] = message.useMessage()
  const queryClient = useQueryClient()
  const user = useSessionStore((s) => s.user)

  const finish = async () => {
    setModal(null)
    form.resetFields()
    await queryClient.invalidateQueries({ queryKey: ['tickets'] })
    await queryClient.invalidateQueries({ queryKey: ['ticket', ticket.id] })
  }

  const run = useMutation({
    mutationFn: async ({ action, values }: { action: string; values: any }) => {
      if (action === 'assign_to_me') return assignToMe(ticket.id)
      if (action === 'assign_sector') return assignSector(ticket.id, values.sectorCode, values.reason)
      if (action === 'assign_to_user') return assignToUser(ticket.id, values.userId, values.reason)
      if (action === 'mark_done') return markDone(ticket.id, values.resolution)
      if (action === 'close') return closeTicket(ticket.id)
      if (action === 'reopen') return reopenTicket(ticket.id, values.reason)
      if (action === 'cancel') return cancelTicket(ticket.id, values.reason)
      if (action === 'priority') return changePriority(ticket.id, values.priority, values.reason)
      throw new Error('Unknown action')
    },
    onSuccess: async () => {
      msg.success('Ticket updated')
      await finish()
    },
    onError: (err) => msg.error(err.message),
  })

  const submitModal = async () => {
    const values = await form.validateFields()
    run.mutate({ action: modal!, values })
  }

  return (
    <>
      {holder}
      <Flex wrap="wrap" gap={8}>
        {canAssignToMe(ticket, user) && (
          <Button icon={<PlayCircleOutlined />} type="primary" loading={run.isPending}
                  onClick={() => run.mutate({ action: 'assign_to_me', values: {} })}>
            Assign to me
          </Button>
        )}
        {canAssignSector(ticket, user) && (
          <Button icon={<RetweetOutlined />} onClick={() => setModal('assign_sector')}>Assign sector</Button>
        )}
        {canAssignToUser(ticket, user) && (
          <Button icon={<UserSwitchOutlined />} onClick={() => setModal('assign_to_user')}>Assign user</Button>
        )}
        {canMarkDone(ticket, user) && (
          <Button icon={<CheckCircleOutlined />} onClick={() => setModal('mark_done')}>Mark done</Button>
        )}
        {canClose(ticket, user) && (
          <Button icon={<CloseCircleOutlined />} onClick={() => run.mutate({ action: 'close', values: {} })}>
            Close
          </Button>
        )}
        {canReopen(ticket, user) && (
          <Button icon={<ReloadOutlined />} onClick={() => setModal('reopen')}>Reopen</Button>
        )}
        {canCancel(ticket, user) && (
          <Button danger icon={<StopOutlined />} onClick={() => setModal('cancel')}>Cancel</Button>
        )}
        <Button icon={<EditOutlined />} onClick={() => setModal('priority')}>Priority</Button>
      </Flex>
      <Modal
        title={modal?.split('_').join(' ')}
        open={!!modal}
        okText="Apply"
        confirmLoading={run.isPending}
        onCancel={() => { setModal(null); form.resetFields() }}
        onOk={submitModal}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          {modal === 'assign_sector' && (
            <Form.Item name="sectorCode" label="Sector code" rules={[{ required: true }]}>
              <Input placeholder="s10" />
            </Form.Item>
          )}
          {modal === 'assign_to_user' && (
            <Form.Item name="userId" label="User ID" rules={[{ required: true }]}>
              <Input placeholder="Tickora user UUID" />
            </Form.Item>
          )}
          {modal === 'priority' && (
            <Form.Item name="priority" label="Priority" rules={[{ required: true }]}>
              <Select options={['low', 'medium', 'high', 'critical'].map((p) => ({ value: p, label: p }))} />
            </Form.Item>
          )}
          {modal === 'mark_done' && (
            <Form.Item name="resolution" label="Resolution" rules={[{ required: true, min: 5 }]}>
              <Input.TextArea rows={4} />
            </Form.Item>
          )}
          {['assign_sector', 'assign_to_user', 'priority', 'reopen', 'cancel'].includes(modal || '') && (
            <Form.Item name="reason" label="Reason" rules={['reopen', 'cancel'].includes(modal || '') ? [{ required: true, min: 3 }] : []}>
              <Input.TextArea rows={3} />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </>
  )
}

function CommentBox({ ticketId }: { ticketId: string }) {
  const [form] = Form.useForm()
  const [msg, holder] = message.useMessage()
  const queryClient = useQueryClient()
  const comments = useQuery({
    queryKey: ['comments', ticketId],
    queryFn: () => listComments(ticketId),
  })
  const add = useMutation({
    mutationFn: (values: { body: string; visibility: CommentDto['visibility'] }) =>
      createComment(ticketId, values.body, values.visibility),
    onSuccess: async () => {
      form.resetFields()
      await queryClient.invalidateQueries({ queryKey: ['comments', ticketId] })
      await queryClient.invalidateQueries({ queryKey: ['ticketAudit', ticketId] })
    },
    onError: (err) => msg.error(err.message),
  })
  const remove = useMutation({
    mutationFn: deleteComment,
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ['comments', ticketId] }),
    onError: (err) => msg.error(err.message),
  })

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {holder}
      <Form form={form} layout="vertical" initialValues={{ visibility: 'public' }} onFinish={(v) => add.mutate(v)}>
        <Form.Item name="body" rules={[{ required: true, min: 2 }]}>
          <Input.TextArea rows={3} placeholder="Add a comment" />
        </Form.Item>
        <Flex justify="space-between" align="center">
          <Form.Item name="visibility" style={{ marginBottom: 0 }}>
            <Select style={{ width: 130 }} options={[
              { value: 'public', label: 'Public' },
              { value: 'private', label: 'Private' },
            ]} />
          </Form.Item>
          <Button htmlType="submit" type="primary" loading={add.isPending}>Post</Button>
        </Flex>
      </Form>
      <List
        loading={comments.isLoading}
        dataSource={comments.data?.items || []}
        locale={{ emptyText: <Empty description="No comments" /> }}
        renderItem={(item) => (
          <List.Item
            actions={[
              <Button key="delete" size="small" type="link" danger onClick={() => remove.mutate(item.id)}>
                Delete
              </Button>,
            ]}
          >
            <List.Item.Meta
              title={<Space><Tag color={item.visibility === 'private' ? 'orange' : 'green'}>{item.visibility}</Tag><Typography.Text>{fmt(item.created_at)}</Typography.Text></Space>}
              description={<Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>{item.body}</Typography.Paragraph>}
            />
          </List.Item>
        )}
      />
    </div>
  )
}

function AttachmentUploader({ ticketId }: { ticketId: string }) {
  const [visibility, setVisibility] = useState<AttachmentDto['visibility']>('private')
  const [msg, holder] = message.useMessage()
  const queryClient = useQueryClient()
  const attachments = useQuery({
    queryKey: ['attachments', ticketId],
    queryFn: () => listAttachments(ticketId),
  })
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const req = await requestAttachmentUpload(ticketId, file, visibility)
      await fetch(req.upload_url, {
        method: 'PUT',
        headers: { 'Content-Type': file.type || 'application/octet-stream' },
        body: file,
      })
      return registerAttachment(ticketId, file, req.storage_key, visibility)
    },
    onSuccess: async () => {
      msg.success('Attachment uploaded')
      await queryClient.invalidateQueries({ queryKey: ['attachments', ticketId] })
      await queryClient.invalidateQueries({ queryKey: ['ticketAudit', ticketId] })
    },
    onError: (err) => msg.error(err.message),
  })
  const remove = useMutation({
    mutationFn: deleteAttachment,
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ['attachments', ticketId] }),
    onError: (err) => msg.error(err.message),
  })

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {holder}
      <Flex wrap="wrap" gap={8} align="center">
        <Select value={visibility} onChange={setVisibility} style={{ width: 130 }} options={[
          { value: 'public', label: 'Public' },
          { value: 'private', label: 'Private' },
        ]} />
        <Button icon={<PaperClipOutlined />} loading={upload.isPending}>
          <label style={{ cursor: 'pointer' }}>
            Upload
            <input
              type="file"
              hidden
              onChange={(event) => {
                const file = event.target.files?.[0]
                event.target.value = ''
                if (file) upload.mutate(file)
              }}
            />
          </label>
        </Button>
      </Flex>
      <List
        loading={attachments.isLoading}
        dataSource={attachments.data?.items || []}
        locale={{ emptyText: <Empty description="No attachments" /> }}
        renderItem={(item) => (
          <List.Item
            actions={[
              <Button key="download" size="small" type="link" href={downloadAttachmentUrl(item.id)} target="_blank">
                Download
              </Button>,
              <Button key="delete" size="small" type="link" danger onClick={() => remove.mutate(item.id)}>
                Delete
              </Button>,
            ]}
          >
            <List.Item.Meta
              title={<Space><Tag>{item.visibility}</Tag><Typography.Text>{item.file_name}</Typography.Text></Space>}
              description={`${bytes(item.size_bytes)} · ${item.content_type || 'application/octet-stream'} · scan ${item.scan_result || 'pending'}`}
            />
          </List.Item>
        )}
      />
    </div>
  )
}

function TicketAudit({ ticketId }: { ticketId: string }) {
  const audit = useQuery({
    queryKey: ['ticketAudit', ticketId],
    queryFn: () => listTicketAudit(ticketId),
  })
  return (
    <List
      loading={audit.isLoading}
      dataSource={audit.data?.items || []}
      locale={{ emptyText: <Empty description="No audit events" /> }}
      renderItem={(item: AuditEventDto) => (
        <List.Item>
          <List.Item.Meta
            title={<Space><Tag color="blue">{item.action}</Tag><Typography.Text>{fmt(item.created_at)}</Typography.Text></Space>}
            description={
              <div style={{ display: 'grid', gap: 4 }}>
                <Typography.Text type="secondary">{item.actor_username || item.actor_user_id || 'system'}</Typography.Text>
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify({ old_value: item.old_value, new_value: item.new_value, metadata: item.metadata }, null, 2)}
                </pre>
              </div>
            }
          />
        </List.Item>
      )}
    />
  )
}

function TicketDrawer({ ticketId }: { ticketId?: string }) {
  const navigate = useNavigate()
  const { token } = antTheme.useToken()
  const { data: ticket, isLoading, error } = useQuery({
    queryKey: ['ticket', ticketId],
    queryFn: () => getTicket(ticketId!),
    enabled: !!ticketId,
  })

  return (
    <Drawer
      title={ticket ? `${ticket.ticket_code} · ${ticket.title || 'Ticket'}` : 'Ticket'}
      open={!!ticketId}
      size="large"
      onClose={() => navigate('/tickets')}
      styles={{ body: { padding: 0 } }}
    >
      {error && <Alert type="error" message={error.message} showIcon style={{ margin: 16 }} />}
      {!error && !ticket && !isLoading && <Empty style={{ marginTop: 80 }} />}
      {ticket && (
        <div style={{ display: 'grid', gap: 16, padding: 16 }}>
          <div style={{
            border: `1px solid ${token.colorBorderSecondary}`,
            borderRadius: 8,
            padding: 16,
            display: 'grid',
            gap: 14,
          }}>
            <Space wrap>
              <Tag color={STATUS_COLORS[ticket.status]}>{ticket.status}</Tag>
              <Tag color={PRIORITY_COLORS[ticket.priority]}>{ticket.priority}</Tag>
              {ticket.current_sector_code && <Tag>{ticket.current_sector_code}</Tag>}
              {ticket.assignee_user_id && <Tag>assigned</Tag>}
            </Space>
            <Typography.Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{ticket.txt}</Typography.Paragraph>
            {ticket.resolution && (
              <Alert type="success" showIcon message="Resolution" description={ticket.resolution} />
            )}
          </div>

          <WorkflowActions ticket={ticket} />

          <Tabs
            items={[
              { key: 'comments', label: 'Comments', children: <CommentBox ticketId={ticket.id} /> },
              { key: 'attachments', label: 'Attachments', children: <AttachmentUploader ticketId={ticket.id} /> },
              { key: 'audit', label: 'Audit', children: <TicketAudit ticketId={ticket.id} /> },
            ]}
          />

          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label="Requester">
              {[ticket.requester_first_name, ticket.requester_last_name].filter(Boolean).join(' ') || ticket.requester_email || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="Created">{fmt(ticket.created_at)}</Descriptions.Item>
            <Descriptions.Item label="Updated">{fmt(ticket.updated_at)}</Descriptions.Item>
            <Descriptions.Item label="Assigned">{fmt(ticket.assigned_at)}</Descriptions.Item>
            <Descriptions.Item label="First response">{fmt(ticket.first_response_at)}</Descriptions.Item>
            <Descriptions.Item label="Done">{fmt(ticket.done_at)}</Descriptions.Item>
            <Descriptions.Item label="Closed">{fmt(ticket.closed_at)}</Descriptions.Item>
            <Descriptions.Item label="SLA">{ticket.sla_status || '-'} · {fmt(ticket.sla_due_at)}</Descriptions.Item>
          </Descriptions>
        </div>
      )}
    </Drawer>
  )
}

export function TicketsPage() {
  const navigate = useNavigate()
  const params = useParams()
  const { token } = antTheme.useToken()
  const [status, setStatus] = useState<string | undefined>()
  const [priority, setPriority] = useState<string | undefined>()
  const [sector, setSector] = useState<string | undefined>()
  const me = useSessionBootstrap()
  const tickets = useQuery({
    queryKey: ['tickets', status, priority, sector],
    queryFn: () => listTickets({ status, priority, current_sector_code: sector, limit: 100 }),
  })

  useEffect(() => {
    if (me.error) message.error(me.error.message)
  }, [me.error])

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
      width: 110,
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
      <Flex justify="space-between" align="center" wrap="wrap" gap={12}>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>Tickets</Typography.Title>
          <Typography.Text type="secondary">Operational queue with workflow actions</Typography.Text>
        </div>
        <Space wrap>
          <Select allowClear placeholder="Status" value={status} onChange={setStatus} style={{ width: 190 }}
                  options={['pending', 'assigned_to_sector', 'in_progress', 'done', 'closed', 'reopened', 'cancelled'].map((s) => ({ value: s, label: s }))} />
          <Select allowClear placeholder="Priority" value={priority} onChange={setPriority} style={{ width: 130 }}
                  options={['low', 'medium', 'high', 'critical'].map((p) => ({ value: p, label: p }))} />
          <Input allowClear placeholder="Sector" value={sector} onChange={(e) => setSector(e.target.value || undefined)}
                 style={{ width: 110 }} />
          <Button icon={<ReloadOutlined />} onClick={() => tickets.refetch()} />
        </Space>
      </Flex>

      {tickets.error && <Alert type="error" message={tickets.error.message} showIcon />}

      <div style={{ border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8, overflow: 'hidden' }}>
        <Table
          rowKey="id"
          loading={tickets.isLoading}
          columns={columns}
          dataSource={tickets.data?.items || []}
          pagination={false}
          onRow={(record) => ({ onClick: () => navigate(`/tickets/${record.id}`) })}
          locale={{ emptyText: <Empty description="No tickets match the current filters" /> }}
          rowClassName={() => 'tickora-row-clickable'}
          scroll={{ x: 860 }}
        />
      </div>

      <TicketDrawer ticketId={params.ticketId} />
    </div>
  )
}
