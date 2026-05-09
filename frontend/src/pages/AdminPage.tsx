import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import ReactECharts from 'echarts-for-react'
import {
  Alert, Button, Col, Empty, Flex, Form, Input, List, Modal, Row, Select, Space,
  Statistic, Table, Tag, Typography, theme as antTheme, Switch, message, Tabs, Spin,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  ApartmentOutlined, AppstoreOutlined, AuditOutlined, BarChartOutlined,
  CarryOutOutlined, DatabaseOutlined, FieldTimeOutlined, HistoryOutlined,
  LineChartOutlined, MessageOutlined, PieChartOutlined, PlusOutlined,
  ReloadOutlined, SafetyCertificateOutlined, SendOutlined, SettingOutlined, SmileOutlined, TeamOutlined,
  UnorderedListOutlined, UserOutlined, ClockCircleOutlined,
  DashboardOutlined, InfoCircleOutlined,
} from '@ant-design/icons'
import {
  ADMIN_ROLES, createAdminSector, getAdminOverview,
  getGroupHierarchy, grantMembership, listAdminMemberships, listAdminMetadataKeys,
  listAdminSectors, listAdminUsers, revokeMembership, updateAdminSector,
  updateAdminUser, upsertAdminMetadataKey,
  listAdminWidgets, upsertAdminWidget, syncAdminWidgets,
  listSystemSettings, upsertSystemSetting,
  type AdminMembership, type AdminMetadataKey, type AdminSector,
  type AdminUser, type AdminWidgetDefinition, type SystemSetting,
  listAdminTicketMetadatas, upsertAdminTicketMetadata, deleteAdminTicketMetadata,
} from '@/api/admin'
import type { MonitorBreakdown, AdminTicketMetadata } from '@/api/tickets'
import { fmtDateTime } from '@/components/common/format'

const ICON_MAP: Record<string, React.ReactNode> = {
  UnorderedListOutlined: <UnorderedListOutlined />,
  BarChartOutlined: <BarChartOutlined />,
  AuditOutlined: <AuditOutlined />,
  UserOutlined: <UserOutlined />,
  MessageOutlined: <MessageOutlined />,
  PieChartOutlined: <PieChartOutlined />,
  TeamOutlined: <TeamOutlined />,
  HistoryOutlined: <HistoryOutlined />,
  LineChartOutlined: <LineChartOutlined />,
  SendOutlined: <SendOutlined />,
  FieldTimeOutlined: <FieldTimeOutlined />,
  DatabaseOutlined: <DatabaseOutlined />,
  CarryOutOutlined: <CarryOutOutlined />,
  SmileOutlined: <SmileOutlined />,
  ClockCircleOutlined: <ClockCircleOutlined />,
  DashboardOutlined: <DashboardOutlined />,
  InfoCircleOutlined: <InfoCircleOutlined />,
}

function getIconComponent(name: string | null | undefined) {
  if (!name) return <AppstoreOutlined />
  return ICON_MAP[name] || <AppstoreOutlined />
}

function labelize(value: string) {
  return value.split('_').join(' ')
}

function MetricPanel({ values }: { values: Record<string, number | null | undefined> }) {
  const { token } = antTheme.useToken()
  return (
    <Row gutter={[12, 12]}>
      {Object.entries(values).map(([key, value]) => (
        <Col key={key} xs={12} md={6}>
          <div style={{ background: token.colorBgContainer, border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8, padding: 14, minHeight: 94 }}>
            <Statistic title={labelize(key)} value={value ?? '-'} />
          </div>
        </Col>
      ))}
    </Row>
  )
}

function Panel({ title, icon, children }: { title: string; icon?: React.ReactNode; children: React.ReactNode }) {
  const { token } = antTheme.useToken()
  return (
    <div style={{ background: token.colorBgContainer, border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8, padding: 20, boxShadow: token.boxShadowTertiary }}>
      <Flex align="center" gap={12} style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 20, color: token.colorPrimary }}>{icon}</div>
        <Typography.Title level={4} style={{ margin: 0 }}>{title}</Typography.Title>
      </Flex>
      {children}
    </div>
  )
}

function WidgetCataloguePanel() {
  const { token } = antTheme.useToken()
  const qc = useQueryClient()
  const [editing, setEditing] = useState<AdminWidgetDefinition | null>(null)
  const widgets = useQuery({ queryKey: ['adminWidgets'], queryFn: listAdminWidgets, staleTime: 60_000 })

  const sync = useMutation({
    mutationFn: syncAdminWidgets,
    onSuccess: () => {
      message.success('Catalogue synced with defaults')
      qc.invalidateQueries({ queryKey: ['adminWidgets'] })
    },
  })

  const save = useMutation({
    mutationFn: (values: Partial<AdminWidgetDefinition>) => upsertAdminWidget({ ...editing, ...values } as AdminWidgetDefinition),
    onSuccess: () => {
      message.success('Widget updated')
      setEditing(null)
      qc.invalidateQueries({ queryKey: ['adminWidgets'] })
    },
  })

  const columns: ColumnsType<AdminWidgetDefinition> = [
    {
      title: 'Icon',
      dataIndex: 'icon',
      width: 80,
      align: 'center',
      render: (icon) => (
        <div style={{
          fontSize: 18,
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: 32,
          width: 32,
          margin: '0 auto',
          background: token.colorFillAlter,
          borderRadius: 4,
          border: `1px solid ${token.colorBorderSecondary}`
        }}>
          {getIconComponent(icon)}
        </div>
      ),
    },
    { title: 'Type', dataIndex: 'type', width: 160 },
    { title: 'Display Name', dataIndex: 'display_name', width: 220 },
    { title: 'Description', dataIndex: 'description', ellipsis: true },
    {
      title: 'Active',
      dataIndex: 'is_active',
      width: 100,
      render: (active) => <Tag color={active ? 'green' : 'default'}>{active ? 'active' : 'inactive'}</Tag>,
    },
    {
      title: 'Action',
      width: 100,
      render: (_, row) => <Button size="small" onClick={() => setEditing(row)}>Edit</Button>,
    },
  ]

  return (
    <Panel title="Widget catalogue" icon={<DatabaseOutlined />}>
      <Flex justify="end" style={{ marginBottom: 12 }}>
        <Button
          icon={<ReloadOutlined />}
          loading={sync.isPending}
          onClick={() => sync.mutate()}
        >
          Sync with defaults
        </Button>
      </Flex>
      <Table
        rowKey="type"
        loading={widgets.isLoading}
        dataSource={widgets.data?.items || []}
        pagination={{ pageSize: 10 }}
        columns={columns}
      />
      <Modal
        title="Edit widget definition"
        open={!!editing}
        onCancel={() => setEditing(null)}
        footer={null}
        destroyOnHide
      >
        <Form
          layout="vertical"
          initialValues={editing || {}}
          onFinish={(values) => save.mutate(values)}
        >
          <Form.Item name="type" label="Type"><Input disabled /></Form.Item>
          <Form.Item name="display_name" label="Display Name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="Description"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="icon" label="Icon (AntD Name)"><Input placeholder="e.g. BarChartOutlined" /></Form.Item>
          <Form.Item name="is_active" label="Active" valuePropName="checked"><Switch /></Form.Item>
          <Button type="primary" htmlType="submit" loading={save.isPending}>Save</Button>
        </Form>
      </Modal>
    </Panel>
  )
}

function UsersTab() {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<AdminUser | null>(null)
  const [pagination, setPagination] = useState({ current: 1, pageSize: 10 })

  const users = useQuery({ 
    queryKey: ['adminUsers', search, pagination], 
    queryFn: () => listAdminUsers({ 
        search: search || undefined,
        limit: pagination.pageSize,
        offset: (pagination.current - 1) * pagination.pageSize
    }), 
    staleTime: 30_000 
  })
  const sectors = useQuery({ queryKey: ['adminSectors'], queryFn: listAdminSectors, staleTime: 60_000 })
  const grant = useMutation({
    mutationFn: grantMembership,
    onSuccess: () => { message.success('Membership granted'); qc.invalidateQueries({ queryKey: ['adminUsers'] }); qc.invalidateQueries({ queryKey: ['adminMemberships'] }); qc.invalidateQueries({ queryKey: ['groupHierarchy'] }) },
  })
  const revoke = useMutation({
    mutationFn: revokeMembership,
    onSuccess: () => { message.success('Membership revoked'); qc.invalidateQueries({ queryKey: ['adminUsers'] }); qc.invalidateQueries({ queryKey: ['adminMemberships'] }); qc.invalidateQueries({ queryKey: ['groupHierarchy'] }) },
  })
  const update = useMutation({
    mutationFn: ({ id, roles, is_active }: { id: string; roles?: AdminUser['roles']; is_active?: boolean }) => updateAdminUser(id, { roles, is_active }),
    onSuccess: () => { message.success('User updated'); qc.invalidateQueries({ queryKey: ['adminUsers'] }) },
  })
  const columns: ColumnsType<AdminUser> = [
    { title: 'User', key: 'user', render: (_, u) => <Space orientation="vertical" size={0}><Typography.Text strong>{u.username || u.email || u.id}</Typography.Text><Typography.Text type="secondary">{u.email}</Typography.Text></Space> },
    { title: 'Roles', dataIndex: 'roles', render: (roles: string[]) => <Space wrap>{roles.map((r) => <Tag key={r}>{r.replace('tickora_', '')}</Tag>)}</Space> },
    { title: 'Groups', dataIndex: 'memberships', render: (memberships: AdminMembership[]) => <Space wrap>{memberships.map((m) => <Tag key={m.id} color={m.role === 'chief' ? 'gold' : 'blue'}>{m.sector_code} · {m.role}</Tag>)}</Space> },
    { title: 'Active', dataIndex: 'is_active', width: 90, render: (active, u) => <Switch checked={active} onChange={(checked) => update.mutate({ id: u.id, is_active: checked })} /> },
    { title: 'Edit', width: 90, render: (_, u) => <Button size="small" onClick={() => setSelected(u)}>Manage</Button> },
  ]
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <Flex justify="space-between" wrap="wrap" gap={12}>
        <Space size={16}>
          <Input.Search placeholder="Search users" allowClear onSearch={setSearch} style={{ maxWidth: 360 }} />
          <Statistic value={users.data?.total || 0} suffix="users" valueStyle={{ fontSize: 16 }} />
        </Space>
        <Button icon={<ReloadOutlined />} onClick={() => users.refetch()} />
      </Flex>
      <Table 
        rowKey="id" 
        loading={users.isLoading} 
        columns={columns} 
        dataSource={users.data?.items || []} 
        pagination={{ 
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: users.data?.total || 0,
            showSizeChanger: true,
            showTotal: (total) => `Total ${total} items`
        }} 
        onChange={(p) => setPagination({ current: p.current || 1, pageSize: p.pageSize || 10 })}
      />
      <Modal title="Manage user access" open={!!selected} onCancel={() => setSelected(null)} footer={null} width={760}>
        {selected && (
          <div style={{ display: 'grid', gap: 16 }}>
            <Typography.Text type="secondary">{selected.keycloak_subject}</Typography.Text>
            <Form layout="vertical" onFinish={(values) => update.mutate({ id: selected.id, roles: values.roles })} initialValues={{ roles: selected.roles }}>
              <Form.Item name="roles" label="Realm roles">
                <Select mode="multiple" options={ADMIN_ROLES.map((role) => ({ value: role, label: role }))} />
              </Form.Item>
              <Button type="primary" htmlType="submit">Save roles</Button>
            </Form>
            <Form layout="inline" onFinish={(values) => grant.mutate({ user_id: selected.id, sector_code: values.sector_code, role: values.role })}>
              <Form.Item name="sector_code" rules={[{ required: true }]}><Select placeholder="Sector" style={{ width: 220 }} options={(sectors.data?.items || []).map((s) => ({ value: s.code, label: `${s.code} · ${s.name}` }))} /></Form.Item>
              <Form.Item name="role" rules={[{ required: true }]}><Select placeholder="Role" style={{ width: 140 }} options={[{ value: 'member', label: 'member' }, { value: 'chief', label: 'chief' }]} /></Form.Item>
              <Button htmlType="submit" icon={<PlusOutlined />}>Grant group</Button>
            </Form>
            <Table
              rowKey="id"
              size="small"
              pagination={false}
              dataSource={selected.memberships}
              columns={[
                { title: 'Sector', dataIndex: 'sector_code' },
                { title: 'Role', dataIndex: 'role', render: (role) => <Tag>{role}</Tag> },
                { title: 'Action', width: 120, render: (_, m) => <Button size="small" danger onClick={() => revoke.mutate(m.id)}>Revoke</Button> },
              ]}
            />
          </div>
        )}
      </Modal>
    </div>
  )
}

function SectorsTab() {
  const qc = useQueryClient()
  const [editing, setEditing] = useState<AdminSector | null>(null)
  const sectors = useQuery({ queryKey: ['adminSectors'], queryFn: listAdminSectors, staleTime: 60_000 })
  const save = useMutation({
    mutationFn: (values: Partial<AdminSector>) => editing?.id ? updateAdminSector(editing.id, values) : createAdminSector(values),
    onSuccess: () => { message.success('Sector saved'); setEditing(null); qc.invalidateQueries({ queryKey: ['adminSectors'] }); qc.invalidateQueries({ queryKey: ['groupHierarchy'] }) },
  })
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <Flex justify="end"><Button type="primary" icon={<PlusOutlined />} onClick={() => setEditing({} as AdminSector)}>New sector</Button></Flex>
      <Table
        rowKey="id"
        loading={sectors.isLoading}
        dataSource={sectors.data?.items || []}
        columns={[
          { title: 'Code', dataIndex: 'code', width: 120 },
          { title: 'Name', dataIndex: 'name' },
          { title: 'Members', dataIndex: 'membership_count', width: 110 },
          { title: 'Active', dataIndex: 'is_active', width: 100, render: (active) => <Tag color={active ? 'green' : 'default'}>{active ? 'active' : 'inactive'}</Tag> },
          { title: 'Edit', width: 90, render: (_, s) => <Button size="small" onClick={() => setEditing(s)}>Edit</Button> },
        ]}
      />
      <Modal title={editing?.id ? 'Edit sector' : 'New sector'} open={!!editing} onCancel={() => setEditing(null)} footer={null}>
        <Form layout="vertical" initialValues={editing || { is_active: true }} onFinish={(values) => save.mutate(values)}>
          <Form.Item name="code" label="Code" rules={[{ required: true }]}><Input disabled={!!editing?.id} /></Form.Item>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="Description"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="is_active" label="Active" valuePropName="checked"><Switch /></Form.Item>
          <Button type="primary" htmlType="submit">Save</Button>
        </Form>
      </Modal>
    </div>
  )
}

function TicketMetadatasPanel() {
  const qc = useQueryClient()
  const [editing, setEditing] = useState<Partial<AdminTicketMetadata> | null>(null)
  const [search, setSearch] = useState('')
  const [pagination, setPagination] = useState({ current: 1, pageSize: 10 })

  const metadatas = useQuery({ 
    queryKey: ['adminTicketMetadatas', search, pagination], 
    queryFn: () => listAdminTicketMetadatas({ 
        search: search || undefined,
        limit: pagination.pageSize,
        offset: (pagination.current - 1) * pagination.pageSize
    }), 
    staleTime: 30_000 
  })
  
  const save = useMutation({
    mutationFn: upsertAdminTicketMetadata,
    onSuccess: () => { message.success('Metadata saved'); setEditing(null); qc.invalidateQueries({ queryKey: ['adminTicketMetadatas'] }) },
    onError: (err: any) => message.error(err.message || 'Save failed')
  })
  const remove = useMutation({
    mutationFn: deleteAdminTicketMetadata,
    onSuccess: () => { message.success('Metadata deleted'); qc.invalidateQueries({ queryKey: ['adminTicketMetadatas'] }) },
  })

  const columns: ColumnsType<AdminTicketMetadata> = [
    { title: 'Ticket', key: 'ticket', render: (_, m) => <Space orientation="vertical" size={0}><Typography.Text strong>{m.ticket_code}</Typography.Text><Typography.Text type="secondary" ellipsis style={{ maxWidth: 200 }}>{m.ticket_title}</Typography.Text></Space> },
    { title: 'Key', dataIndex: 'key', render: (v) => <Tag>{v}</Tag> },
    { title: 'Value', dataIndex: 'value', render: (v) => <Typography.Text code>{v}</Typography.Text> },
    { title: 'Label', dataIndex: 'label' },
    { title: 'Updated', dataIndex: 'updated_at', render: (v) => v ? fmtDateTime(v) : '-' },
    {
      title: 'Action',
      width: 150,
      render: (_, m) => (
        <Space>
          <Button size="small" onClick={() => setEditing(m)}>Edit</Button>
          <Button size="small" danger onClick={() => remove.mutate(m.id)}>Delete</Button>
        </Space>
      ),
    },
  ]

  return (
    <Panel title="Ticket metadatas" icon={<DatabaseOutlined />}>
      <Flex justify="space-between" style={{ marginBottom: 12 }}>
        <Space size={16}>
          <Input.Search placeholder="Search metadata" allowClear onSearch={setSearch} style={{ maxWidth: 360 }} />
          <Statistic value={metadatas.data?.total || 0} suffix="entries" valueStyle={{ fontSize: 16 }} />
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setEditing({})}>New metadata</Button>
      </Flex>
      <Table 
        rowKey="id" 
        loading={metadatas.isLoading} 
        columns={columns} 
        dataSource={metadatas.data?.items || []} 
        pagination={{ 
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: metadatas.data?.total || 0,
            showSizeChanger: true,
            showTotal: (total) => `Total ${total} items`
        }} 
        onChange={(p) => setPagination({ current: p.current || 1, pageSize: p.pageSize || 10 })}
      />
      <Modal title="Ticket metadata" open={!!editing} onCancel={() => setEditing(null)} footer={null}>
         <Form layout="vertical" initialValues={editing || {}} onFinish={(v) => save.mutate(v)}>
             <Form.Item name="ticket_code" label="Ticket code" rules={[{ required: !editing?.id }]}><Input disabled={!!editing?.id} placeholder="e.g. TK-000001" /></Form.Item>
             <Form.Item name="key" label="Key" rules={[{ required: !editing?.id }]}><Input disabled={!!editing?.id} /></Form.Item>
             <Form.Item name="value" label="Value" rules={[{ required: true }]}><Input /></Form.Item>
             <Form.Item name="label" label="Label"><Input /></Form.Item>
             <Button type="primary" htmlType="submit">Save</Button>
         </Form>
      </Modal>
    </Panel>
  )
}

function SystemSettingsPanel() {
  const qc = useQueryClient()
  const settings = useQuery({ queryKey: ['adminSystemSettings'], queryFn: listSystemSettings, staleTime: 60_000 })
  const [editing, setEditing] = useState<SystemSetting | null>(null)

  const save = useMutation({
    mutationFn: (values: any) => {
        const payload = { 
            ...editing, 
            ...values, 
            value: typeof values.value === 'string' ? JSON.parse(values.value) : values.value 
        }
        return upsertSystemSetting(payload)
    },
    onSuccess: () => {
      message.success('Setting saved')
      setEditing(null)
      qc.invalidateQueries({ queryKey: ['adminSystemSettings'] })
    },
    onError: (err: any) => message.error(err.message || 'Save failed')
  })

  const columns: ColumnsType<SystemSetting> = [
    { title: 'Setting Key', dataIndex: 'key', width: 250 },
    { title: 'Value', dataIndex: 'value', render: (v) => <Typography.Text code>{JSON.stringify(v)}</Typography.Text> },
    { title: 'Description', dataIndex: 'description' },
    { title: 'Last Updated', dataIndex: 'updated_at', render: (v) => v ? fmtDateTime(v) : '-' },
    {
      title: 'Action',
      width: 100,
      render: (_, row) => <Button size="small" onClick={() => setEditing(row)}>Edit</Button>,
    },
  ]

  return (
    <Panel title="Auto-Pilot & System Settings" icon={<SettingOutlined />}>
      <Table
        rowKey="key"
        size="small"
        loading={settings.isLoading}
        dataSource={settings.data?.items || []}
        pagination={false}
        columns={columns}
      />
      <Modal
        title="Edit System Setting"
        open={!!editing}
        onCancel={() => setEditing(null)}
        footer={null}
        destroyOnHide
      >
        <Form
          layout="vertical"
          initialValues={editing ? { ...editing, value: JSON.stringify(editing.value, null, 2) } : {}}
          onFinish={(values) => save.mutate(values)}
        >
          <Form.Item name="key" label="Key"><Input disabled /></Form.Item>
          <Form.Item name="value" label="Value (JSON)" rules={[{ required: true }]}>
            <Input.TextArea rows={6} placeholder='{"max": 5}' />
          </Form.Item>
          <Form.Item name="description" label="Description"><Input.TextArea rows={2} /></Form.Item>
          <Button type="primary" htmlType="submit" loading={save.isPending}>Save</Button>
        </Form>
      </Modal>
    </Panel>
  )
}

function ConfigTab() {
  const qc = useQueryClient()
  const [editing, setEditing] = useState<AdminMetadataKey | null>(null)
  const keys = useQuery({ queryKey: ['adminMetadataKeys'], queryFn: listAdminMetadataKeys, staleTime: 60_000 })
  const save = useMutation({
    mutationFn: (values: AdminMetadataKey) => upsertAdminMetadataKey({ ...values, options: typeof values.options === 'string' ? String(values.options).split(',').map((v) => v.trim()).filter(Boolean) : values.options }),
    onSuccess: () => { message.success('Metadata key saved'); setEditing(null); qc.invalidateQueries({ queryKey: ['adminMetadataKeys'] }) },
  })
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <SystemSettingsPanel />
      <Panel title="Metadata catalogue" icon={<DatabaseOutlined />}>
        <Flex justify="end" style={{ marginBottom: 12 }}><Button type="primary" icon={<PlusOutlined />} onClick={() => setEditing({ key: '', label: '', value_type: 'string', options: [], is_active: true })}>New metadata key</Button></Flex>
        <Table
          rowKey="key"
          loading={keys.isLoading}
          dataSource={keys.data?.items || []}
          pagination={{ pageSize: 6 }}
          columns={[
            { title: 'Key', dataIndex: 'key' },
            { title: 'Label', dataIndex: 'label' },
            { title: 'Type', dataIndex: 'value_type', width: 110 },
            { title: 'Options', dataIndex: 'options', render: (options: string[]) => <Space wrap>{options?.map((o) => <Tag key={o}>{o}</Tag>)}</Space> },
            { title: 'Active', dataIndex: 'is_active', width: 100, render: (active) => <Tag color={active ? 'green' : 'default'}>{active ? 'active' : 'inactive'}</Tag> },
            { title: 'Edit', width: 90, render: (_, row) => <Button size="small" onClick={() => setEditing(row)}>Edit</Button> },
          ]}
        />
      </Panel>
      <TicketMetadatasPanel />
      <WidgetCataloguePanel />
      <Modal title="Metadata key" open={!!editing} onCancel={() => setEditing(null)} footer={null}>
        <Form layout="vertical" initialValues={editing ? { ...editing, options: editing.options?.join(', ') } : undefined} onFinish={(values) => save.mutate(values)}>
          <Form.Item name="key" label="Key" rules={[{ required: true }]}><Input disabled={!!editing?.key} /></Form.Item>
          <Form.Item name="label" label="Label" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="value_type" label="Value type" rules={[{ required: true }]}>
            <Select options={[{ value: 'string', label: 'string' }, { value: 'enum', label: 'enum' }]} />
          </Form.Item>
          <Form.Item name="options" label="Enum options (comma separated)"><Input placeholder="e.g. low, medium, high" /></Form.Item>
          <Form.Item name="description" label="Description"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="is_active" label="Active" valuePropName="checked"><Switch /></Form.Item>
          <Button type="primary" htmlType="submit">Save</Button>
        </Form>
      </Modal>
    </div>
  )
}

function SystemTab() {
  const overview = useQuery({ queryKey: ['adminOverview'], queryFn: getAdminOverview, staleTime: 30_000 })
  const hardening = [
    { key: 'hot_path_indexes', label: 'Hot-path indexes migration', status: 'ready', detail: '0007_phase8_hardening_indexes' },
  ]
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} md={12}>
        <Panel title="System health" icon={<DatabaseOutlined />}>
          <MetricPanel values={overview.data?.system || {}} />
        </Panel>
      </Col>
      <Col xs={24} md={12}>
        <Panel title="Infrastructure posture" icon={<SafetyCertificateOutlined />}>
          <List
            size="small"
            dataSource={hardening}
            renderItem={(item) => (
              <List.Item extra={<Tag color="green">{item.status}</Tag>}>
                <List.Item.Meta title={item.label} description={item.detail} />
              </List.Item>
            )}
          />
        </Panel>
      </Col>
      <Col xs={24}>
        <Panel title="SLA posture" icon={<SafetyCertificateOutlined />}>
          <MetricPanel values={{ breached: overview.data?.sla.breached, due_24h: overview.data?.sla.due_24h }} />
        </Panel>
      </Col>
    </Row>
  )
}

export function AdminPage() {
  const overview = useQuery({ queryKey: ['adminOverview'], queryFn: getAdminOverview, staleTime: 30_000 })
  if (overview.isLoading) return <div style={{ padding: 100, textAlign: 'center' }}><Spin size="large" /></div>

  return (
    <div style={{ padding: 24 }}>
      <Typography.Title level={2}>Administration</Typography.Title>
      <Tabs
        defaultActiveKey="users"
        items={[
          { key: 'users', label: <Space><TeamOutlined />Users & roles</Space>, children: <UsersTab /> },
          { key: 'sectors', label: <Space><ApartmentOutlined />Sectors & groups</Space>, children: <SectorsTab /> },
          { key: 'config', label: <Space><DatabaseOutlined />Configuration</Space>, children: <ConfigTab /> },
          { key: 'system', label: <Space><SafetyCertificateOutlined />System</Space>, children: <SystemTab /> },
        ]}
      />
    </div>
  )
}
