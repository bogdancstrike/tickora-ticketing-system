import { useState } from 'react'
import {
  Button, Divider, Empty, Form, Input, Layout, Modal, Popconfirm, Select, Space,
  Spin, Tag, Typography, message, theme as antTheme,
} from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import { useSessionStore } from '@/stores/sessionStore'
import { listAdminSectors } from '@/api/admin'
import {
  createSnippet, deleteSnippet, listSnippets, updateSnippet,
  type Snippet, type SnippetAudience,
} from '@/api/snippets'
import { useTranslation } from 'react-i18next'

const { Sider, Content } = Layout
const { Title, Text } = Typography

const ROLES = [
  'tickora_admin',
  'tickora_distributor',
  'tickora_avizator',
  'tickora_sector_chief',
  'tickora_sector_member',
  'tickora_internal_user',
  'tickora_external_user',
]

const BENEFICIARY_TYPES = ['internal', 'external']

function AudienceTag({ a }: { a: SnippetAudience }) {
  const colorMap: Record<string, string> = { sector: 'blue', role: 'purple', beneficiary_type: 'green' }
  return <Tag color={colorMap[a.kind]}>{a.kind}: {a.value}</Tag>
}

interface SnippetFormValues {
  title: string
  body: string
  audiences: { kind: string; value: string }[]
}

function SnippetModal({
  open,
  initial,
  sectors,
  onClose,
  onSave,
}: {
  open: boolean
  initial?: Snippet | null
  sectors: string[]
  onClose: () => void
  onSave: (values: SnippetFormValues) => Promise<void>
}) {
  const [form] = Form.useForm<SnippetFormValues>()
  const [saving, setSaving] = useState(false)
  const { t } = useTranslation()

  const handleOk = async () => {
    try {
      const values = await form.validateFields()
      setSaving(true)
      await onSave(values)
      form.resetFields()
      onClose()
    } catch {
      // validation errors stay in form
    } finally {
      setSaving(false)
    }
  }

  const afterOpenChange = (visible: boolean) => {
    if (visible) {
      form.setFieldsValue({
        title: initial?.title ?? '',
        body: initial?.body ?? '',
        audiences: initial?.audiences ?? [],
      })
    } else {
      form.resetFields()
    }
  }

  return (
    <Modal
      open={open}
      title={initial ? t('procedures.edit') : t('procedures.new')}
      onOk={handleOk}
      onCancel={onClose}
      okText={t('common.save')}
      cancelText={t('common.cancel')}
      confirmLoading={saving}
      width={680}
      afterOpenChange={afterOpenChange}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item name="title" label={t('common.title')} rules={[{ required: true, message: t('procedures.title_required') }]}>
          <Input />
        </Form.Item>
        <Form.Item name="body" label={t('procedures.body')} rules={[{ required: true, message: t('procedures.body_required') }]}>
          <Input.TextArea rows={10} style={{ fontFamily: 'monospace', fontSize: 13 }} placeholder="Markdown supported…" />
        </Form.Item>
        <Form.Item name="audiences" label={t('procedures.audiences_label')}>
          <Form.List name="audiences">
            {(fields, { add, remove }) => (
              <div>
                {fields.map((field) => (
                  <Space key={field.key} style={{ display: 'flex', marginBottom: 8 }} align="start">
                    <Form.Item
                      {...field}
                      name={[field.name, 'kind']}
                      noStyle
                      rules={[{ required: true }]}
                    >
                      <Select
                        style={{ width: 160 }}
                        placeholder={t('procedures.audience_kind')}
                        options={[
                          { value: 'sector', label: 'Sector' },
                          { value: 'role', label: 'Role' },
                          { value: 'beneficiary_type', label: 'Beneficiary type' },
                        ]}
                      />
                    </Form.Item>
                    <Form.Item
                      noStyle
                      shouldUpdate={(prev, cur) =>
                        prev.audiences?.[field.name]?.kind !== cur.audiences?.[field.name]?.kind
                      }
                    >
                      {({ getFieldValue }) => {
                        const kind = getFieldValue(['audiences', field.name, 'kind'])
                        if (kind === 'sector') {
                          return (
                            <Form.Item name={[field.name, 'value']} noStyle rules={[{ required: true }]}>
                              <Select
                                style={{ width: 200 }}
                                placeholder={t('procedures.audience_value')}
                                options={sectors.map((s) => ({ value: s, label: s }))}
                              />
                            </Form.Item>
                          )
                        }
                        if (kind === 'role') {
                          return (
                            <Form.Item name={[field.name, 'value']} noStyle rules={[{ required: true }]}>
                              <Select
                                style={{ width: 200 }}
                                placeholder={t('procedures.audience_value')}
                                options={ROLES.map((r) => ({ value: r, label: r.replace('tickora_', '') }))}
                              />
                            </Form.Item>
                          )
                        }
                        if (kind === 'beneficiary_type') {
                          return (
                            <Form.Item name={[field.name, 'value']} noStyle rules={[{ required: true }]}>
                              <Select
                                style={{ width: 200 }}
                                placeholder={t('procedures.audience_value')}
                                options={BENEFICIARY_TYPES.map((b) => ({ value: b, label: b }))}
                              />
                            </Form.Item>
                          )
                        }
                        return (
                          <Form.Item name={[field.name, 'value']} noStyle rules={[{ required: true }]}>
                            <Input style={{ width: 200 }} placeholder={t('procedures.audience_value')} />
                          </Form.Item>
                        )
                      }}
                    </Form.Item>
                    <Button type="text" danger onClick={() => remove(field.name)}>✕</Button>
                  </Space>
                ))}
                <Button type="dashed" onClick={() => add({ kind: '', value: '' })} icon={<PlusOutlined />}>
                  {t('procedures.add_audience')}
                </Button>
                <div style={{ marginTop: 4 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {t('procedures.audiences_hint')}
                  </Text>
                </div>
              </div>
            )}
          </Form.List>
        </Form.Item>
      </Form>
    </Modal>
  )
}

export function ProceduresPage() {
  const { token } = antTheme.useToken()
  const { t } = useTranslation()
  const user = useSessionStore((s) => s.user)
  const isAdmin = !!user?.hasRootGroup
  const qc = useQueryClient()

  const [selected, setSelected] = useState<Snippet | null>(null)
  const [search, setSearch] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Snippet | null>(null)

  const snippetsQuery = useQuery({
    queryKey: ['snippets'],
    queryFn: listSnippets,
  })

  const sectorsQuery = useQuery({
    queryKey: ['adminSectors'],
    queryFn: listAdminSectors,
    enabled: isAdmin,
  })

  const sectorCodes = sectorsQuery.data?.items.map((s) => s.code) ?? []

  const createMutation = useMutation({
    mutationFn: (v: { title: string; body: string; audiences: SnippetAudience[] }) =>
      createSnippet(v),
    onSuccess: () => {
      message.success(t('procedures.created'))
      qc.invalidateQueries({ queryKey: ['snippets'] })
    },
    onError: (e: any) => message.error(e.response?.data?.error || t('errors.generic')),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, ...rest }: { id: string; title: string; body: string; audiences: SnippetAudience[] }) =>
      updateSnippet(id, rest),
    onSuccess: (updated) => {
      message.success(t('procedures.updated'))
      qc.invalidateQueries({ queryKey: ['snippets'] })
      setSelected(updated)
    },
    onError: (e: any) => message.error(e.response?.data?.error || t('errors.generic')),
  })

  const deleteMutation = useMutation({
    mutationFn: deleteSnippet,
    onSuccess: () => {
      message.success(t('procedures.deleted'))
      qc.invalidateQueries({ queryKey: ['snippets'] })
      setSelected(null)
    },
    onError: (e: any) => message.error(e.response?.data?.error || t('errors.generic')),
  })

  const items = (snippetsQuery.data?.items ?? []).filter((s) =>
    s.title.toLowerCase().includes(search.toLowerCase()),
  )

  const handleSave = async (values: { title: string; body: string; audiences: { kind: string; value: string }[] }) => {
    const audiences = values.audiences.filter((a) => a.kind && a.value) as SnippetAudience[]
    if (editing) {
      await updateMutation.mutateAsync({ id: editing.id, title: values.title, body: values.body, audiences })
    } else {
      await createMutation.mutateAsync({ title: values.title, body: values.body, audiences })
    }
  }

  const openCreate = () => {
    setEditing(null)
    setModalOpen(true)
  }

  const openEdit = (s: Snippet) => {
    setEditing(s)
    setModalOpen(true)
  }

  return (
    <Layout style={{ height: '100%', background: token.colorBgContainer }}>
      {/* Sidebar */}
      <Sider
        width={260}
        style={{
          background: token.colorBgContainer,
          borderRight: `1px solid ${token.colorBorder}`,
          height: '100%',
          overflow: 'auto',
        }}
      >
        <div style={{ padding: '16px 12px 8px' }}>
          <Title level={5} style={{ margin: 0 }}>{t('procedures.title')}</Title>
        </div>
        <div style={{ padding: '0 12px 8px' }}>
          <Input.Search
            placeholder={t('common.search')}
            allowClear
            size="small"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        {isAdmin && (
          <div style={{ padding: '0 12px 8px' }}>
            <Button type="dashed" size="small" icon={<PlusOutlined />} block onClick={openCreate}>
              {t('procedures.new')}
            </Button>
          </div>
        )}
        <Divider style={{ margin: '0 0 4px' }} />
        {snippetsQuery.isLoading ? (
          <div style={{ textAlign: 'center', padding: 24 }}><Spin /></div>
        ) : items.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '24px 0' }} description={t('procedures.empty')} />
        ) : (
          items.map((s) => (
            <div
              key={s.id}
              onClick={() => setSelected(s)}
              style={{
                padding: '8px 12px',
                cursor: 'pointer',
                background: selected?.id === s.id ? token.colorPrimaryBg : 'transparent',
                borderLeft: selected?.id === s.id ? `3px solid ${token.colorPrimary}` : '3px solid transparent',
              }}
            >
              <Text strong={selected?.id === s.id} ellipsis style={{ display: 'block' }}>
                {s.title}
              </Text>
              {s.audiences.length > 0 && (
                <div style={{ marginTop: 2 }}>
                  {s.audiences.slice(0, 2).map((a, i) => (
                    <Tag key={i} style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: '0 2px 0 0' }}>
                      {a.value}
                    </Tag>
                  ))}
                  {s.audiences.length > 2 && <Tag style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>+{s.audiences.length - 2}</Tag>}
                </div>
              )}
            </div>
          ))
        )}
      </Sider>

      {/* Main content */}
      <Content style={{ padding: 24, overflow: 'auto', background: token.colorBgContainer }}>
        {!selected ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
            <Empty
              description={<Text type="secondary">{t('procedures.select_hint')}</Text>}
            />
          </div>
        ) : (
          <div style={{ maxWidth: 860 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
              <Title level={3} style={{ margin: 0 }}>{selected.title}</Title>
              {isAdmin && (
                <Space>
                  <Button icon={<EditOutlined />} size="small" onClick={() => openEdit(selected)}>
                    {t('common.edit')}
                  </Button>
                  <Popconfirm
                    title={t('procedures.delete_confirm')}
                    onConfirm={() => deleteMutation.mutate(selected.id)}
                    okType="danger"
                    okText={t('common.delete')}
                    cancelText={t('common.cancel')}
                  >
                    <Button icon={<DeleteOutlined />} size="small" danger>
                      {t('common.delete')}
                    </Button>
                  </Popconfirm>
                </Space>
              )}
            </div>

            {selected.audiences.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>{t('procedures.visible_to')}: </Text>
                {selected.audiences.map((a, i) => <AudienceTag key={i} a={a} />)}
              </div>
            )}

            <Divider style={{ margin: '12px 0' }} />

            <div style={{ lineHeight: 1.7 }}>
              <ReactMarkdown>{selected.body}</ReactMarkdown>
            </div>

            <div style={{ marginTop: 16 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {selected.updated_at
                  ? `${t('common.updated_at')} ${new Date(selected.updated_at).toLocaleString()}`
                  : selected.created_at
                  ? `${t('common.created_at')} ${new Date(selected.created_at).toLocaleString()}`
                  : null}
              </Text>
            </div>
          </div>
        )}
      </Content>

      <SnippetModal
        open={modalOpen}
        initial={editing}
        sectors={sectorCodes}
        onClose={() => setModalOpen(false)}
        onSave={handleSave}
      />
    </Layout>
  )
}
