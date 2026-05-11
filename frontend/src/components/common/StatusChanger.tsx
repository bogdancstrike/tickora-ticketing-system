import { useMemo, useState } from 'react'
import { Dropdown, Modal, Form, Input, Button, Space, message } from 'antd'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { DownOutlined, SwapOutlined } from '@ant-design/icons'
import { changeTicketStatus, type TicketDto } from '@/api/tickets'
import { useSessionStore } from '@/stores/sessionStore'
import { StatusTag } from './StatusTag'

interface Transition { to: string; label: string }

const STATUSES: Transition[] = [
  { to: 'pending', label: 'Pending' },
  { to: 'assigned_to_sector', label: 'Assigned to sector' },
  { to: 'in_progress', label: 'In progress' },
  { to: 'done', label: 'Done' },
  { to: 'cancelled', label: 'Cancelled' },
]

const REQUIRES_REASON = new Set<string>()
// Optional but prompted: ask the operator to leave a closing note even though
// the backend is happy with empty.
const OPTIONAL_REASON = new Set(['pending', 'assigned_to_sector', 'in_progress', 'done', 'cancelled'])

const REASON_LABELS: Record<string, { label: string; placeholder?: string }> = {
  pending:            { label: 'Reason (optional)',             placeholder: 'Why is this ticket going back to pending?' },
  done:               { label: 'Resolution (optional)',         placeholder: 'How was this ticket resolved?' },
  cancelled:          { label: 'Cancellation reason',           placeholder: 'Why is this ticket being cancelled?' },
  in_progress:        { label: 'Reason (optional)',             placeholder: 'Why is this ticket moving to in progress?' },
  assigned_to_sector: { label: 'Reason (optional)',             placeholder: 'Why are you releasing this ticket?' },
}

/**
 * A specialized component for managing ticket status transitions.
 * It enforces the state machine rules defined in the backend, ensuring only
 * valid transitions are available based on the user's role and the ticket's current state.
 * Supports both tag-like dropdowns and button-style interfaces.
 * 
 * @param {Object} props - The component props.
 * @param {TicketDto} props.ticket - The ticket instance whose status is being changed.
 * @param {'small' | 'middle'} [props.size] - The size of the UI element.
 * @param {'tag' | 'button'} [props.mode] - The display mode of the component.
 */
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
  const [form] = Form.useForm<{ reason?: string }>()
  const [msg, holder] = message.useMessage()
  const queryClient = useQueryClient()
  const user = useSessionStore((s) => s.user)
  const transitions = useMemo<Transition[]>(() => {
    if (!user) return []
    const isAssignee = !!user.id && (
      ticket.assignee_user_id === user.id
      || (ticket.assignee_user_ids || []).includes(user.id)
    )

    // Operators must be assigned to drive status. Admin/chief/distributor
    // users can route or assign through explicit assignment actions, but
    // status changes require an assignee link.
    if (isAssignee) return STATUSES.filter((s) => s.to !== ticket.status)

    return []
  }, [ticket, user])

  const change = useMutation({
    mutationFn: ({ status, reason }: { status: string; reason?: string }) =>
      changeTicketStatus(ticket.id, status, reason),
    onSuccess: async () => {
      msg.success('Status changed')
      setPending(null)
      setStep(1)
      form.resetFields()
      await queryClient.invalidateQueries({ queryKey: ['tickets'] })
      await queryClient.invalidateQueries({ queryKey: ['ticket', ticket.id] })
      await queryClient.invalidateQueries({ queryKey: ['comments', ticket.id] })
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
              return (
                <>
                  <p>You are about to change <code>{ticket.ticket_code}</code> from <b>{ticket.status}</b> to <b>{pending}</b>.</p>
                  <Form form={form} layout="vertical">
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
                      if (required) {
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
