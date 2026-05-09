import { useMemo, useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Button, Card, Col, Empty, Flex, Form, Input, List, Modal, Row, Select, Space,
  Spin, Statistic, Table, Tag, Typography, message, theme as antTheme,
} from 'antd'
import {
  AppstoreAddOutlined, AppstoreOutlined, DeleteOutlined, EditOutlined, PlusOutlined,
  ReloadOutlined, SaveOutlined, SettingOutlined,
} from '@ant-design/icons'
import { Responsive, WidthProvider } from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'

import {
  createDashboard, deleteDashboard, deleteWidget, getDashboard,
  listDashboards, updateDashboard, upsertWidget,
  type CustomDashboardDto, type DashboardWidgetDto,
} from '@/api/tickets'
import { useSessionStore } from '@/stores/sessionStore'

// Import widgets components or implement inline-minimal ones
import { MonitorPage } from './MonitorPage'

const ResponsiveGridLayout = WidthProvider(Responsive)

function WidgetRenderer({ widget }: { widget: DashboardWidgetDto }) {
  const { token } = antTheme.useToken()
  
  // Minimal widget previews
  if (widget.type === 'ticket_list') {
    return (
      <div style={{ padding: 12 }}>
        <Typography.Text type="secondary">Live ticket queue preview...</Typography.Text>
        {/* Real implementation would fetch listTickets with widget.config params */}
      </div>
    )
  }
  
  if (widget.type === 'monitor_kpi') {
    return (
      <div style={{ padding: 12, display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
         <Statistic title={widget.config.label || 'KPI'} value={42} />
      </div>
    )
  }

  return <Empty description="Unknown widget type" image={Empty.PRESENTED_IMAGE_SIMPLE} />
}

function DashboardDetail({ dashboardId, onBack }: { dashboardId: string, onBack: () => void }) {
  const { token } = antTheme.useToken()
  const qc = useQueryClient()
  const [editingTitle, setEditingTitle] = useState(false)
  const [isAddingWidget, setIsAddingWidget] = useState(false)
  const [form] = Form.useForm()
  
  const { data: dashboard, isLoading } = useQuery({
    queryKey: ['customDashboard', dashboardId],
    queryFn: () => getDashboard(dashboardId),
  })

  const saveLayout = useMutation({
    mutationFn: async (layout: any[]) => {
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
    mutationFn: (values: any) => upsertWidget(dashboardId, values),
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
        <Form form={form} layout="vertical" onFinish={(v) => addWidget.mutate({ ...v, x: 0, y: 0, w: 4, h: 6 })} initialValues={{ type: 'ticket_list' }}>
          <Form.Item name="title" label="Widget Title" rules={[{ required: true }]}>
            <Input placeholder="E.g., My Active Tickets" />
          </Form.Item>
          <Form.Item name="type" label="Widget Type" rules={[{ required: true }]}>
            <Select options={[
              { value: 'ticket_list', label: 'Ticket List' },
              { value: 'monitor_kpi', label: 'KPI Stat' },
            ]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

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
