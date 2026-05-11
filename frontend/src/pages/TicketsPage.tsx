import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ProductTour, TourInfoButton } from '@/components/common/ProductTour'
import { WatchButton } from '@/components/common/WatchButton'
import { TicketLinksPanel } from '@/components/common/TicketLinksPanel'
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
  listTickets, markDone, registerAttachment, reopenTicket, requestAttachmentUpload,
  deleteTicket, listTicketMetadata, removeAssignee, removeSector,
  type AttachmentDto,
  type TicketDto,
} from '@/api/tickets'
import { useSessionStore } from '@/stores/sessionStore'
import { StatusTag, STATUS_OPTIONS } from '@/components/common/StatusTag'
import { PriorityTag } from '@/components/common/PriorityTag'
import { BeneficiaryTypeTag, BENEFICIARY_TYPE_OPTIONS } from '@/components/common/BeneficiaryTypeTag'
import {
  listEndorsementsForTicket, requestEndorsement, decideEndorsement,
} from '@/api/endorsements'
import { StatusChanger } from '@/components/common/StatusChanger'
import { fmtDateTime, fmtBytes } from '@/components/common/format'

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
        firstName: query.data.first_name ?? undefined,
        lastName: query.data.last_name ?? undefined,
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
  const isAssignee = !!user.id && ticketAssigneeIds(ticket).includes(user.id)
  return isAssignee && ['in_progress', 'reopened'].includes(ticket.status)
}

function canClose(ticket: TicketDto, user: ReturnType<typeof useSessionStore.getState>['user']) {
  if (!user) return false
  const isRequesterEmail = ticket.beneficiary_type === 'external' && !!user.email && ticket.requester_email === user.email
  const isRequester = ticket.created_by_user_id === user.id || (!!user.id && ticket.beneficiary_user_id === user.id) || isRequesterEmail
  return ticket.status === 'done' && isRequester
}

function canReopen(ticket: TicketDto, user: ReturnType<typeof useSessionStore.getState>['user']) {
  if (!user) return false
  const isRequesterEmail = ticket.beneficiary_type === 'external' && !!user.email && ticket.requester_email === user.email
  const isRequester = ticket.created_by_user_id === user.id || (!!user.id && ticket.beneficiary_user_id === user.id) || isRequesterEmail
  return ['done', 'closed'].includes(ticket.status) && isRequester
}

function canCancel(ticket: TicketDto, user: ReturnType<typeof useSessionStore.getState>['user']) {
  if (!user) return false
  const isAssignee = !!user.id && ticketAssigneeIds(ticket).includes(user.id)
  return isAssignee && ['pending', 'assigned_to_sector'].includes(ticket.status)
}

function WorkflowActions({ ticket }: { ticket: TicketDto }) {
  const [form] = Form.useForm()
  const [modal, setModal] = useState<string | null>(null)
  const [msg, holder] = message.useMessage()
  const [modalApi, modalHolder] = Modal.useModal()
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
    form.resetFields()
    setModal(null)
    await queryClient.invalidateQueries({ queryKey: ['tickets'] })
    await queryClient.invalidateQueries({ queryKey: ['ticket', ticket.id] })
    await queryClient.invalidateQueries({ queryKey: ['comments', ticket.id] })
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
      {modalHolder}
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
             modalApi.confirm({
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

/**
 * Endorsement panel on the ticket detail page.
 *
 * - The active assignee sees a "Request endorsement…" button.
 *   The modal lets them target a specific avizator or the pool, with a
 *   short rationale.
 * - Any visible endorsement is listed with its status. Avizators see
 *   inline Approve / Reject actions on the pending ones they can act on.
 * - While at least one endorsement is `pending`, an info banner spells
 *   out that `mark_done` / `close` are blocked.
 */
function EndorsementsCard({ ticket }: { ticket: TicketDto }) {
  const queryClient = useQueryClient()
  const user = useSessionStore((s) => s.user)
  const [msg, holder] = message.useMessage()
  const [requestOpen, setRequestOpen] = useState(false)
  const [decideTarget, setDecideTarget] = useState<{ id: string; decision: 'approved' | 'rejected' } | null>(null)
  const [reqForm] = Form.useForm<{ reason?: string; assigned_to_user_id?: string }>()
  const [decideForm] = Form.useForm<{ reason?: string }>()

  const isAdmin = !!user?.roles.includes('tickora_admin')
  const isAvizator = !!user?.roles.includes('tickora_avizator')
  const assigneeIds = ticketAssigneeIds(ticket)
  const isAssignee = !!user?.id && assigneeIds.includes(user.id)
  const canRequest = isAssignee

  const endorsements = useQuery({
    queryKey: ['endorsements', ticket.id],
    queryFn: () => listEndorsementsForTicket(ticket.id),
    staleTime: 30_000,
  })
  const items = endorsements.data?.items || []
  const hasPending = items.some((i) => i.status === 'pending')

  // Avizator pickers can pin the request to a specific user. The list is
  // derived from the existing assignable-users surface, filtered to
  // those carrying the `tickora_avizator` role server-side… we don't
  // have a dedicated endpoint yet, so we just let the requester type a
  // username/email or leave it blank for the pool.
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['endorsements', ticket.id] })
    await queryClient.invalidateQueries({ queryKey: ['ticket', ticket.id] })
    await queryClient.invalidateQueries({ queryKey: ['comments', ticket.id] })
  }

  const requestM = useMutation({
    mutationFn: (vars: { reason?: string; assigned_to_user_id?: string | null }) =>
      requestEndorsement(ticket.id, vars),
    onSuccess: async () => {
      msg.success('Endorsement requested')
      setRequestOpen(false)
      reqForm.resetFields()
      await refresh()
    },
    onError: (err) => msg.error(err.message),
  })

  const decideM = useMutation({
    mutationFn: (vars: { id: string; decision: 'approved' | 'rejected'; reason?: string }) =>
      decideEndorsement(vars.id, { decision: vars.decision, reason: vars.reason }),
    onSuccess: async (_data, vars) => {
      msg.success(`Endorsement ${vars.decision}`)
      setDecideTarget(null)
      decideForm.resetFields()
      await refresh()
    },
    onError: (err) => msg.error(err.message),
  })

  if (!canRequest && items.length === 0 && !isAvizator) {
    // Nothing to show — not a participant, no endorsements posted yet.
    return null
  }

  return (
    <Card
      title="Supplementary endorsement"
      size="small"
      extra={canRequest ? (
        <Button size="small" type="primary" onClick={() => setRequestOpen(true)}>
          Request endorsement…
        </Button>
      ) : null}
    >
      {holder}
      {hasPending && (
        <Alert
          showIcon
          type="warning"
          style={{ marginBottom: 12 }}
          message="Pending endorsement"
          description="Mark-done and close are blocked until every endorsement is decided."
        />
      )}
      {items.length === 0 && (
        <Empty description="No endorsements requested yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}
      <div style={{ display: 'grid', gap: 8 }}>
        {items.map((it) => {
          const statusColor =
            it.status === 'approved' ? 'green' :
            it.status === 'rejected' ? 'red'   : 'gold'
          const canIDecide = it.status === 'pending' && (
            isAdmin || (isAvizator && (!it.assigned_to_user_id || it.assigned_to_user_id === user?.id))
          )
          return (
            <div key={it.id} style={{
              padding: 10, border: '1px solid rgba(0,0,0,0.06)', borderRadius: 6,
              background: it.status === 'pending' ? 'rgba(250,173,20,0.04)' : undefined,
            }}>
              <Flex justify="space-between" align="center" wrap="wrap" gap={8}>
                <Space size={6}>
                  <Tag color={statusColor}>{it.status}</Tag>
                  <Tag color={it.assigned_to_user_id ? 'blue' : 'purple'}>
                    {it.assigned_to_user_id ? 'direct' : 'pool'}
                  </Tag>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    requested {fmt(it.created_at)}
                  </Typography.Text>
                  {it.decided_at && (
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      · decided {fmt(it.decided_at)}
                    </Typography.Text>
                  )}
                </Space>
                {canIDecide && (
                  <Space size={4}>
                    <Button size="small" type="primary"
                            onClick={() => setDecideTarget({ id: it.id, decision: 'approved' })}>
                      Approve
                    </Button>
                    <Button size="small" danger
                            onClick={() => setDecideTarget({ id: it.id, decision: 'rejected' })}>
                      Reject
                    </Button>
                  </Space>
                )}
              </Flex>
              {it.request_reason && (
                <Typography.Paragraph style={{ marginTop: 6, marginBottom: 0, whiteSpace: 'pre-wrap' }}>
                  <Typography.Text type="secondary">Reason: </Typography.Text>{it.request_reason}
                </Typography.Paragraph>
              )}
              {it.decision_reason && (
                <Typography.Paragraph style={{ marginTop: 4, marginBottom: 0, whiteSpace: 'pre-wrap' }}>
                  <Typography.Text type="secondary">Decision note: </Typography.Text>{it.decision_reason}
                </Typography.Paragraph>
              )}
            </div>
          )
        })}
      </div>

      {/* Request modal */}
      <Modal
        title="Request supplementary endorsement"
        open={requestOpen}
        okText="Request"
        confirmLoading={requestM.isPending}
        onCancel={() => { setRequestOpen(false); reqForm.resetFields() }}
        onOk={async () => {
          const values = await reqForm.validateFields()
          requestM.mutate({
            reason: values.reason?.trim() || undefined,
            assigned_to_user_id: values.assigned_to_user_id?.trim() || null,
          })
        }}
        destroyOnHidden
      >
        <Form form={reqForm} layout="vertical">
          <Alert
            type="info" showIcon style={{ marginBottom: 12 }}
            message="The ticket stays workable — this is non-blocking."
            description="However, mark-done and close are blocked until every endorsement is decided (approved OR rejected)."
          />
          <Form.Item
            name="reason"
            label="What needs a second opinion?"
            rules={[{ required: true, min: 3 }]}
          >
            <Input.TextArea rows={3} placeholder="Briefly describe what you want the avizator to look at." />
          </Form.Item>
          <Form.Item
            name="assigned_to_user_id"
            label="Target avizator (optional)"
            extra="Leave empty to fan the request out to the whole avizator pool. To target a specific person, paste their user id."
          >
            <Input placeholder="Pool (any avizator)" />
          </Form.Item>
        </Form>
      </Modal>

      {/* Decide modal */}
      <Modal
        title={decideTarget?.decision === 'approved' ? 'Approve endorsement' : 'Reject endorsement'}
        open={!!decideTarget}
        okText={decideTarget?.decision === 'approved' ? 'Approve' : 'Reject'}
        okButtonProps={{ danger: decideTarget?.decision === 'rejected', type: 'primary' }}
        confirmLoading={decideM.isPending}
        onCancel={() => { setDecideTarget(null); decideForm.resetFields() }}
        onOk={async () => {
          const values = await decideForm.validateFields()
          decideM.mutate({
            id: decideTarget!.id,
            decision: decideTarget!.decision,
            reason: values.reason?.trim() || undefined,
          })
        }}
        destroyOnHidden
      >
        <Form form={decideForm} layout="vertical">
          <Form.Item name="reason" label="Decision note (optional)"
                     extra="Recorded on the endorsement decision.">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}

function authorInitials(name: string): string {
  return name.split(/[\s.@]+/).filter(Boolean).slice(0, 2).map(s => s[0]?.toUpperCase()).join('') || '?'
}

/**
 * Banner shown to the beneficiary (or admin) after the operator marked
 * the ticket as `done`. Forces a clear decision: confirm closure or
 * reopen with a reason that becomes a public comment on the timeline.
 */
function ClosureApprovalBanner({ ticket }: { ticket: TicketDto }) {
  const user = useSessionStore((s) => s.user)
  const queryClient = useQueryClient()
  const [msg, holder] = message.useMessage()
  const [reopenOpen, setReopenOpen] = useState(false)
  const [form] = Form.useForm<{ reason: string }>()

  const showClose = canClose(ticket, user)
  const showReopen = canReopen(ticket, user)
  const visible = ticket.status === 'done' && (showClose || showReopen)

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['ticket', ticket.id] })
    await queryClient.invalidateQueries({ queryKey: ['tickets'] })
    await queryClient.invalidateQueries({ queryKey: ['comments', ticket.id] })
  }

  const approve = useMutation({
    mutationFn: () => closeTicket(ticket.id),
    onSuccess: async () => { msg.success('Ticket closed'); await refresh() },
    onError: (err) => msg.error(err.message),
  })
  const reopenIt = useMutation({
    mutationFn: (reason: string) => reopenTicket(ticket.id, reason),
    onSuccess: async () => {
      msg.success('Ticket reopened')
      setReopenOpen(false)
      form.resetFields()
      await refresh()
    },
    onError: (err) => msg.error(err.message),
  })

  if (!visible) return null

  return (
    <>
      {holder}
      <Alert
        type="success"
        showIcon
        message="The operator marked this ticket as done."
        description="Please approve the closure or reopen the ticket with a reason."
        action={
          <Space>
            {showReopen && (
              <Button danger onClick={() => setReopenOpen(true)}>Reopen…</Button>
            )}
            {showClose && (
              <Button type="primary" loading={approve.isPending}
                      onClick={() => approve.mutate()}>
                Approve closure
              </Button>
            )}
          </Space>
        }
      />
      <Modal
        title="Reopen ticket"
        open={reopenOpen}
        okText="Reopen"
        okButtonProps={{ danger: true }}
        confirmLoading={reopenIt.isPending}
        onCancel={() => { setReopenOpen(false); form.resetFields() }}
        onOk={async () => {
          const values = await form.validateFields()
          reopenIt.mutate(values.reason.trim())
        }}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="reason"
            label="Reason"
            rules={[{ required: true, min: 3, message: 'A reason of at least 3 characters is required.' }]}
            extra="Your reason will appear as a public comment on the ticket so the operator knows what to revisit."
          >
            <Input.TextArea rows={4} placeholder="What still needs to be fixed?" autoFocus />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}

interface SystemCommentPayload {
  kind: string
  actor_user_id?: string
  actor_username?: string
  old_status?: string
  new_status?: string
  reason?: string
  [k: string]: unknown
}

function parseSystemComment(body: string): SystemCommentPayload | null {
  try {
    const parsed = JSON.parse(body)
    if (parsed && typeof parsed === 'object' && typeof parsed.kind === 'string') {
      return parsed as SystemCommentPayload
    }
  } catch {
    // Older system rows or hand-written ones may not be JSON — fall back to raw body.
  }
  return null
}

function shouldHideSystemComment(body: string): boolean {
  const payload = parseSystemComment(body)
  return !!payload?.kind?.startsWith('endorsement_')
}

function SystemCommentRow({ body, createdAt }: { body: string; createdAt: string }) {
  const { t } = useTranslation()
  const payload = parseSystemComment(body)

  // Render the structured payload through i18n so EN/RO read naturally;
  // fall back to the raw body for anything we don't recognise.
  let rendered: React.ReactNode = body
  if (payload?.kind === 'status_changed') {
    rendered = t('tickets.comments.system.status_changed', {
      actor: payload.actor_username || t('tickets.comments.system.unknown_actor'),
      old: t(`status.${payload.old_status}`, { defaultValue: payload.old_status || '' }),
      new: t(`status.${payload.new_status}`, { defaultValue: payload.new_status || '' }),
    })
  }

  return (
    <div style={{
      display: 'flex', gap: 10, padding: '6px 12px', alignItems: 'center',
      borderLeft: '2px solid rgba(0,0,0,0.12)', background: 'rgba(0,0,0,0.02)', borderRadius: 4,
    }}>
      <Typography.Text type="secondary" italic style={{ flex: 1, fontSize: 12 }}>
        {rendered}
        {payload?.reason && (
          <>
            {' '}
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              — {payload.reason}
            </Typography.Text>
          </>
        )}
      </Typography.Text>
      <Typography.Text type="secondary" style={{ fontSize: 11 }}>{fmt(createdAt)}</Typography.Text>
    </div>
  )
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

  // Mirror the backend rules in `src/iam/rbac.py`:
  //   can_post_public_comment  = active assignee || requester-side
  //   can_post_private_comment = active assignee
  // Admins/chiefs/distributors who want to comment must first be assigned
  // to the ticket, same as any other operator.
  // `isAssignee` covers both the legacy `assignee_user_id` field and the
  // multi-assignee list so a secondary assignee can also comment.
  const isAssignee = !!user?.id && (
    ticket?.assignee_user_id === user.id
    || (ticket?.assignee_user_ids || []).includes(user.id)
  )
  const isRequester = !!ticket && (
    (ticket.beneficiary_type === 'external' && !!user?.email && ticket.requester_email === user?.email)
    || ticket.created_by_user_id === user?.id
    || (!!user?.id && ticket.beneficiary_user_id === user.id)
  )

  const canPostPublic   = isAssignee || isRequester
  const canPostPrivate  = isAssignee
  const canPostAtAll    = canPostPublic || canPostPrivate
  // When *only* private posting is available (a distributor leaving a
  // triage note before the ticket is picked up), pin the form to
  // private so they can't accidentally submit a public comment that the
  // backend will reject.
  const forcePrivate    = canPostPrivate && !canPostPublic

  const comments = useQuery({
    queryKey: ['comments', ticketId],
    queryFn: () => listComments(ticketId),
  })

  const add = useMutation({
    /**
     * Comment + attachments flow:
     *   1. Persist the comment first so we have a `comment_id` to attach to.
     *   2. For each queued file, request a presigned URL, PUT to MinIO,
     *      then call `register` to store the metadata row.
     *   3. Per-file failures bubble up — partial success is reported so
     *      the user sees which file didn't make it.
     *
     * Visibility is the comment's visibility (public/private). Private
     * uploads inherit the comment's RBAC: only staff that can read
     * private comments can download them. Backend re-checks every time.
     */
    mutationFn: async (values: { body: string; is_public?: boolean }) => {
      // Three cases:
      //   forcePrivate  -> reserved for any future private-only actor.
      //   public-only   -> a beneficiary; pin public.
      //   both allowed  -> assigned operator; honour the visibility checkbox.
      let visibility: 'public' | 'private'
      if (forcePrivate)            visibility = 'private'
      else if (!canPostPrivate)    visibility = 'public'
      else                         visibility = values.is_public === false ? 'private' : 'public'
      const comment = await createComment(ticketId, values.body, visibility)

      const failures: string[] = []
      for (const fileItem of fileList) {
        if (!fileItem.originFileObj) continue
        const file = fileItem.originFileObj as File
        try {
          const req = await requestAttachmentUpload(ticketId, file)
          const putRes = await fetch(req.upload_url, {
            method: 'PUT',
            headers: { 'Content-Type': file.type || 'application/octet-stream' },
            body: file,
          })
          if (!putRes.ok) throw new Error(`MinIO PUT failed: ${putRes.status}`)
          await registerAttachment(ticketId, file, req.storage_key, comment.id)
        } catch (e) {
          failures.push(`${file.name}: ${(e as Error).message}`)
        }
      }
      if (failures.length) {
        // Surface partial-failure detail; the comment itself succeeded.
        throw new Error(`Comment posted but ${failures.length} attachment(s) failed:\n${failures.join('\n')}`)
      }
      return comment
    },
    onSuccess: async () => {
      form.resetFields()
      setFileList([])
      await queryClient.invalidateQueries({ queryKey: ['comments', ticketId] })
      await queryClient.invalidateQueries({ queryKey: ['attachments', ticketId] })
      msg.success('Comment posted')
    },
    onError: async (err) => {
      // Even on partial failure the comment exists, so we still refresh
      // the visible threads — the message tells the user what's missing.
      msg.error({ content: err.message, duration: 6 })
      await queryClient.invalidateQueries({ queryKey: ['comments', ticketId] })
      await queryClient.invalidateQueries({ queryKey: ['attachments', ticketId] })
    },
  })

  const remove = useMutation({
    mutationFn: deleteComment,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['comments', ticketId] })
      await queryClient.invalidateQueries({ queryKey: ['attachments', ticketId] })
    },
    onError: (err) => msg.error(err.message),
  })

  // Self-assign shortcut for sector bystanders. Lives at the component
  // root so the hooks order stays stable even when the read-only banner
  // unmounts/remounts.
  const claim = useMutation({
    mutationFn: () => assignToMe(ticketId),
    onSuccess: async () => {
      msg.success('Assigned to you')
      await queryClient.invalidateQueries({ queryKey: ['ticket', ticketId] })
      await queryClient.invalidateQueries({ queryKey: ['comments', ticketId] })
    },
    onError: (err) => msg.error(err.message),
  })

  const { data: allAttachments } = useQuery({
    queryKey: ['attachments', ticketId],
    queryFn: () => listAttachments(ticketId),
  })

  const visibleComments = (comments.data?.items || []).filter((item) => (
    item.comment_type !== 'system' || !shouldHideSystemComment(item.body)
  ))

  // Upload props are shared between the Dragger (drag-and-drop area) and
  // the inline button. `beforeUpload: false` short-circuits AntD's auto-
  // upload so the file just lands in `fileList`; the actual transfer
  // happens inside the comment-create mutation (so MinIO + register run
  // after the comment exists and we have its id).
  const uploadProps: UploadProps = {
    onRemove: (file) => {
      const index = fileList.indexOf(file)
      const newFileList = fileList.slice()
      newFileList.splice(index, 1)
      setFileList(newFileList)
    },
    beforeUpload: (file) => {
      // Cap per-file size client-side to mirror the backend
      // (`Config.ATTACHMENT_MAX_SIZE_BYTES`, default 25 MiB). We can't
      // read the env from the SPA, so the limit is duplicated here as a
      // safety net — the backend remains the source of truth.
      const MAX = 25 * 1024 * 1024
      if (file.size > MAX) {
        msg.error(`${file.name} is larger than 25 MB`)
        return Upload.LIST_IGNORE
      }
      setFileList((prev) => [...prev, file])
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
              <Upload.Dragger {...uploadProps} style={{ padding: '12px 16px' }}>
                <p style={{ margin: 0, color: 'rgba(0,0,0,0.65)' }}>
                  <PaperClipOutlined style={{ fontSize: 18, marginRight: 6 }} />
                  Drag files here or click to attach
                </p>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Up to 25 MB per file. Files inherit the comment's
                  visibility — private comments → private files.
                </Typography.Text>
              </Upload.Dragger>
            </div>

            <Flex justify="space-between" align="center">
              {forcePrivate ? (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  <Tag color="orange">private</Tag>
                  Triage note — only staff can see this.
                </Typography.Text>
              ) : canPostPrivate ? (
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
        <Alert
          type="info"
          showIcon
          message="You can read this conversation."
          description={
            !!ticket && canAssignToMe(ticket, user)
              ? 'Assign the ticket to yourself to comment or move it forward.'
              : 'Only the active assignee, the requester, or an admin can post.'
          }
          action={!!ticket && canAssignToMe(ticket, user) ? (
            <Button size="small" type="primary" loading={claim.isPending} onClick={() => claim.mutate()}>
              Assign to me
            </Button>
          ) : undefined}
        />
      )}
      {visibleComments.length === 0 && !comments.isLoading && (
        <Empty description="No comments yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}
      <div style={{ display: 'grid', gap: 8 }}>
        {visibleComments.map((item) => {
          if (item.comment_type === 'system') {
            return <SystemCommentRow key={item.id} body={item.body} createdAt={item.created_at} />
          }

          const display = item.author_display || item.author_username || item.author_email || 'user'
          const isMine = !!user?.id && item.author_user_id === user.id
          const itemAttachments = (allAttachments?.items || []).filter(a => a.comment_id === item.id)
          const isReopenReason = item.comment_type === 'reopen_reason'

          return (
            <div key={item.id} style={{
              display: 'flex', gap: 12, padding: 12,
              border: '1px solid rgba(0,0,0,0.06)', borderRadius: 8,
              background: isReopenReason
                ? 'rgba(255,77,79,0.05)'
                : item.visibility === 'private' ? 'rgba(255,180,0,0.04)' : undefined,
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
                    {isReopenReason
                      ? <Tag color="red">reopen reason</Tag>
                      : <Tag color={item.visibility === 'private' ? 'orange' : 'green'}>{item.visibility}</Tag>}
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
          <Descriptions.Item label="Category">{ticket.category_name || '—'}</Descriptions.Item>
          <Descriptions.Item label="Subcategory">{ticket.subcategory_name || '—'}</Descriptions.Item>
          <Descriptions.Item label="Assignees">
            <Space wrap size={[0, 4]}>
              {(ticket.assignee_usernames || []).map((name, idx) => (
                <Tag key={idx} color="cyan">{name}</Tag>
              ))}
              {!ticket.assignee_usernames?.length && 'Unassigned'}
            </Space>
          </Descriptions.Item>
        </Descriptions>
      </Card>
      <Card size="small" title="Requester">
        <Descriptions size="small" column={1} colon={false}>
          <Descriptions.Item label="Name">
            {[ticket.requester_first_name, ticket.requester_last_name].filter(Boolean).join(' ') || '—'}
          </Descriptions.Item>
          <Descriptions.Item label="Email">{ticket.requester_email || '—'}</Descriptions.Item>
          <Descriptions.Item label="Type"><BeneficiaryTypeTag type={ticket.beneficiary_type} /></Descriptions.Item>
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
        </Descriptions>
      </Card>
      <TicketLinksPanel ticketId={ticket.id} />
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
      {/* Top breadcrumb / back + watch toggle */}
      <Flex justify="space-between" align="center" wrap="wrap" gap={8}>
        <Space>
          <Button type="link" onClick={() => navigate('/tickets')} style={{ padding: 0 }}>← Back to Tickets</Button>
        </Space>
        <Space>
          <WatchButton ticketId={ticket.id} />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Created {fmt(ticket.created_at)} · Updated {fmt(ticket.updated_at)}
          </Typography.Text>
        </Space>
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

      <ClosureApprovalBanner ticket={ticket} />

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
            <EndorsementsCard ticket={ticket} />

            <Card title="Attachments" size="small">
              <AttachmentList ticketId={ticket.id} />
            </Card>
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
  const [beneficiaryType, setBeneficiaryType] = useState<'internal' | 'external' | undefined>()
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
    queryKey: ['tickets', status, priority, sector, beneficiaryType, search, sortBy, sortDir, pagination],
    queryFn: () => listTickets({
      status, priority, current_sector_code: sector,
      beneficiary_type: beneficiaryType,
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
      title: t('beneficiary_type.label'),
      dataIndex: 'beneficiary_type',
      width: 130,
      render: (value: string) => <BeneficiaryTypeTag type={value} />,
      filters: BENEFICIARY_TYPE_OPTIONS.map(o => ({ text: t(`beneficiary_type.${o.value}`), value: o.value })),
      filteredValue: beneficiaryType ? [beneficiaryType] : null,
      filterMultiple: false,
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
  ], [status, priority, sector, beneficiaryType, sectorFilterOptions, priorityFilterOptions, t])

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
          {(status || priority || sector || beneficiaryType) && (
            <Button data-tour-id="tickets-filters" onClick={() => { setStatus(undefined); setPriority(undefined); setSector(undefined); setBeneficiaryType(undefined) }}>
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
            const bt = pickFirst('beneficiary_type')
            setBeneficiaryType(bt === 'internal' || bt === 'external' ? bt : undefined)
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
          },
          {
            target: '[data-tour-id="tickets-filters"]',
            content: t('tour.tickets.filters'),
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
