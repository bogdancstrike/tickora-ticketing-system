import { useMemo, useState } from 'react'
import { Dropdown, Modal, Form, Input, Button, Select, Space, message } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { DownOutlined, SwapOutlined } from '@ant-design/icons'
import { assignSector, changeTicketStatus, getTicketOptions, type TicketDto } from '@/api/tickets'
import { useSessionStore } from '@/stores/sessionStore'
import { StatusTag } from './StatusTag'

interface Transition { to: string; label: string }

// These mirror the backend state_machine.TRANSITIONS exactly. Stay in lockstep
// with src/ticketing/state_machine.py — adding an option here without an
// allowed transition there results in a runtime error.
const STAFF_TRANSITIONS: Record<string, Transition[]> = {
  pending: [
    { to: 'in_progress',        label: 'Take ownership' },
    { to: 'assigned_to_sector', label: 'Route to sector' },
    { to: 'cancelled',          label: 'Cancel' },
  ],
  assigned_to_sector: [
    { to: 'in_progress', label: 'Take ownership' },
    { to: 'cancelled',   label: 'Cancel' },
  ],
  in_progress: [
    { to: 'done',               label: 'Mark done' },
    { to: 'assigned_to_sector', label: 'Unassign · back to sector' },
  ],
  reopened: [
    { to: 'in_progress', label: 'Take ownership' },
    { to: 'done',        label: 'Mark done' },
  ],
  done: [
    { to: 'closed',   label: 'Close ticket' },
    { to: 'reopened', label: 'Reopen' },
  ],
  closed: [
    { to: 'reopened', label: 'Reopen' },
  ],
}

// Beneficiaries (the requester / external user) only acknowledge or reopen.
const REQUESTER_TRANSITIONS: Record<string, Transition[]> = {
  done:   [{ to: 'closed', label: 'Acknowledge & close' }, { to: 'reopened', label: 'Reopen' }],
  closed: [{ to: 'reopened', label: 'Reopen' }],
}

const REQUIRES_REASON = new Set(['cancelled', 'reopened'])
// Optional but prompted: ask the operator to leave a closing note even though
// the backend is happy with empty.
const OPTIONAL_REASON = new Set(['done', 'closed', 'assigned_to_sector'])

const REASON_LABELS: Record<string, { label: string; placeholder?: string }> = {
  done:               { label: 'Resolution (optional)',         placeholder: 'How was this ticket resolved?' },
  closed:             { label: 'Closing note (optional)',       placeholder: 'Anything to add before closing?' },
  cancelled:          { label: 'Cancellation reason',           placeholder: 'Why is this ticket being cancelled?' },
  reopened:           { label: 'Reopen reason',                 placeholder: 'Why is this ticket being reopened?' },
  assigned_to_sector: { label: 'Reason (optional)',             placeholder: 'Why are you releasing this ticket?' },
}

export function StatusChanger({
  ticket,
  size = 'middle',
  mode = 'tag',
}: {
  ticket: TicketDto
  size?: 'small' | 'middle'
  /** 'tag' shows the StatusTag with a chevron; 'button' shows a labeled "Status" Button. */
  mode?: 'tag' | 'button'
}) {
  const [pending, setPending] = useState<string | null>(null)
  const [step, setStep] = useState<1 | 2>(1)
  const [form] = Form.useForm<{ reason?: string; sector_code?: string }>()
  const [msg, holder] = message.useMessage()
  const queryClient = useQueryClient()
  const user = useSessionStore((s) => s.user)
  const options = useQuery({
    queryKey: ['ticketOptions'],
    queryFn: getTicketOptions,
    staleTime: 300_000,
  })

  const transitions = useMemo<Transition[]>(() => {
    if (!user) return []
    const isAdmin = user.roles.includes('tickora_admin')
    const isDistributor = user.roles.includes('tickora_distributor')
    const sectorCode = ticket.current_sector_code
    const isChiefHere = !!sectorCode && !!user.sectors?.some((s) => s.sectorCode === sectorCode && s.role === 'chief')
    const isAssignee = ticket.assignee_user_id === user.id
    const isRequester = (
      ticket.created_by_user_id === user.id
      || (!!user.id && ticket.beneficiary_user_id === user.id)
      || (ticket.beneficiary_type === 'external' && !!user.email && ticket.requester_email === user.email)
    )

    // Operators must be assigned (or chief / admin) to drive the workflow.
    const canDriveAsStaff = isAdmin || isChiefHere || isAssignee
    if (canDriveAsStaff) return STAFF_TRANSITIONS[ticket.status] || []

    // Distributors triage but only at pending/assigned_to_sector — they can cancel.
    if (isDistributor && ['pending', 'assigned_to_sector'].includes(ticket.status)) {
      return [{ to: 'cancelled', label: 'Cancel' }]
    }

    // Requester / beneficiary path
    if (isRequester) return REQUESTER_TRANSITIONS[ticket.status] || []

    return []
  }, [ticket, user])

  const change = useMutation({
    mutationFn: ({ status, reason, sectorCode }: { status: string; reason?: string; sectorCode?: string }) =>
      status === 'assigned_to_sector' && sectorCode
        ? assignSector(ticket.id, sectorCode, reason)
        : changeTicketStatus(ticket.id, status, reason),
    onSuccess: async () => {
      msg.success('Status changed')
      setPending(null)
      setStep(1)
      form.resetFields()
      await queryClient.invalidateQueries({ queryKey: ['tickets'] })
      await queryClient.invalidateQueries({ queryKey: ['ticket', ticket.id] })
      await queryClient.invalidateQueries({ queryKey: ['ticketAudit', ticket.id] })
      await queryClient.invalidateQueries({ queryKey: ['monitorOverview'] })
      await queryClient.invalidateQueries({ queryKey: ['monitorSector'] })
      await queryClient.invalidateQueries({ queryKey: ['monitorUser'] })
    },
    onError: (err) => msg.error(err.message),
  })

  if (transitions.length === 0) {
    if (mode === 'button') return null
    return (
      <span onClick={(e) => e.stopPropagation()}>
        <StatusTag status={ticket.status} />
      </span>
    )
  }

  const trigger = mode === 'button' ? (
    <Button icon={<SwapOutlined />} size={size}>
      Status <DownOutlined />
    </Button>
  ) : (
    <span style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <StatusTag status={ticket.status} />
      <DownOutlined style={{ fontSize: 10, opacity: 0.6 }} />
    </span>
  )

  return (
    <span onClick={(e) => e.stopPropagation()}>
      {holder}
      <Dropdown
        trigger={['click']}
        menu={{
          items: transitions.map((t) => ({
            key: t.to,
            label: (
              <Space size={6}>
                <StatusTag status={t.to} />
                <span style={{ fontSize: 12, opacity: 0.8 }}>{t.label}</span>
              </Space>
            ),
          })),
          onClick: ({ key }) => { setPending(key); setStep(1) },
        }}
      >
        {trigger}
      </Dropdown>

      {/* Confirmation modal: two-step (review + reason) */}
      <Modal
        open={!!pending}
        title="Change ticket status"
        onCancel={() => { setPending(null); setStep(1); form.resetFields() }}
        footer={null}
        destroyOnHidden
      >
        {pending && (
          <div>
            <Space size={8} style={{ marginBottom: 16 }}>
              <StatusTag status={ticket.status} />
              <span>→</span>
              <StatusTag status={pending} />
            </Space>
            {step === 1 && (() => {
              const reasonMeta = REASON_LABELS[pending]
              const showField = REQUIRES_REASON.has(pending) || OPTIONAL_REASON.has(pending)
              const required = REQUIRES_REASON.has(pending)
              const requiresSector = pending === 'assigned_to_sector'
              return (
                <>
                  <p>You are about to change <code>{ticket.ticket_code}</code> from <b>{ticket.status}</b> to <b>{pending}</b>.</p>
                  <Form form={form} layout="vertical" initialValues={{ sector_code: ticket.current_sector_code || undefined }}>
                    {requiresSector && (
                      <Form.Item
                        name="sector_code"
                        label="Target sector"
                        rules={[{ required: true, message: 'Select the sector that should receive this ticket' }]}
                      >
                        <Select
                          showSearch
                          optionFilterProp="label"
                          loading={options.isLoading}
                          placeholder="Select sector"
                          options={(options.data?.sectors || []).map((s) => ({
                            value: s.code,
                            label: `${s.code} · ${s.name}`,
                          }))}
                        />
                      </Form.Item>
                    )}
                    {showField && (
                      <Form.Item
                        name="reason"
                        label={reasonMeta?.label || (required ? 'Reason' : 'Reason (optional)')}
                        rules={required ? [{ required: true, min: 3 }] : []}
                      >
                        <Input.TextArea rows={3} placeholder={reasonMeta?.placeholder} />
                      </Form.Item>
                    )}
                  </Form>
                  <Space style={{ marginTop: 8 }}>
                    <Button onClick={() => { setPending(null); form.resetFields() }}>Cancel</Button>
                    <Button type="primary" onClick={async () => {
                      if (required || requiresSector) {
                        try { await form.validateFields() } catch { return }
                      }
                      setStep(2)
                    }}>Continue</Button>
                  </Space>
                </>
              )
            })()}
            {step === 2 && (
              <>
                <p>Are you sure? This action will be recorded in the audit log.</p>
                <Space>
                  <Button onClick={() => setStep(1)}>Back</Button>
                  <Button type="primary" danger loading={change.isPending}
                          onClick={() => change.mutate({
                            status: pending,
                            reason: form.getFieldValue('reason'),
                            sectorCode: form.getFieldValue('sector_code'),
                          })}>
                    Yes, confirm change
                  </Button>
                </Space>
              </>
            )}
          </div>
        )}
      </Modal>
    </span>
  )
}
