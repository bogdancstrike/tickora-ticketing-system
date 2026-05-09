import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import ReactECharts from 'echarts-for-react'
import {
  Alert, Button, Col, Empty, Flex, Form, Input, List, Modal, Row, Select, Space,
  Statistic, Switch, Table, Tabs, Tag, Tree, Typography, message, theme as antTheme,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  ApartmentOutlined, BarChartOutlined, DatabaseOutlined, PlusOutlined, ReloadOutlined,
  SafetyCertificateOutlined, TeamOutlined,
} from '@ant-design/icons'
import {
  ADMIN_ROLES, createAdminSector, createAdminSlaPolicy, getAdminOverview,
  getGroupHierarchy, grantMembership, listAdminMemberships, listAdminMetadataKeys,
  listAdminSectors, listAdminSlaPolicies, listAdminUsers, revokeMembership,
  updateAdminSector, updateAdminSlaPolicy, updateAdminUser, upsertAdminMetadataKey,
  type AdminMembership, type AdminMetadataKey, type AdminSector, type AdminSlaPolicy,
  type AdminUser,
} from '@/api/admin'
import type { DashboardBreakdown } from '@/api/tickets'

function labelize(value: string) {
  return value.split('_').join(' ')
}

function MetricPanel({ values }: { values: Record<string, number | null | undefined> }) {
  const { token } = antTheme.useToken()
  return (
    <Row gutter={[12, 12]}>
      {Object.entries(values).map(([key, value]) => (
        <Col key={key} xs={12} md={8} xl={6}>
          <div style={{ border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8, padding: 14, minHeight: 92 }}>
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
    <div style={{ border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8, padding: 16, minHeight: 220 }}>
      <Space align="center" style={{ marginBottom: 12 }}>
        {icon}
        <Typography.Title level={5} style={{ margin: 0 }}>{title}</Typography.Title>
      </Space>
      {children}
    </div>
  )
}

function BarChart({ data, title, color = '#1677ff' }: { data: DashboardBreakdown[]; title: string; color?: string }) {
  if (!data?.length) return <Empty description="No data" image={Empty.PRESENTED_IMAGE_SIMPLE} />
  const option = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '8%', containLabel: true },
    xAxis: { type: 'category', data: data.map((i) => labelize(i.key)), axisLabel: { interval: 0, rotate: data.length > 5 ? 24 : 0 } },
    yAxis: { type: 'value' },
    series: [{ name: title, type: 'bar', data: data.map((i) => i.count), itemStyle: { color, borderRadius: [4, 4, 0, 0] } }],
  }
  return <ReactECharts option={option} style={{ height: 260 }} />
}

function OverviewTab() {
  const overview = useQuery({ queryKey: ['adminOverview'], queryFn: getAdminOverview, staleTime: 30_000 })
  const sectorBreakdown = useMemo(
    () => (overview.data?.by_sector || []).map((s) => ({ key: s.sector_code, count: s.count })),
    [overview.data?.by_sector],
  )
  if (overview.error) return <Alert type="error" message={overview.error.message} showIcon />
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <Flex justify="end"><Button icon={<ReloadOutlined />} onClick={() => overview.refetch()} /></Flex>
      <MetricPanel values={overview.data?.kpis || {}} />
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={8}><Panel title="Ticket status" icon={<BarChartOutlined />}><BarChart data={overview.data?.by_status || []} title="Status" /></Panel></Col>
        <Col xs={24} xl={8}><Panel title="Priority pressure" icon={<SafetyCertificateOutlined />}><BarChart data={overview.data?.by_priority || []} title="Priority" color="#fa8c16" /></Panel></Col>
        <Col xs={24} xl={8}><Panel title="Sector load" icon={<ApartmentOutlined />}><BarChart data={sectorBreakdown} title="Sector" color="#13a8a8" /></Panel></Col>
        <Col xs={24} xl={12}>
          <Panel title="Queues">
            <MetricPanel values={overview.data?.queues || {}} />
          </Panel>
        </Col>
        <Col xs={24} xl={12}>
          <Panel title="Recent audit">
            <List
              size="small"
              dataSource={overview.data?.recent_audit || []}
              locale={{ emptyText: <Empty description="No audit events" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={<Space><Tag>{item.action}</Tag><Typography.Text>{item.actor_username || 'system'}</Typography.Text></Space>}
                    description={`${item.entity_type}${item.ticket_id ? ` · ${item.ticket_id}` : ''}`}
                  />
                </List.Item>
              )}
            />
          </Panel>
        </Col>
      </Row>
    </div>
  )
}

function UsersTab() {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<AdminUser | null>(null)
  const users = useQuery({ queryKey: ['adminUsers', search], queryFn: () => listAdminUsers(search), staleTime: 30_000 })
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
    { title: 'User', key: 'user', render: (_, u) => <Space direction="vertical" size={0}><Typography.Text strong>{u.username || u.email || u.id}</Typography.Text><Typography.Text type="secondary">{u.email}</Typography.Text></Space> },
    { title: 'Roles', dataIndex: 'roles', render: (roles: string[]) => <Space wrap>{roles.map((r) => <Tag key={r}>{r.replace('tickora_', '')}</Tag>)}</Space> },
    { title: 'Groups', dataIndex: 'memberships', render: (memberships: AdminMembership[]) => <Space wrap>{memberships.map((m) => <Tag key={m.id} color={m.role === 'chief' ? 'gold' : 'blue'}>{m.sector_code} · {m.role}</Tag>)}</Space> },
    { title: 'Active', dataIndex: 'is_active', width: 90, render: (active, u) => <Switch checked={active} onChange={(checked) => update.mutate({ id: u.id, is_active: checked })} /> },
    { title: 'Edit', width: 90, render: (_, u) => <Button size="small" onClick={() => setSelected(u)}>Manage</Button> },
  ]
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <Flex justify="space-between" wrap="wrap" gap={12}>
        <Input.Search placeholder="Search users" allowClear onSearch={setSearch} style={{ maxWidth: 360 }} />
        <Button icon={<ReloadOutlined />} onClick={() => users.refetch()} />
      </Flex>
      <Table rowKey="id" loading={users.isLoading} columns={columns} dataSource={users.data?.items || []} pagination={{ pageSize: 10 }} />
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
          <Button type="primary" htmlType="submit" loading={save.isPending}>Save</Button>
        </Form>
      </Modal>
    </div>
  )
}

function GroupsTab() {
  const [sectorCode, setSectorCode] = useState<string | undefined>()
  const sectors = useQuery({ queryKey: ['adminSectors'], queryFn: listAdminSectors, staleTime: 60_000 })
  const memberships = useQuery({ queryKey: ['adminMemberships', sectorCode], queryFn: () => listAdminMemberships(sectorCode), staleTime: 30_000 })
  const tree = useQuery({ queryKey: ['groupHierarchy'], queryFn: getGroupHierarchy, staleTime: 30_000 })
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={10}>
        <Panel title="Group hierarchy" icon={<ApartmentOutlined />}>
          <Tree defaultExpandAll treeData={tree.data ? [tree.data] : []} />
        </Panel>
      </Col>
      <Col xs={24} xl={14}>
        <Panel title="Membership ledger" icon={<TeamOutlined />}>
          <Select
            allowClear
            placeholder="Filter sector"
            value={sectorCode}
            onChange={setSectorCode}
            style={{ width: 260, marginBottom: 12 }}
            options={(sectors.data?.items || []).map((s) => ({ value: s.code, label: `${s.code} · ${s.name}` }))}
          />
          <Table
            rowKey="id"
            loading={memberships.isLoading}
            dataSource={memberships.data?.items || []}
            pagination={{ pageSize: 8 }}
            columns={[
              { title: 'User', render: (_, m: AdminMembership) => m.username || m.email || m.user_id },
              { title: 'Sector', dataIndex: 'sector_code', width: 120 },
              { title: 'Role', dataIndex: 'role', width: 120, render: (role) => <Tag color={role === 'chief' ? 'gold' : 'blue'}>{role}</Tag> },
            ]}
          />
        </Panel>
      </Col>
    </Row>
  )
}

function ConfigTab() {
  const qc = useQueryClient()
  const [editing, setEditing] = useState<AdminMetadataKey | null>(null)
  const [editingPolicy, setEditingPolicy] = useState<AdminSlaPolicy | null>(null)
  const keys = useQuery({ queryKey: ['adminMetadataKeys'], queryFn: listAdminMetadataKeys, staleTime: 60_000 })
  const policies = useQuery({ queryKey: ['adminSlaPolicies'], queryFn: listAdminSlaPolicies, staleTime: 60_000 })
  const save = useMutation({
    mutationFn: (values: AdminMetadataKey) => upsertAdminMetadataKey({ ...values, options: typeof values.options === 'string' ? String(values.options).split(',').map((v) => v.trim()).filter(Boolean) : values.options }),
    onSuccess: () => { message.success('Metadata key saved'); setEditing(null); qc.invalidateQueries({ queryKey: ['adminMetadataKeys'] }) },
  })
  const savePolicy = useMutation({
    mutationFn: (values: AdminSlaPolicy) => values.id ? updateAdminSlaPolicy(values.id, values) : createAdminSlaPolicy(values),
    onSuccess: () => { message.success('SLA policy saved'); setEditingPolicy(null); qc.invalidateQueries({ queryKey: ['adminSlaPolicies'] }); qc.invalidateQueries({ queryKey: ['adminOverview'] }) },
  })
  return (
    <div style={{ display: 'grid', gap: 16 }}>
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
      <Panel title="SLA policies" icon={<SafetyCertificateOutlined />}>
        <Flex justify="end" style={{ marginBottom: 12 }}>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setEditingPolicy({
              name: '',
              priority: 'medium',
              first_response_minutes: 60,
              resolution_minutes: 480,
              is_active: true,
            })}
          >
            New SLA policy
          </Button>
        </Flex>
        <Table
          rowKey="id"
          loading={policies.isLoading}
          dataSource={policies.data?.items || []}
          pagination={{ pageSize: 6 }}
          columns={[
            { title: 'Name', dataIndex: 'name' },
            { title: 'Priority', dataIndex: 'priority', width: 110, render: (priority) => <Tag color={priority === 'critical' ? 'red' : priority === 'high' ? 'orange' : undefined}>{priority}</Tag> },
            { title: 'Category', dataIndex: 'category', render: (value) => value || 'Any' },
            { title: 'Beneficiary', dataIndex: 'beneficiary_type', width: 120, render: (value) => value || 'Any' },
            { title: 'First response', dataIndex: 'first_response_minutes', width: 140, render: (value) => `${value} min` },
            { title: 'Resolution', dataIndex: 'resolution_minutes', width: 120, render: (value) => `${value} min` },
            { title: 'Active', dataIndex: 'is_active', width: 100, render: (active) => <Tag color={active ? 'green' : 'default'}>{active ? 'active' : 'inactive'}</Tag> },
            { title: 'Edit', width: 90, render: (_, row) => <Button size="small" onClick={() => setEditingPolicy(row)}>Edit</Button> },
          ]}
        />
      </Panel>
      <Modal title="Metadata key" open={!!editing} onCancel={() => setEditing(null)} footer={null}>
        <Form layout="vertical" initialValues={editing ? { ...editing, options: editing.options?.join(', ') } : undefined} onFinish={(values) => save.mutate(values)}>
          <Form.Item name="key" label="Key" rules={[{ required: true }]}><Input disabled={!!editing?.key} /></Form.Item>
          <Form.Item name="label" label="Label" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="value_type" label="Type"><Select options={[{ value: 'string', label: 'string' }, { value: 'enum', label: 'enum' }]} /></Form.Item>
          <Form.Item name="options" label="Options"><Input placeholder="comma-separated values" /></Form.Item>
          <Form.Item name="description" label="Description"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="is_active" label="Active" valuePropName="checked"><Switch /></Form.Item>
          <Button type="primary" htmlType="submit" loading={save.isPending}>Save</Button>
        </Form>
      </Modal>
      <Modal title="SLA policy" open={!!editingPolicy} onCancel={() => setEditingPolicy(null)} footer={null}>
        <Form layout="vertical" initialValues={editingPolicy || undefined} onFinish={(values) => savePolicy.mutate({ ...editingPolicy, ...values })}>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="priority" label="Priority" rules={[{ required: true }]}>
            <Select options={['low', 'medium', 'high', 'critical'].map((value) => ({ value, label: value }))} />
          </Form.Item>
          <Form.Item name="category" label="Category"><Input placeholder="Any category" /></Form.Item>
          <Form.Item name="beneficiary_type" label="Beneficiary type">
            <Select allowClear options={[{ value: 'internal', label: 'internal' }, { value: 'external', label: 'external' }]} />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}><Form.Item name="first_response_minutes" label="First response minutes" rules={[{ required: true }]}><Input type="number" min={1} /></Form.Item></Col>
            <Col span={12}><Form.Item name="resolution_minutes" label="Resolution minutes" rules={[{ required: true }]}><Input type="number" min={1} /></Form.Item></Col>
          </Row>
          <Form.Item name="is_active" label="Active" valuePropName="checked"><Switch /></Form.Item>
          <Button type="primary" htmlType="submit" loading={savePolicy.isPending}>Save</Button>
        </Form>
      </Modal>
    </div>
  )
}

function SystemTab() {
  const overview = useQuery({ queryKey: ['adminOverview'], queryFn: getAdminOverview, staleTime: 30_000 })
  const hardening = [
    { key: 'hot_path_indexes', label: 'Hot-path indexes migration', status: 'ready', detail: '0007_phase8_hardening_indexes' },
    { key: 'seed_sql', label: 'Seed SQL artifact', status: 'ready', detail: 'scripts/seed.sql' },
    { key: 'audit_review', label: 'Audit events today', status: `${overview.data?.kpis.audit_events_today ?? 0}`, detail: 'Global immutable audit ledger' },
    { key: 'sla_breaches', label: 'SLA breaches', status: `${overview.data?.sla.breached ?? 0}`, detail: 'Operational breach queue' },
    { key: 'unread_notifications', label: 'Unread notifications', status: `${overview.data?.kpis.unread_notifications ?? 0}`, detail: 'In-app notification backlog' },
  ]
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={12}>
        <Panel title="System counters" icon={<DatabaseOutlined />}>
          <MetricPanel values={overview.data?.system || {}} />
        </Panel>
      </Col>
      <Col xs={24} xl={12}>
        <Panel title="Hardening checklist" icon={<SafetyCertificateOutlined />}>
          <Table
            rowKey="key"
            size="small"
            pagination={false}
            dataSource={hardening}
            columns={[
              { title: 'Item', dataIndex: 'label' },
              { title: 'Status', dataIndex: 'status', width: 130, render: (value) => <Tag color={value === 'ready' ? 'green' : undefined}>{value}</Tag> },
              { title: 'Detail', dataIndex: 'detail' },
            ]}
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
  return (
    <div style={{ padding: 24, display: 'grid', gap: 16 }}>
      <div>
        <Typography.Title level={3} style={{ margin: 0 }}>Admin</Typography.Title>
        <Typography.Text type="secondary">Operations, access control, group hierarchy, and platform configuration</Typography.Text>
      </div>
      <Tabs
        items={[
          { key: 'overview', label: <Space><BarChartOutlined />Overview</Space>, children: <OverviewTab /> },
          { key: 'users', label: <Space><TeamOutlined />Users & roles</Space>, children: <UsersTab /> },
          { key: 'sectors', label: <Space><ApartmentOutlined />Sectors</Space>, children: <SectorsTab /> },
          { key: 'groups', label: <Space><SafetyCertificateOutlined />Groups</Space>, children: <GroupsTab /> },
          { key: 'config', label: <Space><DatabaseOutlined />Configuration</Space>, children: <ConfigTab /> },
          { key: 'system', label: <Space><SafetyCertificateOutlined />System</Space>, children: <SystemTab /> },
        ]}
      />
    </div>
  )
}
