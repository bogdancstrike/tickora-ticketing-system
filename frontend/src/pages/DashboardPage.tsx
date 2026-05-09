import { useMemo, useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Button, Card, Col, Empty, Flex, Form, Input, List, Modal, Row, Select, Space,
  Spin, Statistic, Table, Tag, Typography, message, theme as antTheme, Avatar,
} from 'antd'
import {
  AppstoreAddOutlined, AppstoreOutlined, DeleteOutlined, EditOutlined, PlusOutlined,
  ReloadOutlined, SaveOutlined, SettingOutlined, UserOutlined, WarningOutlined,
  ClockCircleOutlined, AuditOutlined, UnorderedListOutlined, CheckCircleOutlined,
  SendOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import { Responsive, WidthProvider } from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'

import {
  createDashboard, deleteDashboard, deleteWidget, getDashboard,
  listDashboards, updateDashboard, upsertWidget,
  listTickets, getMonitorOverview, listAudit,
  type CustomDashboardDto, type DashboardWidgetDto, type TicketDto,
} from '@/api/tickets'
import { useSessionStore } from '@/stores/sessionStore'
import { StatusTag } from '@/components/common/StatusTag'
import { PriorityTag } from '@/components/common/PriorityTag'
import { fmtDateTime } from '@/components/common/format'
import { useNavigate } from 'react-router-dom'

const ResponsiveGridLayout = WidthProvider(Responsive)

// ── Widget Implementations ──────────────────────────────────────────────────

function TicketListWidget({ config }: { config: any }) {
  const navigate = useNavigate()
  const { data, isLoading } = useQuery({
    queryKey: ['widgetTickets', config],
    queryFn: () => listTickets(config),
    staleTime: 30_000,
  })

  if (isLoading) return <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>

  return (
    <List
      size="small"
      dataSource={(data?.items || []).slice(0, 15)}
      locale={{ emptyText: <Empty description="No tickets" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
      renderItem={(t: TicketDto) => (
        <List.Item 
          style={{ padding: '8px 12px', cursor: 'pointer' }}
          onClick={() => navigate(`/tickets/${t.id}`)}
          className="tickora-row-clickable"
        >
          <div style={{ display: 'grid', gap: 2, width: '100%' }}>
            <Flex justify="space-between" align="center">
              <Typography.Text strong ellipsis style={{ fontSize: 13 }}>{t.title || t.ticket_code}</Typography.Text>
              <StatusTag status={t.status} />
            </Flex>
            <Space size={4} style={{ fontSize: 11 }}>
              <PriorityTag priority={t.priority} />
              <Typography.Text type="secondary">{t.ticket_code}</Typography.Text>
            </Space>
          </div>
        </List.Item>
      )}
    />
  )
}

function KpiWidget({ config }: { config: any }) {
  const { data } = useQuery({
    queryKey: ['monitorOverview'],
    queryFn: getMonitorOverview,
    staleTime: 60_000,
  })
  
  const val = useMemo(() => {
    if (!data) return '-'
    if (config.path === 'personal.kpis.assigned_active') return data.personal.kpis.assigned_active
    if (config.path === 'personal.beneficiary_kpis.active') return data.personal.beneficiary_kpis.active
    if (config.path === 'global.kpis.total_tickets') return data.global?.kpis.total_tickets
    if (config.path === 'global.kpis.sla_breached') return data.global?.kpis.sla_breached
    if (config.path === 'distributor.kpis.pending_review') return data.distributor?.kpis.pending_review
    return '-'
  }, [data, config.path])

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', padding: 12 }}>
      <Statistic 
        title={config.label || 'Metric'} 
        value={val} 
        valueStyle={{ color: config.color || undefined, fontWeight: 700 }}
        prefix={config.icon === 'warning' ? <WarningOutlined /> : undefined}
      />
    </div>
  )
}

function AuditWidget() {
  const { data, isLoading } = useQuery({
    queryKey: ['globalAuditWidget'],
    queryFn: () => listAudit({ limit: 10 }),
    staleTime: 30_000,
  })

  if (isLoading) return <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>

  return (
    <List
      size="small"
      dataSource={(data?.items || []).slice(0, 10)}
      renderItem={(a: any) => (
        <List.Item style={{ padding: '8px 12px', fontSize: 12 }}>
          <List.Item.Meta
            avatar={<Avatar size="small" icon={<UserOutlined />} />}
            title={<Typography.Text style={{ fontSize: 12 }}><b>{a.actor_username}</b> {a.action.replace(/_/g, ' ')}</Typography.Text>}
            description={<Typography.Text type="secondary" style={{ fontSize: 11 }}>{fmtDateTime(a.created_at)}</Typography.Text>}
          />
        </List.Item>
      )}
    />
  )
}

function ProfileWidget() {
  const user = useSessionStore(s => s.user)
  const navigate = useNavigate()
  if (!user) return null
  return (
    <div style={{ padding: 16, textAlign: 'center', height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
      <Avatar size={64} icon={<UserOutlined />} style={{ margin: '0 auto 12px', background: '#1677ff' }} />
      <Typography.Title level={5} style={{ margin: 0 }}>{user.username}</Typography.Title>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>{user.email}</Typography.Text>
      <div style={{ marginTop: 12 }}>
        <Button size="small" type="link" onClick={() => navigate('/profile')}>View Profile</Button>
      </div>
    </div>
  )
}

function ShortcutsWidget() {
  const navigate = useNavigate()
  return (
    <div style={{ padding: 16, display: 'grid', gap: 8 }}>
      <Button block icon={<PlusOutlined />} onClick={() => navigate('/create')}>Create Ticket</Button>
      <Button block icon={<UnorderedListOutlined />} onClick={() => navigate('/tickets')}>View Queue</Button>
      <Button block icon={<SendOutlined />} onClick={() => navigate('/monitor')}>Monitor</Button>
    </div>
  )
}

function WidgetRenderer({ widget }: { widget: DashboardWidgetDto }) {
  if (widget.type === 'ticket_list') return <TicketListWidget config={widget.config} />
  if (widget.type === 'monitor_kpi') return <KpiWidget config={widget.config} />
  if (widget.type === 'audit_stream') return <AuditWidget />
  if (widget.type === 'profile_card') return <ProfileWidget />
  if (widget.type === 'shortcuts') return <ShortcutsWidget />

  return <Empty description="Unknown widget type" image={Empty.PRESENTED_IMAGE_SIMPLE} />
}

// ── Dashboard Detail ────────────────────────────────────────────────────────

function DashboardDetail({ dashboardId, onBack }: { dashboardId: string, onBack: () => void }) {
  const { token } = antTheme.useToken()
  const qc = useQueryClient()
  const user = useSessionStore(s => s.user)
  const [editingTitle, setEditingTitle] = useState(false)
  const [isAddingWidget, setIsAddingWidget] = useState(false)
  const [form] = Form.useForm()
  
  const { data: dashboard, isLoading } = useQuery({
    queryKey: ['customDashboard', dashboardId],
    queryFn: () => getDashboard(dashboardId),
  })

  const saveLayout = useMutation({
    mutationFn: async (layout: any[]) => {
      // Filter only widgets that actually moved/resized to reduce API noise
      for (const item of layout) {
        const w = dashboard?.widgets?.find(w => w.id === item.i)
        if (w && (w.x !== item.x || w.y !== item.y || w.w !== item.w || w.h !== item.h)) {
            await upsertWidget(dashboardId, { id: w.id, x: item.x, y: item.y, w: item.w, h: item.h })
        }
      }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['customDashboard', dashboardId] })
  })

  const addWidget = useMutation({
    mutationFn: (values: any) => {
        let config = {}
        if (values.type === 'ticket_list') {
            if (values.preset === 'assigned') config = { assignee_user_id: user?.id, status: 'in_progress' }
            if (values.preset === 'sector') config = { current_sector_code: user?.sectors?.[0]?.sectorCode, status: 'assigned_to_sector' }
            if (values.preset === 'pending') config = { status: 'pending' }
        }
        if (values.type === 'monitor_kpi') {
            if (values.preset === 'breached') config = { path: 'global.kpis.sla_breached', label: 'Breached', color: '#f5222d', icon: 'warning' }
            if (values.preset === 'assigned') config = { path: 'personal.kpis.assigned_active', label: 'My Active' }
            if (values.preset === 'pending') config = { path: 'distributor.kpis.pending_review', label: 'Triage Queue' }
        }
        return upsertWidget(dashboardId, { ...values, config, x: 0, y: 0, w: 4, h: 6 })
    },
    onSuccess: () => {
      setIsAddingWidget(false)
      form.resetFields()
      qc.invalidateQueries({ queryKey: ['customDashboard', dashboardId] })
      message.success('Widget added')
    }
  })

  const removeWidget = useMutation({
    mutationFn: (widgetId: string) => deleteWidget(dashboardId, widgetId),
    onSuccess: () => {
        qc.invalidateQueries({ queryKey: ['customDashboard', dashboardId] })
        message.success('Widget removed')
    }
  })

  const rename = useMutation({
    mutationFn: (title: string) => updateDashboard(dashboardId, { title }),
    onSuccess: () => { setEditingTitle(false); qc.invalidateQueries({ queryKey: ['customDashboard', dashboardId] }) }
  })

  if (isLoading) return <div style={{ padding: 100, textAlign: 'center' }}><Spin size="large" /></div>
  if (!dashboard) return <Alert type="error" message="Dashboard not found" />

  const layouts = {
    lg: (dashboard.widgets || []).map(w => ({ i: w.id, x: w.x, y: w.y, w: w.w, h: w.h }))
  }

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <Flex justify="space-between" align="center">
        <Space>
          <Button type="link" onClick={onBack} style={{ padding: 0 }}>← Back</Button>
          {editingTitle ? (
             <Input defaultValue={dashboard.title} autoFocus onPressEnter={(e) => rename.mutate(e.currentTarget.value)} onBlur={() => setEditingTitle(false)} />
          ) : (
             <Typography.Title level={4} style={{ margin: 0 }} onClick={() => setEditingTitle(true)}>
               {dashboard.title} <EditOutlined style={{ fontSize: 14, color: token.colorTextDescription }} />
             </Typography.Title>
          )}
        </Space>
        <Space>
           <Button icon={<AppstoreAddOutlined />} type="primary" onClick={() => setIsAddingWidget(true)}>Add Widget</Button>
           <Button icon={<ReloadOutlined />} onClick={() => qc.invalidateQueries({ queryKey: ['customDashboard', dashboardId] })} />
        </Space>
      </Flex>

      <div style={{ background: 'rgba(0,0,0,0.02)', borderRadius: 12, minHeight: 'calc(100vh - 200px)', padding: 8 }}>
        <ResponsiveGridLayout
          key={dashboard.widgets?.length} // CRITICAL: Forces rebuild when widget count changes to fix "no-refresh" bug
          className="layout"
          layouts={layouts}
          breakpoints={{ lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 }}
          cols={{ lg: 12, md: 10, sm: 6, xs: 4, xxs: 2 }}
          rowHeight={30}
          draggableHandle=".widget-drag-handle"
          onLayoutChange={(currentLayout) => saveLayout.mutate(currentLayout)}
        >
          {(dashboard.widgets || []).map((w) => (
            <div key={w.id} style={{ background: token.colorBgContainer, borderRadius: 8, border: `1px solid ${token.colorBorderSecondary}`, overflow: 'hidden', display: 'flex', flexDirection: 'column', boxShadow: token.boxShadowTertiary }}>
              <div className="widget-drag-handle" style={{ 
                padding: '4px 12px', background: token.colorFillTertiary, cursor: 'move',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center'
              }}>
                <Typography.Text strong style={{ fontSize: 12 }}>{w.title || w.type}</Typography.Text>
                <Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={() => removeWidget.mutate(w.id)} />
              </div>
              <div style={{ flex: 1, overflow: 'auto' }}>
                <WidgetRenderer widget={w} />
              </div>
            </div>
          ))}
        </ResponsiveGridLayout>
        {(dashboard.widgets || []).length === 0 && (
           <Empty style={{ marginTop: 100 }} description="This dashboard has no widgets yet." />
        )}
      </div>

      <Modal title="Add Widget" open={isAddingWidget} onCancel={() => setIsAddingWidget(false)} onOk={() => form.submit()}>
        <Form form={form} layout="vertical" onFinish={addWidget.mutate} initialValues={{ type: 'ticket_list', preset: 'assigned' }}>
          <Form.Item name="title" label="Widget Title" rules={[{ required: true }]}>
            <Input placeholder="E.g., My Active Tickets" />
          </Form.Item>
          <Form.Item name="type" label="Widget Type" rules={[{ required: true }]}>
            <Select options={[
              { value: 'ticket_list', label: 'Ticket List' },
              { value: 'monitor_kpi', label: 'KPI Stat' },
              { value: 'audit_stream', label: 'Audit Pulse' },
              { value: 'profile_card', label: 'Profile Card' },
              { value: 'shortcuts', label: 'Quick Links' },
            ]} />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.type !== cur.type}>
            {({ getFieldValue }) => {
              const type = getFieldValue('type')
              if (['profile_card', 'shortcuts', 'audit_stream'].includes(type)) return null
              return (
                <Form.Item name="preset" label="Data Preset" rules={[{ required: true }]}>
                  <Select options={
                    type === 'ticket_list' ? [
                      { value: 'assigned', label: 'Tickets assigned to me' },
                      { value: 'sector', label: 'Sector unassigned queue' },
                      { value: 'pending', label: 'New/Triage queue (Distributor)' },
                    ] : [
                      { value: 'breached', label: 'SLA Breaches (Global)' },
                      { value: 'assigned', label: 'My active count' },
                      { value: 'pending', label: 'Triage count' },
                    ]
                  } />
                </Form.Item>
              )
            }}
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

// ── Dashboard List ──────────────────────────────────────────────────────────

export function DashboardPage() {
  const { token } = antTheme.useToken()
  const [activeDashboardId, setActiveDashboardId] = useState<string | null>(null)
  const [isCreating, setIsAdding] = useState(false)
  const [form] = Form.useForm()
  const qc = useQueryClient()

  const list = useQuery({
    queryKey: ['customDashboards'],
    queryFn: listDashboards,
  })

  const create = useMutation({
    mutationFn: createDashboard,
    onSuccess: (d) => {
      setIsAdding(false)
      form.resetFields()
      qc.invalidateQueries({ queryKey: ['customDashboards'] })
      setActiveDashboardId(d.id)
    }
  })

  const del = useMutation({
    mutationFn: deleteDashboard,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['customDashboards'] })
  })

  if (activeDashboardId) {
    return <div style={{ padding: 24 }}><DashboardDetail dashboardId={activeDashboardId} onBack={() => setActiveDashboardId(null)} /></div>
  }

  return (
    <div style={{ padding: 24, display: 'grid', gap: 24 }}>
      <Flex justify="space-between" align="center">
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>Dashboards</Typography.Title>
          <Typography.Text type="secondary">Customizable operational views with live widgets</Typography.Text>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsAdding(true)}>New Dashboard</Button>
      </Flex>

      <Row gutter={[16, 16]}>
        {(list.data?.items || []).map((d) => (
          <Col key={d.id} xs={24} sm={12} lg={8} xl={6}>
            <Card
              hoverable
              onClick={() => setActiveDashboardId(d.id)}
              actions={[
                <DeleteOutlined key="del" onClick={(e) => { e.stopPropagation(); del.mutate(d.id) }} />
              ]}
            >
              <Card.Meta 
                avatar={<AppstoreOutlined style={{ fontSize: 24, color: token.colorPrimary }} />}
                title={d.title} 
                description={`Created ${new Date(d.created_at).toLocaleDateString()}`}
              />
            </Card>
          </Col>
        ))}
        {list.data?.items.length === 0 && !list.isLoading && (
          <Col xs={24}>
            <Empty description="No custom dashboards yet." />
          </Col>
        )}
      </Row>

      <Modal title="New Dashboard" open={isCreating} onCancel={() => setIsAdding(false)} onOk={() => form.submit()}>
        <Form form={form} layout="vertical" onFinish={(v) => create.mutate(v)}>
          <Form.Item name="title" label="Title" rules={[{ required: true, min: 2 }]}>
            <Input placeholder="E.g., Morning Review" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
