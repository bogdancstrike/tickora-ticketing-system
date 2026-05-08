import { useState } from 'react'
import { Dropdown, Modal, Form, Input, Button, Space, message } from 'antd'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { DownOutlined } from '@ant-design/icons'
import { changeTicketStatus, type TicketDto } from '@/api/tickets'
import { StatusTag } from './StatusTag'

const ALLOWED_TRANSITIONS: Record<string, Array<{ to: string; label: string }>> = {
  pending:            [{ to: 'in_progress', label: 'Take ownership' }, { to: 'cancelled', label: 'Cancel' }],
  assigned_to_sector: [{ to: 'in_progress', label: 'Take ownership' }, { to: 'cancelled', label: 'Cancel' }],
  in_progress:        [{ to: 'done', label: 'Mark done' }, { to: 'assigned_to_sector', label: 'Unassign · back to sector' }],
  reopened:           [{ to: 'in_progress', label: 'Take ownership' }, { to: 'done', label: 'Mark done' }],
  waiting_for_user:   [{ to: 'done', label: 'Mark done' }],
  on_hold:            [{ to: 'done', label: 'Mark done' }],
  done:               [{ to: 'closed', label: 'Close ticket' }, { to: 'reopened', label: 'Reopen' }],
  closed:             [{ to: 'reopened', label: 'Reopen' }],
}

const REQUIRES_REASON = new Set(['cancelled', 'reopened'])

export function StatusChanger({ ticket, size = 'middle' }: { ticket: TicketDto; size?: 'small' | 'middle' }) {
  const [pending, setPending] = useState<string | null>(null)
  const [step, setStep] = useState<1 | 2>(1)
  const [form] = Form.useForm<{ reason?: string }>()
  const [msg, holder] = message.useMessage()
  const queryClient = useQueryClient()

  const transitions = ALLOWED_TRANSITIONS[ticket.status] || []

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
      await queryClient.invalidateQueries({ queryKey: ['ticketAudit', ticket.id] })
    },
    onError: (err) => msg.error(err.message),
  })

  if (transitions.length === 0) {
    return (
      <span onClick={(e) => e.stopPropagation()}>
        <StatusTag status={ticket.status} />
      </span>
    )
  }

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
        <span style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          <StatusTag status={ticket.status} />
          <DownOutlined style={{ fontSize: 10, opacity: 0.6 }} />
        </span>
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
            {step === 1 && (
              <>
                <p>You are about to change <code>{ticket.ticket_code}</code> from <b>{ticket.status}</b> to <b>{pending}</b>.</p>
                {REQUIRES_REASON.has(pending) && (
                  <Form form={form} layout="vertical">
                    <Form.Item name="reason" label="Reason" rules={[{ required: true, min: 3 }]}>
                      <Input.TextArea rows={3} />
                    </Form.Item>
                  </Form>
                )}
                <Space style={{ marginTop: 8 }}>
                  <Button onClick={() => { setPending(null); form.resetFields() }}>Cancel</Button>
                  <Button type="primary" onClick={async () => {
                    if (REQUIRES_REASON.has(pending)) {
                      try { await form.validateFields() } catch { return }
                    }
                    setStep(2)
                  }}>Continue</Button>
                </Space>
              </>
            )}
            {step === 2 && (
              <>
                <p>Are you sure? This action will be recorded in the audit log.</p>
                <Space>
                  <Button onClick={() => setStep(1)}>Back</Button>
                  <Button type="primary" danger loading={change.isPending}
                          onClick={() => change.mutate({ status: pending, reason: form.getFieldValue('reason') })}>
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
