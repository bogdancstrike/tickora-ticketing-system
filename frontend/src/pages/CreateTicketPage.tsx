import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Button, Flex, Form, Input, Select, Typography, message, theme as antTheme,
} from 'antd'
import { SaveOutlined } from '@ant-design/icons'
import { createTicket, type CreateTicketPayload } from '@/api/tickets'

export function CreateTicketPage() {
  const [form] = Form.useForm<CreateTicketPayload>()
  const [beneficiaryType, setBeneficiaryType] = useState<'internal' | 'external'>('internal')
  const [msg, holder] = message.useMessage()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { token } = antTheme.useToken()

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
      <div>
        <Typography.Title level={3} style={{ margin: 0 }}>Create Ticket</Typography.Title>
        <Typography.Text type="secondary">Register a beneficiary request for distribution and follow-up</Typography.Text>
      </div>

      {create.error && <Alert type="error" message={create.error.message} showIcon />}

      <div style={{ border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8, padding: 16 }}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{ beneficiary_type: 'internal' }}
          onFinish={(values) => create.mutate(values)}
          onValuesChange={(changed) => {
            if (changed.beneficiary_type) setBeneficiaryType(changed.beneficiary_type)
          }}
        >
          <Flex gap={12} wrap="wrap">
            <Form.Item name="beneficiary_type" label="Beneficiary" rules={[{ required: true }]} style={{ minWidth: 180 }}>
              <Select options={[
                { value: 'internal', label: 'Internal' },
                { value: 'external', label: 'External' },
              ]} />
            </Form.Item>
          </Flex>

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

          <Form.Item name="title" label="Title" rules={[{ max: 500 }]}>
            <Input placeholder="Short summary" />
          </Form.Item>
          <Form.Item name="txt" label="Description" rules={[{ required: true, min: 5, max: 20000 }]}>
            <Input.TextArea rows={8} placeholder="Describe the request, impact, affected assets, and expected outcome" />
          </Form.Item>

          <Flex justify="end" gap={8}>
            <Button onClick={() => navigate('/tickets')}>Cancel</Button>
            <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={create.isPending}>
              Create
            </Button>
          </Flex>
        </Form>
      </div>
    </div>
  )
}
