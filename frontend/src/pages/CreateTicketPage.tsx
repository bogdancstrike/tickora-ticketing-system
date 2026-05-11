import { useNavigate } from 'react-router-dom'
import { useMemo, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Button, Flex, Form, Input, Select, Tag, Typography, message, theme as antTheme,
} from 'antd'
import { SaveOutlined } from '@ant-design/icons'
import {
  createTicket, getTicketOptions, listSubcategoryFields,
  type CreateTicketPayload, type SubcategoryFieldDto,
} from '@/api/tickets'
import { useSessionStore } from '@/stores/sessionStore'
import { ProductTour, TourInfoButton } from '@/components/common/ProductTour'
import { BeneficiaryTypeTag } from '@/components/common/BeneficiaryTypeTag'
import { useTranslation } from 'react-i18next'

interface CreateFormValues extends Omit<CreateTicketPayload, 'metadata'> {
  // Dynamic fields land under a `metadata` object — AntD's Form keeps nested
  // values when names are tuples (`['metadata', key]`), so the submit handler
  // can read them directly.
  metadata?: Record<string, string>
}

export function CreateTicketPage() {
  const { t } = useTranslation()
  const [form] = Form.useForm<CreateFormValues>()
  const [msg, holder] = message.useMessage()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { token } = antTheme.useToken()
  const user = useSessionStore((s) => s.user)
  const beneficiaryType: 'internal' | 'external' =
    user?.roles.includes('tickora_external_user') && !user?.roles.includes('tickora_internal_user')
      ? 'external'
      : 'internal'

  // Selected category drives the Subcategory dropdown; the selected
  // subcategory drives the dynamic field block. Both pieces of state are
  // local so the AntD form doesn't have to re-render the whole tree when
  // they change.
  const [categoryId, setCategoryId] = useState<string | undefined>()
  const [subcategoryId, setSubcategoryId] = useState<string | undefined>()

  const options = useQuery({
    queryKey: ['ticketOptions'],
    queryFn: getTicketOptions,
    staleTime: 300_000,
  })

  const fields = useQuery({
    queryKey: ['subcategoryFields', subcategoryId],
    queryFn: () => listSubcategoryFields(subcategoryId!),
    enabled: !!subcategoryId,
    staleTime: 60_000,
  })

  const subcategories = useMemo(() => {
    const cat = options.data?.categories.find((c) => c.id === categoryId)
    return cat?.subcategories ?? []
  }, [options.data, categoryId])

  const create = useMutation({
    mutationFn: createTicket,
    onSuccess: async (ticket) => {
      msg.success(`Created ${ticket.ticket_code}`)
      await queryClient.invalidateQueries({ queryKey: ['tickets'] })
      navigate(`/tickets/${ticket.id}`)
    },
    onError: (err) => msg.error(err.message),
  })

  const onFinish = (values: CreateFormValues) => {
    // Strip empty optional fields so the backend sees `undefined`, not '' —
    // the metadata validator treats blanks as "not provided" anyway, but
    // sending the raw form values keeps the payload self-documenting.
    const metadata: Record<string, string | null> = {}
    if (values.metadata) {
      for (const [k, v] of Object.entries(values.metadata)) {
        if (v !== undefined && v !== null && String(v).trim() !== '') {
          metadata[k] = String(v).trim()
        }
      }
    }
    create.mutate({
      ...values,
      beneficiary_type: beneficiaryType,
      category_id: values.category_id || null,
      subcategory_id: values.subcategory_id || null,
      metadata: Object.keys(metadata).length ? metadata : undefined,
    })
  }

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
          initialValues={{ beneficiary_type: beneficiaryType, priority: 'medium' }}
          onFinish={onFinish}
          onValuesChange={(changed) => {
            // Reset subcategory + dynamic fields when the category changes,
            // otherwise stale values from a previous category survive the
            // form re-render and slip into the submit payload.
            if ('category_id' in changed) {
              setCategoryId(changed.category_id || undefined)
              setSubcategoryId(undefined)
              form.setFieldsValue({ subcategory_id: undefined, metadata: {} })
            }
            if ('subcategory_id' in changed) {
              setSubcategoryId(changed.subcategory_id || undefined)
              form.setFieldsValue({ metadata: {} })
            }
          }}
        >
          <Form.Item name="beneficiary_type" hidden><Input /></Form.Item>
          <Alert
            data-tour-id="create-beneficiary"
            showIcon
            type="info"
            style={{ marginBottom: 16 }}
            message={<SpaceText label="Beneficiary type" value={<BeneficiaryTypeTag type={beneficiaryType} />} />}
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
            <Input.TextArea rows={6} placeholder="Describe the request, impact, affected assets, and expected outcome" />
          </Form.Item>

          <Flex gap={12} wrap="wrap">
            <Form.Item
              name="priority"
              label={t('common.priority')}
              rules={[{ required: true }]}
              style={{ minWidth: 200, flex: 1 }}
            >
              <Select options={(options.data?.priorities ?? ['low', 'medium', 'high', 'critical']).map((p) => ({
                value: p, label: t(`priority.${p}`, { defaultValue: p }),
              }))} />
            </Form.Item>
            <Form.Item
              name="category_id"
              label={t('common.category')}
              style={{ minWidth: 240, flex: 1 }}
            >
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                placeholder="—"
                options={(options.data?.categories ?? []).map((c) => ({ value: c.id, label: c.name }))}
              />
            </Form.Item>
            <Form.Item
              name="subcategory_id"
              label="Subcategory"
              style={{ minWidth: 240, flex: 1 }}
            >
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                placeholder={categoryId ? '—' : 'Pick a category first'}
                disabled={!categoryId || subcategories.length === 0}
                options={subcategories.map((s) => ({ value: s.id, label: s.name }))}
              />
            </Form.Item>
          </Flex>

          {/* Dynamic fields driven by the selected subcategory. Required
              fields wear the AntD red asterisk; option-lists render as a
              Select, free text as an Input. */}
          {subcategoryId && (fields.data?.items?.length ?? 0) > 0 && (
            <div style={{
              marginTop: 4, padding: 12, borderRadius: 6,
              background: 'rgba(0,0,0,0.02)', border: '1px solid rgba(0,0,0,0.06)',
            }}>
              <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
                Additional information
              </Typography.Text>
              <Flex wrap="wrap" gap={12}>
                {(fields.data?.items || []).map((field) => (
                  <DynamicField key={field.id} field={field} />
                ))}
              </Flex>
            </div>
          )}

          <Flex justify="end" gap={8} data-tour-id="create-actions" style={{ marginTop: 12 }}>
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

function DynamicField({ field }: { field: SubcategoryFieldDto }) {
  const rules = field.is_required
    ? [{ required: true, message: `${field.label} is required` }]
    : []
  return (
    <Form.Item
      name={['metadata', field.key]}
      label={field.label}
      required={field.is_required}
      rules={rules}
      tooltip={field.description || undefined}
      style={{ minWidth: 240, flex: 1 }}
    >
      {field.options && field.options.length > 0 ? (
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder="—"
          options={field.options.map((o) => ({ value: o, label: o }))}
        />
      ) : (
        <Input placeholder={field.label} />
      )}
    </Form.Item>
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
