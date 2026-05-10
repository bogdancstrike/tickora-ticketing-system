import { useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Button, Flex, Form, Input, Tag, Typography, message, theme as antTheme,
} from 'antd'
import { SaveOutlined } from '@ant-design/icons'
import { createTicket, type CreateTicketPayload } from '@/api/tickets'
import { useSessionStore } from '@/stores/sessionStore'
import { ProductTour, TourInfoButton } from '@/components/common/ProductTour'
import { useTranslation } from 'react-i18next'

export function CreateTicketPage() {
  const { t } = useTranslation()
  const [form] = Form.useForm<CreateTicketPayload>()
  const [msg, holder] = message.useMessage()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { token } = antTheme.useToken()
  const user = useSessionStore((s) => s.user)
  const beneficiaryType: 'internal' | 'external' =
    user?.roles.includes('tickora_external_user') && !user?.roles.includes('tickora_internal_user')
      ? 'external'
      : 'internal'

  const create = useMutation({
    mutationFn: createTicket,
    onSuccess: async (ticket) => {
      msg.success(`Created ${ticket.ticket_code}`)
      await queryClient.invalidateQueries({ queryKey: ['tickets'] })
      navigate(`/tickets/${ticket.id}`)
    },
    onError: (err) => msg.error(err.message),
  })

  return (
    <div style={{ padding: 24, display: 'grid', gap: 16, maxWidth: 920 }}>
      {holder}
      <Flex justify="space-between" align="center" wrap="wrap" gap={12}>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>Create Ticket</Typography.Title>
          <Typography.Text type="secondary">Register a beneficiary request for distribution and follow-up</Typography.Text>
        </div>
        <TourInfoButton pageKey="create-ticket" />
      </Flex>

      {create.error && <Alert type="error" message={create.error.message} showIcon />}

      <div style={{ border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8, padding: 16 }}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{ beneficiary_type: beneficiaryType }}
          onFinish={(values) => create.mutate({ ...values, beneficiary_type: beneficiaryType })}
        >
          <Form.Item name="beneficiary_type" hidden><Input /></Form.Item>
          <Alert
            data-tour-id="create-beneficiary"
            showIcon
            type="info"
            style={{ marginBottom: 16 }}
            title={<SpaceText label="Beneficiary type" value={<Tag>{beneficiaryType}</Tag>} />}
            description="This is derived from your account role and cannot be changed while creating a ticket."
          />

          {beneficiaryType === 'external' && (
            <>
              <Flex gap={12} wrap="wrap">
                <Form.Item name="requester_first_name" label="First name" rules={[{ required: true }]} style={{ minWidth: 220, flex: 1 }}>
                  <Input />
                </Form.Item>
                <Form.Item name="requester_last_name" label="Last name" rules={[{ required: true }]} style={{ minWidth: 220, flex: 1 }}>
                  <Input />
                </Form.Item>
              </Flex>
              <Flex gap={12} wrap="wrap">
                <Form.Item name="requester_email" label="Email" rules={[{ type: 'email' }]} style={{ minWidth: 260, flex: 1 }}>
                  <Input />
                </Form.Item>
                <Form.Item name="requester_phone" label="Phone" style={{ minWidth: 180 }}>
                  <Input />
                </Form.Item>
                <Form.Item name="organization_name" label="Organization" style={{ minWidth: 220, flex: 1 }}>
                  <Input />
                </Form.Item>
              </Flex>
            </>
          )}

          <Form.Item name="title" label="Title" rules={[{ max: 500 }]} data-tour-id="create-title">
            <Input placeholder="Short summary" />
          </Form.Item>
          <Form.Item name="txt" label="Description" rules={[{ required: true, min: 5, max: 20000 }]} data-tour-id="create-description">
            <Input.TextArea rows={8} placeholder="Describe the request, impact, affected assets, and expected outcome" />
          </Form.Item>

          <Flex justify="end" gap={8} data-tour-id="create-actions">
            <Button onClick={() => navigate('/tickets')}>Cancel</Button>
            <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={create.isPending}>
              Create
            </Button>
          </Flex>
        </Form>
      </div>
      <ProductTour
        pageKey="create-ticket"
        steps={[
          { target: '[data-tour-id="create-beneficiary"]', content: t('tour.create.beneficiary') },
          { target: '[data-tour-id="create-title"]', content: t('tour.create.title') },
          { target: '[data-tour-id="create-description"]', content: t('tour.create.description') },
          { target: '[data-tour-id="create-actions"]', content: t('tour.create.actions') },
        ]}
      />
    </div>
  )
}

function SpaceText({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Flex align="center" gap={8}>
      <Typography.Text>{label}</Typography.Text>
      {value}
    </Flex>
  )
}
