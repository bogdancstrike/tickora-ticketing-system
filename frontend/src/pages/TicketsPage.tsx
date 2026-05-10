import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ProductTour, TourInfoButton } from '@/components/common/ProductTour'
import {
  Alert, Button, Card, Checkbox, Col, Descriptions, Empty, Flex, Form, Input, Modal, Row, Select,
  Space, Table, Tag, Typography, message, theme as antTheme, Upload, Statistic, Spin,
} from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import type { SorterResult } from 'antd/es/table/interface'
import type { UploadFile, UploadProps } from 'antd'
import {
  CheckCircleOutlined, CloseCircleOutlined, EditOutlined, PlayCircleOutlined,
  PaperClipOutlined, PlusOutlined, ReloadOutlined, RetweetOutlined, StopOutlined, UserSwitchOutlined,
  UserAddOutlined, UserDeleteOutlined, DownOutlined, UserOutlined,
} from '@ant-design/icons'
import { Dropdown } from 'antd'
import {
  addAssignee, addSector, assignSector, assignToMe, assignToUser, cancelTicket, changePriority, closeTicket,
  createComment, deleteAttachment, deleteComment, downloadAttachmentUrl, getMe,
  getTicket, getTicketOptions, listAssignableUsers, listAttachments, listComments,
  listTicketAudit, listTickets, markDone, registerAttachment, reopenTicket, requestAttachmentUpload,
  deleteTicket, listTicketMetadata, removeAssignee, removeSector,
  type AttachmentDto,
  type TicketDto,
} from '@/api/tickets'
import { useSessionStore } from '@/stores/sessionStore'
import { StatusTag, STATUS_OPTIONS } from '@/components/common/StatusTag'
import { PriorityTag } from '@/components/common/PriorityTag'
import { StatusChanger } from '@/components/common/StatusChanger'
import { fmtDateTime, fmtBytes } from '@/components/common/format'
import { AuditTimeline } from '@/components/common/AuditTimeline'

const fmt = fmtDateTime
const bytes = fmtBytes

function ticketSectorCodes(ticket: TicketDto): string[] {
  const codes = ticket.sector_codes?.length ? ticket.sector_codes : []
  return Array.from(new Set([ticket.current_sector_code, ...codes].filter(Boolean) as string[]))
}

function ticketAssigneeIds(ticket: TicketDto): string[] {
  const userIds = ticket.assignee_user_ids?.length ? ticket.assignee_user_ids : []
  return Array.from(new Set([ticket.assignee_user_id, ...userIds].filter(Boolean) as string[]))
}

function shortUserId(userId: string): string {
  return `${userId.slice(0, 8)}…`
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
        hasRootGroup: query.data.has_root_group,
      })
    }
  }, [query.data, setUser])
  return query
}

function canAssignToMe(ticket: TicketDto, user: ReturnType<typeof useSessionStore.getState>['user']) {
  if (!user) return false
  const isAdmin = user.roles.includes('tickora_admin')
  const sectors = ticketSectorCodes(ticket)
  const inSector = !!user.sectors?.some((s) => sectors.includes(s.sectorCode))
  return (isAdmin || inSector)
    && ticketAssigneeIds(ticket).length === 0
    && ['pending', 'assigned_to_sector', 'reopened'].includes(ticket.status)
}

function canAssignToUser(ticket: TicketDto, user: ReturnType<typeof useSessionStore.getState>['user']) {
  if (!user) return false
  const isAdmin = user.roles.includes('tickora_admin')
  const isDistributor = user.roles.includes('tickora_distributor')
  const isChief = !!user.sectors?.some((s) => s.sectorCode === ticket.current_sector_code && s.role === 'chief')
  return (isAdmin || isDistributor || isChief)
    && ['pending', 'assigned_to_sector', 'in_progress', 'reopened'].includes(ticket.status)
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
  const isAssignee = !!user.id && ticketAssigneeIds(ticket).includes(user.id)
  return (isAdmin || isChief || isAssignee)
    && ['in_progress', 'reopened'].includes(ticket.status)
}

function canClose(ticket: TicketDto, user: ReturnType<typeof useSessionStore.getState>['user']) {
  if (!user) return false
  const isRequesterEmail = ticket.beneficiary_type === 'external' && !!user.email && ticket.requester_email === user.email
  const isRequester = ticket.created_by_user_id === user.id || (!!user.id && ticket.beneficiary_user_id === user.id) || isRequesterEmail
  return ticket.status === 'done'
    && (user.roles.includes('tickora_admin') || isRequester)
}

function canReopen(ticket: TicketDto, user: ReturnType<typeof useSessionStore.getState>['user']) {
  if (!user) return false
  const isRequesterEmail = ticket.beneficiary_type === 'external' && !!user.email && ticket.requester_email === user.email
  const isRequester = ticket.created_by_user_id === user.id || (!!user.id && ticket.beneficiary_user_id === user.id) || isRequesterEmail
  return ['done', 'closed'].includes(ticket.status)
    && (user.roles.includes('tickora_admin') || isRequester)
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
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useSessionStore((s) => s.user)
  const options = useQuery({
    queryKey: ['ticketOptions'],
    queryFn: getTicketOptions,
    staleTime: 300_000,
  })
  const assignable = useQuery({
    queryKey: ['assignableUsers', ticket.current_sector_code],
    queryFn: () => listAssignableUsers(ticket.current_sector_code || undefined),
    enabled: !!ticket.current_sector_code,
    staleTime: 60_000,
  })

  const isClosed = ['done', 'closed', 'cancelled'].includes(ticket.status)

  const finish = async () => {
    setModal(null)
    form.resetFields()
    await queryClient.invalidateQueries({ queryKey: ['tickets'] })
    await queryClient.invalidateQueries({ queryKey: ['ticket', ticket.id] })
    await queryClient.invalidateQueries({ queryKey: ['monitorOverview'] })
    await queryClient.invalidateQueries({ queryKey: ['monitorSector'] })
    await queryClient.invalidateQueries({ queryKey: ['monitorUser'] })
  }

  const run = useMutation({
    mutationFn: async ({ action, values }: { action: string; values: any }) => {
      if (action === 'assign_to_me') return assignToMe(ticket.id)
      if (action === 'assign_sector') return assignSector(ticket.id, values.sectorCode, values.reason)
      if (action === 'assign_to_user') return assignToUser(ticket.id, values.userId, values.reason)
      if (action === 'unassign_me') {
        if (!user?.id) throw new Error('No current user')
        return removeAssignee(ticket.id, user.id)
      }
      if (action === 'mark_done') return markDone(ticket.id, values.resolution)
      if (action === 'close') return closeTicket(ticket.id)
      if (action === 'reopen') return reopenTicket(ticket.id, values.reason)
      if (action === 'cancel') return cancelTicket(ticket.id, values.reason)
      if (action === 'priority') return changePriority(ticket.id, values.priority, values.reason)
      if (action === 'delete') return deleteTicket(ticket.id)
      throw new Error('Unknown action')
    },
    onSuccess: async (_, vars) => {
      msg.success(`Ticket ${vars.action === 'delete' ? 'deleted' : 'updated'}`)
      if (vars.action === 'delete') {
        navigate('/tickets')
      } else {
        await finish()
      }
    },
    onError: (err) => msg.error(err.message),
  })

  const submitModal = async () => {
    const values = await form.validateFields()
    run.mutate({ action: modal!, values })
  }

  // Build a single Assign menu when at least one assign option is available
  const assignItems: { key: string; label: string; icon: React.ReactNode }[] = []
  if (canAssignToMe(ticket, user)) assignItems.push({ key: 'assign_to_me', label: 'Assign to me', icon: <PlayCircleOutlined /> })
  if (canAssignSector(ticket, user)) assignItems.push({ key: 'assign_sector', label: 'Assign to sector…', icon: <RetweetOutlined /> })
  if (canAssignToUser(ticket, user)) assignItems.push({ key: 'assign_to_user', label: 'Assign to user…', icon: <UserSwitchOutlined /> })

  const isCurrentAssignee = !!user?.id && ticketAssigneeIds(ticket).includes(user.id)
  const canUnassign = isCurrentAssignee

  return (
    <>
      {holder}
      <Flex wrap="wrap" gap={8}>
        {assignItems.length > 0 && (
          <Dropdown
            menu={{
              items: assignItems,
              onClick: ({ key }) => {
                if (key === 'assign_to_me') run.mutate({ action: 'assign_to_me', values: {} })
                else setModal(key)
              },
            }}
          >
            <Button type="primary" icon={<UserAddOutlined />} loading={run.isPending}>
              Assign <DownOutlined />
            </Button>
          </Dropdown>
        )}
        {canUnassign && (
          <Button
            icon={<UserDeleteOutlined />}
            loading={run.isPending}
            onClick={() => setModal('unassign_me')}
          >
            Unassign me
          </Button>
        )}
        <StatusChanger ticket={ticket} mode="button" />
        {!isClosed && (
          <Button icon={<EditOutlined />} onClick={() => setModal('priority')}>Priority</Button>
        )}
        {user?.roles.includes('tickora_admin') && (
           <Button danger type="dashed" loading={run.isPending} onClick={() => {
             Modal.confirm({
               title: 'Delete ticket?',
               content: 'This will soft-delete the ticket. It will not appear in lists.',
               okText: 'Yes, Delete',
               okType: 'danger',
               onOk: () => run.mutate({ action: 'delete', values: {} })
             })
           }}>Delete</Button>
        )}
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
              <Select
                showSearch
                optionFilterProp="label"
                options={(options.data?.sectors || []).map((s) => ({
                  value: s.code,
                  label: `${s.code} · ${s.name}`,
                }))}
              />
            </Form.Item>
          )}
          {modal === 'assign_to_user' && (
            <Form.Item name="userId" label="User ID" rules={[{ required: true }]}>
              <Select
                showSearch
                optionFilterProp="label"
                loading={assignable.isLoading}
                options={(assignable.data?.items || []).map((u) => ({
                  value: u.id,
                  label: `${u.username || u.email || u.id} · ${u.sector_code} ${u.membership_role}`,
                }))}
              />
            </Form.Item>
          )}
          {modal === 'priority' && (
            <Form.Item name="priority" label="Priority" rules={[{ required: true }]}>
              <Select options={(options.data?.priorities || ['low', 'medium', 'high', 'critical']).map((p) => ({ value: p, label: p }))} />
            </Form.Item>
          )}
          {modal === 'mark_done' && (
            <Form.Item name="resolution" label="Resolution (optional)">
              <Input.TextArea rows={4} placeholder="How was this ticket resolved?" />
            </Form.Item>
          )}
          {modal === 'unassign_me' && (
            <Alert type="info" showIcon style={{ marginBottom: 12 }}
                   message="Remove yourself from this ticket"
                   description="Only your assignment will be removed. Other assignees stay on the ticket." />
          )}
          {['assign_sector', 'assign_to_user', 'priority', 'reopen', 'cancel'].includes(modal || '') && (
            <Form.Item name="reason" label="Reason"
                       rules={['reopen', 'cancel'].includes(modal || '') ? [{ required: true, min: 3 }] : []}>
              <Input.TextArea rows={3} />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </>
  )
}

function authorInitials(name: string): string {
  return name.split(/[\s.@]+/).filter(Boolean).slice(0, 2).map(s => s[0]?.toUpperCase()).join('') || '?'
}

function CommentBox({
  ticketId, disabled, ticket,
}: {
  ticketId: string
  disabled?: boolean
  ticket?: TicketDto
}) {
  const [form] = Form.useForm()
  const [msg, holder] = message.useMessage()
  const queryClient = useQueryClient()
  const user = useSessionStore((s) => s.user)
  const [fileList, setFileList] = useState<UploadFile[]>([])

  // Operators (staff working on the ticket) can post private comments;
  // beneficiaries / external requesters are public-only.
  const isAdmin = !!user?.roles.includes('tickora_admin')
  const isAuditor = !!user?.roles.includes('tickora_auditor')
  const isDistributor = !!user?.roles.includes('tickora_distributor')
  const inSector = !!(ticket?.current_sector_code && user?.sectors?.some(s => s.sectorCode === ticket.current_sector_code))
  const isStaff = isAdmin || isAuditor || isDistributor || inSector
  const canPostPrivate = isStaff

  // Only assigned operators (or chiefs/admins) can post at all when staff;
  // requesters always retain public commenting on their own tickets.
  const isAssignee = !!ticket && ticket.assignee_user_id === user?.id
  const isChiefOfTicket = !!(ticket?.current_sector_code && user?.sectors?.some(s => s.sectorCode === ticket.current_sector_code && s.role === 'chief'))
  const isRequester = !!ticket && (
    (ticket.beneficiary_type === 'external' && !!user?.email && ticket.requester_email === user?.email)
    || ticket.created_by_user_id === user?.id
    || (!!user?.id && ticket.beneficiary_user_id === user.id)
  )
  const canPostAtAll = isAdmin || isChiefOfTicket || isAssignee || isRequester || isDistributor

  const comments = useQuery({
    queryKey: ['comments', ticketId],
    queryFn: () => listComments(ticketId),
  })

  const add = useMutation({
    mutationFn: async (values: { body: string; is_public?: boolean }) => {
      const visibility = (canPostPrivate ? values.is_public !== false : true) ? 'public' : 'private'
      const comment = await createComment(ticketId, values.body, visibility)
      
      // Sequential uploads for any attached files
      for (const fileItem of fileList) {
        if (!fileItem.originFileObj) continue
        const file = fileItem.originFileObj as File
        const req = await requestAttachmentUpload(ticketId, file)
        await fetch(req.upload_url, {
          method: 'PUT',
          headers: { 'Content-Type': file.type || 'application/octet-stream' },
          body: file,
        })
        await registerAttachment(ticketId, file, req.storage_key, comment.id)
      }
      return comment
    },
    onSuccess: async () => {
      form.resetFields()
      setFileList([])
      await queryClient.invalidateQueries({ queryKey: ['comments', ticketId] })
      await queryClient.invalidateQueries({ queryKey: ['attachments', ticketId] })
      await queryClient.invalidateQueries({ queryKey: ['ticketAudit', ticketId] })
      msg.success('Comment posted')
    },
    onError: (err) => msg.error(err.message),
  })

  const remove = useMutation({
    mutationFn: deleteComment,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['comments', ticketId] })
      await queryClient.invalidateQueries({ queryKey: ['attachments', ticketId] })
    },
    onError: (err) => msg.error(err.message),
  })

  const { data: allAttachments } = useQuery({
    queryKey: ['attachments', ticketId],
    queryFn: () => listAttachments(ticketId),
  })

  const uploadProps: UploadProps = {
    onRemove: (file) => {
      const index = fileList.indexOf(file)
      const newFileList = fileList.slice()
      newFileList.splice(index, 1)
      setFileList(newFileList)
    },
    beforeUpload: (file) => {
      setFileList([...fileList, file])
      return false
    },
    fileList,
    multiple: true,
  }

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      {holder}
      {!disabled && canPostAtAll && (
        <div style={{ padding: 12, border: '1px solid rgba(0,0,0,0.06)', borderRadius: 8 }}>
          <Form form={form} layout="vertical" initialValues={{ is_public: true }} onFinish={(v) => add.mutate(v)}>
            <Form.Item name="body" rules={[{ required: true, min: 2 }]} style={{ marginBottom: 8 }}>
              <Input.TextArea rows={3} placeholder="Write a comment…" />
            </Form.Item>
            
            <div style={{ marginBottom: 12 }}>
              <Upload {...uploadProps}>
                <Button size="small" icon={<PaperClipOutlined />}>Attach files</Button>
              </Upload>
            </div>

            <Flex justify="space-between" align="center">
              {canPostPrivate ? (
                <Form.Item name="is_public" valuePropName="checked" style={{ marginBottom: 0 }}>
                  <Checkbox>Visible to requester (public)</Checkbox>
                </Form.Item>
              ) : (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Posted as a public comment.
                </Typography.Text>
              )}
              <Button htmlType="submit" type="primary" loading={add.isPending}>Post comment</Button>
            </Flex>
          </Form>
        </div>
      )}
      {disabled && <Alert type="info" message="Comments are disabled for closed tickets." />}
      {!disabled && !canPostAtAll && (
        <Alert type="info" showIcon
               message="You can read this conversation but only assigned operators (or the requester) can post."  />
      )}
      {(comments.data?.items || []).length === 0 && !comments.isLoading && (
        <Empty description="No comments yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}
      <div style={{ display: 'grid', gap: 8 }}>
        {(comments.data?.items || []).map((item) => {
          const display = item.author_display || item.author_username || item.author_email || 'user'
          const isMine = !!user?.id && item.author_user_id === user.id
          const itemAttachments = (allAttachments?.items || []).filter(a => a.comment_id === item.id)

          return (
            <div key={item.id} style={{
              display: 'flex', gap: 12, padding: 12,
              border: '1px solid rgba(0,0,0,0.06)', borderRadius: 8,
              background: item.visibility === 'private' ? 'rgba(255,180,0,0.04)' : undefined,
            }}>
              <div style={{
                width: 36, height: 36, flexShrink: 0,
                borderRadius: '50%',
                background: isMine ? '#1677ff' : '#8c8c8c',
                color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontWeight: 600, fontSize: 13,
              }}>{authorInitials(display)}</div>
              <div style={{ flex: 1 }}>
                <Flex justify="space-between" align="center" wrap="wrap" gap={8}>
                  <Space size={6}>
                    <Typography.Text strong>{display}</Typography.Text>
                    {item.author_username && item.author_display && item.author_username !== item.author_display && (
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>@{item.author_username}</Typography.Text>
                    )}
                    <Tag color={item.visibility === 'private' ? 'orange' : 'green'}>{item.visibility}</Tag>
                  </Space>
                  <Space size={6}>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>{fmt(item.created_at)}</Typography.Text>
                    {(isMine || user?.roles.includes('tickora_admin')) && (
                      <Button size="small" type="text" danger onClick={() => remove.mutate(item.id)}>
                        Delete
                      </Button>
                    )}
                  </Space>
                </Flex>
                <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginTop: 6, marginBottom: 0 }}>
                  {item.body}
                </Typography.Paragraph>

                {itemAttachments.length > 0 && (
                  <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {itemAttachments.map(a => (
                      <a key={a.id} href={downloadAttachmentUrl(a.id)} target="_blank" rel="noreferrer" style={{
                        padding: '4px 10px', background: 'rgba(0,0,0,0.03)', borderRadius: 4,
                        fontSize: 12, display: 'flex', alignItems: 'center', gap: 6,
                        border: '1px solid rgba(0,0,0,0.06)'
                      }}>
                        <PaperClipOutlined /> {a.file_name} <Typography.Text type="secondary" style={{ fontSize: 11 }}>({bytes(a.size_bytes)})</Typography.Text>
                      </a>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function AttachmentList({ ticketId }: { ticketId: string }) {
  const { token } = antTheme.useToken()
  const user = useSessionStore(s => s.user)
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['attachments', ticketId],
    queryFn: () => listAttachments(ticketId),
  })

  const remove = useMutation({
    mutationFn: deleteAttachment,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['attachments', ticketId] })
      await queryClient.invalidateQueries({ queryKey: ['comments', ticketId] })
    },
  })

  if (isLoading) return <Typography.Text type="secondary">Loading attachments…</Typography.Text>
  if (!data?.items.length) return <Empty description="No attachments found" image={Empty.PRESENTED_IMAGE_SIMPLE} />

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      {data.items.map((item) => (
        <div 
          key={item.id} 
          style={{ padding: '8px 12px', background: token.colorFillAlter, borderRadius: 8, border: `1px solid ${token.colorBorderSecondary}` }}
        >
          <Flex justify="space-between" align="center" gap={12}>
            <Flex gap={12} align="center" style={{ flex: 1 }}>
              <PaperClipOutlined style={{ fontSize: 18, color: token.colorTextSecondary }} />
              <div>
                <Typography.Text strong style={{ display: 'block' }}>{item.file_name}</Typography.Text>
                <Space split="·" style={{ fontSize: 12 }}>
                  <Typography.Text type="secondary">{bytes(item.size_bytes)}</Typography.Text>
                  <Tag color={item.visibility === 'private' ? 'orange' : 'green'} style={{ fontSize: 10, lineHeight: '14px', margin: 0 }}>{item.visibility}</Tag>
                  <Typography.Text type="secondary">scan: {item.scan_result || 'clean'}</Typography.Text>
                  <Typography.Text type="secondary">{fmt(item.created_at)}</Typography.Text>
                </Space>
              </div>
            </Flex>
            <Space>
              <Button size="small" type="link" href={downloadAttachmentUrl(item.id)} target="_blank">Download</Button>
              {(user?.id === item.uploaded_by_user_id || user?.roles.includes('tickora_admin')) && (
                <Button size="small" type="link" danger onClick={() => remove.mutate(item.id)}>Delete</Button>
              )}
            </Space>
          </Flex>
        </div>
      ))}
    </div>
  )
}

function TicketAudit({ ticketId }: { ticketId: string }) {
  const audit = useQuery({
    queryKey: ['ticketAudit', ticketId],
    queryFn: () => listTicketAudit(ticketId),
  })
  return <AuditTimeline events={audit.data?.items || []} loading={audit.isLoading} />
}

function TicketSidebar({ ticket }: { ticket: TicketDto }) {
  const queryClient = useQueryClient()
  const user = useSessionStore((s) => s.user)
  const [msg, holder] = message.useMessage()

  const meta = useQuery({
    queryKey: ['ticketMetadata', ticket.id],
    queryFn: () => listTicketMetadata(ticket.id),
  })

  const unassignSector = useMutation({
    mutationFn: (sectorCode: string) => removeSector(ticket.id, sectorCode),
    onSuccess: async () => {
      msg.success('Sector removed')
      await queryClient.invalidateQueries({ queryKey: ['ticket', ticket.id] })
      await queryClient.invalidateQueries({ queryKey: ['tickets'] })
    },
    onError: (err) => msg.error(err.message),
  })

  const isAdmin = !!user?.roles.includes('tickora_admin')
  const isDistributor = !!user?.roles.includes('tickora_distributor')
  const sectors = ticketSectorCodes(ticket)
  const items = meta.data?.items || []

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {holder}
      <Card size="small" title="Details">
        <Descriptions size="small" column={1} colon={false}>
          <Descriptions.Item label="Sectors">
            <Space wrap size={[0, 4]}>
              {sectors.map((code) => {
                const isPrimary = code === ticket.current_sector_code
                const canRemove = !isPrimary && (isAdmin || isDistributor || !!user?.sectors?.some(s => s.sectorCode === code && s.role === 'chief'))
                return (
                  <Tag
                    key={code}
                    color={isPrimary ? 'blue' : undefined}
                    closable={canRemove}
                    onClose={() => unassignSector.mutate(code)}
                  >
                    {code} {isPrimary && '(primary)'}
                  </Tag>
                )
              })}
              {sectors.length === 0 && '—'}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="Category">{ticket.category || '—'}</Descriptions.Item>
          <Descriptions.Item label="Type">{ticket.type || '—'}</Descriptions.Item>
          <Descriptions.Item label="Assignees">
            <Space wrap size={[0, 4]}>
              {(ticket.assignee_usernames || []).map((name, idx) => (
                <Tag key={idx} color="cyan">{name}</Tag>
              ))}
              {!ticket.assignee_usernames?.length && 'Unassigned'}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="SLA">
            {ticket.sla_status
              ? <Tag color={ticket.sla_status === 'breached' ? 'red' : ticket.sla_status === 'at_risk' ? 'orange' : 'green'}>{ticket.sla_status}</Tag>
            : '—'}
          </Descriptions.Item>
        </Descriptions>
      </Card>
      <Card size="small" title="Requester">
        <Descriptions size="small" column={1} colon={false}>
          <Descriptions.Item label="Name">
            {[ticket.requester_first_name, ticket.requester_last_name].filter(Boolean).join(' ') || '—'}
          </Descriptions.Item>
          <Descriptions.Item label="Email">{ticket.requester_email || '—'}</Descriptions.Item>
          <Descriptions.Item label="Type"><Tag>{ticket.beneficiary_type}</Tag></Descriptions.Item>
        </Descriptions>
      </Card>
      <Card size="small" title="Timeline">
        <Descriptions size="small" column={1} colon={false}>
          <Descriptions.Item label="Created">{fmt(ticket.created_at)}</Descriptions.Item>
          <Descriptions.Item label="Updated">{fmt(ticket.updated_at)}</Descriptions.Item>
          <Descriptions.Item label="Assigned">{fmt(ticket.assigned_at)}</Descriptions.Item>
          <Descriptions.Item label="First response">{fmt(ticket.first_response_at)}</Descriptions.Item>
          <Descriptions.Item label="Done">{fmt(ticket.done_at)}</Descriptions.Item>
          <Descriptions.Item label="Closed">{fmt(ticket.closed_at)}</Descriptions.Item>
          <Descriptions.Item label="SLA due">{fmt(ticket.sla_due_at)}</Descriptions.Item>
        </Descriptions>
      </Card>
      {items.length > 0 && (
        <Card size="small" title="Metadata">
          <div style={{ display: 'grid', gap: 4 }}>
            {items.map((m) => (
              <Flex key={m.key} justify="space-between" gap={8}>
                <Typography.Text type="secondary">{m.label || m.key}</Typography.Text>
                <Typography.Text strong>{m.value}</Typography.Text>
              </Flex>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}

function TicketDetails({ ticketId }: { ticketId?: string }) {
  const navigate = useNavigate()
  const { token } = antTheme.useToken()
  const { data: ticket, isLoading, error } = useQuery({
    queryKey: ['ticket', ticketId],
    queryFn: () => getTicket(ticketId!),
    enabled: !!ticketId,
  })

  const user = useSessionStore(s => s.user)
  const isClosed = ticket ? ['done', 'closed', 'cancelled'].includes(ticket.status) : false

  if (error) {
    return (
      <div style={{ padding: 24 }}>
        <Alert type="error" message={error.message} showIcon />
      </div>
    )
  }
  if (!ticket && !isLoading) return <div style={{ padding: 80 }}><Empty /></div>
  if (!ticket) return null

  if (isLoading) return <div style={{ padding: 100, textAlign: 'center' }}><Spin size="large" /></div>

  return (
    <div style={{ padding: 24, display: 'grid', gap: 16 }}>
      {/* Top breadcrumb / back */}
      <Flex justify="space-between" align="center" wrap="wrap" gap={8}>
        <Space>
          <Button type="link" onClick={() => navigate('/tickets')} style={{ padding: 0 }}>← Back to Tickets</Button>
        </Space>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Created {fmt(ticket.created_at)} · Updated {fmt(ticket.updated_at)}
        </Typography.Text>
      </Flex>

      {/* Hero card */}
      <div style={{
        border: `1px solid ${token.colorBorderSecondary}`,
        borderRadius: 12,
        padding: 20,
        background: token.colorBgContainer,
        display: 'grid',
        gap: 12,
      }}>
        <Flex justify="space-between" align="start" wrap="wrap" gap={12}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <Space size={8} style={{ marginBottom: 6 }}>
              <Typography.Text type="secondary" style={{ fontFamily: 'monospace' }}>{ticket.ticket_code}</Typography.Text>
              <StatusChanger ticket={ticket} />
              <PriorityTag priority={ticket.priority} />
              {ticket.current_sector_code && <Tag color="cyan">{ticket.current_sector_code}</Tag>}
            </Space>
            <Typography.Title level={3} style={{ margin: 0 }}>
              {ticket.title || 'Untitled ticket'}
            </Typography.Title>
          </div>
        </Flex>
        <WorkflowActions ticket={ticket} />
      </div>

      {/* Two-column body */}
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={16}>
          <div style={{ display: 'grid', gap: 16 }}>
            <Card title="Description" size="small">
              <Typography.Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{ticket.txt}</Typography.Paragraph>
              {ticket.resolution && (
                <Alert style={{ marginTop: 12 }} type="success" showIcon message="Resolution" description={ticket.resolution} />
              )}
            </Card>
            <Card title="Conversation" size="small">
              <CommentBox ticketId={ticket.id} disabled={isClosed} ticket={ticket} />
            </Card>
            <Card title="Attachments" size="small">
              <AttachmentList ticketId={ticket.id} />
            </Card>
            {(() => {
              const isAdmin = user?.roles.includes('tickora_admin')
              const isAuditor = user?.roles.includes('tickora_auditor')
              const isDistributor = user?.roles.includes('tickora_distributor')
              const isStaff = !!user?.sectors?.some(s => s.sectorCode === ticket.current_sector_code)
              if (!(isAdmin || isAuditor || isDistributor || isStaff)) return null
              return (
                <Card title="Activity" size="small">
                  <TicketAudit ticketId={ticket.id} />
                </Card>
              )
            })()}
          </div>
        </Col>
        <Col xs={24} xl={8}>
          <TicketSidebar ticket={ticket} />
        </Col>
      </Row>
    </div>
  )
}

/**
 * Wrapper component for the ticket details view.
 * Extracts the ticket ID from the URL parameters and manages the initial session bootstrap.
 */
export function TicketDetailPage() {
  const params = useParams()
  useSessionBootstrap()
  return <TicketDetails ticketId={params.ticketId} />
}

/**
 * The main ticket listing page featuring a searchable, sortable, and filterable table.
 * Allows users to browse the ticket queue, apply operational filters (status, priority, sector),
 * and navigate to individual ticket details.
 */
export function TicketsPage() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { token } = antTheme.useToken()
  const [msg, holder] = message.useMessage()
  const [status, setStatus] = useState<string | undefined>()
  const [priority, setPriority] = useState<string | undefined>()
  const [sector, setSector] = useState<string | undefined>()
  const [search, setSearch] = useState<string>('')
  const [sortBy, setSortBy] = useState<'created_at' | 'updated_at' | 'ticket_code' | 'priority' | 'status' | 'title'>('created_at')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [modalUsers, setModalUsers] = useState<string[] | null>(null)
  
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20 })

  const me = useSessionBootstrap()
  // The query key fans out across every filter + sort + page combination, so
  // TanStack Query keeps each cache entry independent and the back/forward
  // navigation feels instant. The backend endpoint is RBAC-aware, so we
  // never have to filter visibility client-side.
  const tickets = useQuery({
    queryKey: ['tickets', status, priority, sector, search, sortBy, sortDir, pagination],
    queryFn: () => listTickets({
      status, priority, current_sector_code: sector,
      search: search || undefined,
      sort_by: sortBy, sort_dir: sortDir,
      limit: pagination.pageSize,
      offset: (pagination.current - 1) * pagination.pageSize
    }),
  })
  const options = useQuery({
    queryKey: ['ticketOptions'],
    queryFn: getTicketOptions,
    staleTime: 300_000,
  })

  useEffect(() => {
    if (me.error) message.error(me.error.message)
  }, [me.error])

  // Uncontrolled sortOrder: only set defaultSortOrder on the initial column so
  // AntD manages click-to-toggle internally; onChange syncs to backend params.

  const sectorFilterOptions = useMemo(
    () => (options.data?.sectors || []).map((s) => ({ text: `${s.code} · ${s.name}`, value: s.code })),
    [options.data?.sectors],
  )
  const priorityFilterOptions = useMemo(
    () => (options.data?.priorities || ['low', 'medium', 'high', 'critical']).map((p) => ({ text: p, value: p })),
    [options.data?.priorities],
  )

  const columns: ColumnsType<TicketDto> = useMemo(() => [
    {
      title: 'Code',
      dataIndex: 'ticket_code',
      width: 150,
      render: (value) => <Typography.Text strong>{value}</Typography.Text>,
      sorter: { multiple: 0 },
    },
    {
      title: 'Title',
      dataIndex: 'title',
      width: 320,
      ellipsis: true,
      render: (value, row) => value || row.txt?.slice(0, 90) || '-',
      sorter: { multiple: 0 },
    },
    {
      title: 'Status',
      dataIndex: 'status',
      width: 220,
      render: (_value, record) => <StatusChanger ticket={record} size="small" />,
      sorter: { multiple: 0 },
      filters: STATUS_OPTIONS.map((o) => ({ text: o.label, value: o.value })),
      filteredValue: status ? [status] : null,
      filterMultiple: false,
    },
    {
      title: 'Priority',
      dataIndex: 'priority',
      width: 140,
      render: (value) => <PriorityTag priority={value} />,
      sorter: { multiple: 0 },
      filters: priorityFilterOptions,
      filteredValue: priority ? [priority] : null,
      filterMultiple: false,
    },
    {
      title: 'Sector',
      dataIndex: 'sector_codes',
      width: 160,
      render: (values: string[], row) => {
        const codes = values?.length ? values : (row.current_sector_code ? [row.current_sector_code] : [])
        if (!codes.length) return '-'
        return (
          <Space wrap size={[0, 4]}>
            {codes.map(code => <Tag key={code}>{code}</Tag>)}
          </Space>
        )
      },
      filters: sectorFilterOptions,
      filteredValue: sector ? [sector] : null,
      filterMultiple: false,
      filterSearch: true,
    },
    {
      title: 'Assigned users',
      dataIndex: 'assignee_usernames',
      width: 180,
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
      title: 'Created',
      dataIndex: 'created_at',
      width: 160,
      render: fmt,
      sorter: { multiple: 0 },
      defaultSortOrder: 'descend' as const,
    },
    {
      title: 'Updated',
      dataIndex: 'updated_at',
      width: 160,
      render: fmt,
      sorter: { multiple: 0 },
    },
  ], [status, priority, sector, sectorFilterOptions, priorityFilterOptions])

  return (
    <div style={{ padding: 24, display: 'grid', gap: 16 }}>
      {holder}
      <Flex justify="space-between" align="center" wrap="wrap" gap={12}>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>Tickets</Typography.Title>
          <Typography.Text type="secondary">Operational queue with workflow actions</Typography.Text>
        </div>
        <Space wrap>
          <Statistic value={tickets.data?.total || 0} suffix="tickets" styles={{ content: { fontSize: 18 } }} style={{ marginRight: 16 }} />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/create')} data-tour-id="tickets-create">
            Create Ticket
          </Button>
          <span data-tour-id="tickets-search">
            <Input.Search allowClear placeholder="Search title, body or code"
                    value={search} onChange={(e) => setSearch(e.target.value)}
                    onSearch={setSearch} style={{ width: 280 }} />
          </span>
          {(status || priority || sector) && (
            <Button data-tour-id="tickets-filters" onClick={() => { setStatus(undefined); setPriority(undefined); setSector(undefined) }}>
              Clear filters
            </Button>
          )}
          <Button icon={<ReloadOutlined />} onClick={() => tickets.refetch()} />
          <TourInfoButton pageKey="tickets" />
        </Space>
      </Flex>

      {tickets.error && <Alert type="error" message={tickets.error.message} showIcon />}

      <div style={{ border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8, overflow: 'hidden' }}>
        <Table
          rowKey="id"
          loading={tickets.isLoading}
          columns={columns}
          dataSource={tickets.data?.items || []}
          pagination={{ 
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: tickets.data?.total || 0,
            showSizeChanger: true, 
            showTotal: (n) => `Total ${n} tickets` 
          }}
          onChange={(p, filters, sorter: SorterResult<TicketDto> | SorterResult<TicketDto>[]) => {
            setPagination({ current: p.current || 1, pageSize: p.pageSize || 20 })
            const s = Array.isArray(sorter) ? sorter[0] : sorter
            const field = (s?.field as any)
            if (s?.order && field && ['created_at', 'updated_at', 'ticket_code', 'priority', 'status', 'title'].includes(field)) {
              setSortBy(field)
              setSortDir(s.order === 'ascend' ? 'asc' : 'desc')
            } else if (!s?.order) {
              setSortBy('created_at')
              setSortDir('desc')
            }
            const pickFirst = (key: string) => {
              const v = filters?.[key]
              return Array.isArray(v) && v.length ? String(v[0]) : undefined
            }
            setStatus(pickFirst('status'))
            setPriority(pickFirst('priority'))
            setSector(pickFirst('current_sector_code'))
          }}
          onRow={(record) => ({ onClick: () => navigate(`/tickets/${record.id}`) })}
          locale={{ emptyText: <Empty description="No tickets match the current filters" /> }}
          rowClassName={() => 'tickora-row-clickable'}
          scroll={{ x: 860 }}
        />
      </div>

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
      <ProductTour
        pageKey="tickets"
        steps={[
          {
            target: '[data-tour-id="tickets-search"]',
            content: t('tour.tickets.search'),
            disableBeacon: true,
          },
          {
            target: '[data-tour-id="tickets-create"]',
            content: t('tour.tickets.create'),
          },
        ]}
      />
    </div>
  )
}
