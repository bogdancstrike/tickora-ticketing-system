import { useMemo, useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import ReactECharts from 'echarts-for-react'
import {
  Alert, Button, Card, Col, Empty, Flex, Form, Input, List, Modal, Row, Select, Space,
  Spin, Statistic, Table, Tag, Typography, message, theme as antTheme, Avatar, Checkbox,
  Switch, Divider, Tooltip, Radio,
} from 'antd'
import {
  AppstoreAddOutlined, AppstoreOutlined, DeleteOutlined, EditOutlined, PlusOutlined,
  ReloadOutlined, SaveOutlined, SettingOutlined, UserOutlined, WarningOutlined,
  AuditOutlined, UnorderedListOutlined,
  SendOutlined, ThunderboltOutlined, BarChartOutlined, PieChartOutlined,
  MessageOutlined, FieldTimeOutlined, DatabaseOutlined,
  CarryOutOutlined, SmileOutlined, TeamOutlined, HistoryOutlined, LineChartOutlined,
  ClockCircleOutlined, CheckCircleOutlined, SearchOutlined, DashboardOutlined, InfoCircleOutlined,
  HourglassOutlined,
} from '@ant-design/icons'
import { Responsive, WidthProvider } from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'

import {
  createDashboard, deleteDashboard, deleteWidget, getDashboard,
  listDashboards, updateDashboard, upsertWidget, autoConfigureDashboard,
  listTickets, getMonitorOverview, listAudit, listTicketAudit,
  getMonitorSector, listComments, getTicketOptions, listAssignableUsers,
  type CustomDashboardDto, type DashboardWidgetDto, type TicketDto,
} from '@/api/tickets'
import { listAdminWidgets } from '@/api/admin'
import { useSessionStore } from '@/stores/sessionStore'
import { StatusTag, STATUS_OPTIONS } from '@/components/common/StatusTag'
import { PriorityTag, PRIORITY_OPTIONS } from '@/components/common/PriorityTag'
import { fmtDateTime } from '@/components/common/format'
import { useNavigate } from 'react-router-dom'
import { apiClient } from '@/api/client'
import { BreakdownChart, WorkloadChart } from '@/components/dashboard/DashboardCharts'

const ResponsiveGridLayout = WidthProvider(Responsive)

// ── Helpers for selection ──────────────────────────────────────────────────

function TicketSelect({ name, label, placeholder }: { name: any, label: string, placeholder?: string }) {
    const { data, isLoading } = useQuery({
        queryKey: ['recentTicketsForSelect'],
        queryFn: () => listTickets({ limit: 50, sort_by: 'created_at', sort_dir: 'desc' }),
        staleTime: 60_000,
    })

    return (
        <Form.Item name={name} label={label}>
            <Select
                showSearch
                placeholder={placeholder}
                loading={isLoading}
                optionFilterProp="label"
                options={(data?.items || []).map(t => ({
                    value: t.id,
                    label: `${t.ticket_code} · ${t.title || t.txt?.slice(0, 30)}`,
                }))}
            />
        </Form.Item>
    )
}

function SectorSelect({ name, label }: { name: any, label: string }) {
    const { data, isLoading } = useQuery({
        queryKey: ['ticketOptions'],
        queryFn: getTicketOptions,
        staleTime: 300_000,
    })

    return (
        <Form.Item name={name} label={label}>
            <Select
                showSearch
                loading={isLoading}
                optionFilterProp="label"
                options={(data?.sectors || []).map(s => ({
                    value: s.code,
                    label: `${s.code} · ${s.name}`,
                }))}
            />
        </Form.Item>
    )
}

function UserSelect({ name, label, sectorCode }: { name: any, label: string, sectorCode?: string }) {
    const { data, isLoading } = useQuery({
        queryKey: ['assignableUsers', sectorCode],
        queryFn: () => listAssignableUsers(sectorCode),
        staleTime: 60_000,
    })

    return (
        <Form.Item name={name} label={label}>
            <Select
                showSearch
                loading={isLoading}
                optionFilterProp="label"
                options={(data?.items || []).map(u => ({
                    value: u.id,
                    label: `${u.username} (${u.sector_code})`,
                }))}
            />
        </Form.Item>
    )
}

// ── Widget Implementations ──────────────────────────────────────────────────

function TicketListWidget({ config }: { config: any }) {
  const navigate = useNavigate()
  const { token } = antTheme.useToken()
  const { data, isLoading } = useQuery({
    queryKey: ['widgetTickets', config],
    queryFn: () => listTickets({
        status: config.status || undefined,
        priority: config.priority || undefined,
        assignee_user_id: config.assignee_user_id || undefined,
        current_sector_code: config.current_sector_code || undefined,
        limit: config.limit || 10,
    }),
    staleTime: 30_000,
  })

  if (isLoading) return <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>

  const items = (data?.items || []).slice(0, 20)

  return (
    <div style={{ padding: '4px 0' }}>
      {items.map((t: TicketDto) => (
        <div
          key={t.id}
          style={{ padding: '8px 12px', cursor: 'pointer', borderBottom: `1px solid ${token.colorBorderSecondary}` }}
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
        </div>
      ))}
      {items.length === 0 && (
        <div style={{ padding: 20 }}>
          <Empty description="No tickets match filters" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </div>
      )}
    </div>
  )
}

function KpiWidget({ config }: { config: any }) {
  const { data } = useQuery({
    queryKey: ['monitorOverview'],
    queryFn: () => getMonitorOverview(),
    staleTime: 60_000,
  })
  
  const val = useMemo(() => {
    if (!data) return '-'
    const p = config.path || 'personal.kpis.assigned_active'
    try {
        const parts = p.split('.')
        let current: any = data
        for (const part of parts) {
            current = current[part]
        }
        return current ?? 0
    } catch (e) {
        return '-'
    }
  }, [data, config.path])

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', padding: 12 }}>
      <Statistic 
        title={config.label || 'Metric'} 
        value={val} 
        styles={{ content: { color: config.color || undefined, fontWeight: 700 } }}
        prefix={config.icon === 'warning' ? <WarningOutlined /> : undefined}
      />
    </div>
  )
}

function AuditWidget({ config }: { config: any }) {
  const navigate = useNavigate()
  const { token } = antTheme.useToken()
  const { data, isLoading } = useQuery({
    queryKey: ['auditWidget', config],
    queryFn: () => {
        if (config.ticketId) return listTicketAudit(config.ticketId)
        return listAudit({ 
            limit: config.limit || 10, 
            action: config.action || undefined,
            actor_user_id: config.userId || undefined
        })
    },
    staleTime: 30_000,
  })

  if (isLoading) return <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>

  const items = (data?.items || []).slice(0, config.limit || 15)

  return (
    <div style={{ padding: '4px 0' }}>
      {items.map((a: any) => (
        <div 
          key={a.id}
          style={{ padding: '8px 12px', fontSize: 12, cursor: a.ticket_id ? 'pointer' : 'default', borderBottom: `1px solid ${token.colorBorderSecondary}` }}
          onClick={() => a.ticket_id && navigate(`/tickets/${a.ticket_id}`)}
          className={a.ticket_id ? 'tickora-row-clickable' : ''}
        >
          <Flex gap={12} align="start">
            <Avatar size="small" icon={<UserOutlined />} />
            <div style={{ flex: 1 }}>
              <Typography.Text style={{ fontSize: 12 }}><b>{a.actor_username}</b> {a.action.replace(/_/g, ' ')}</Typography.Text>
              <div style={{ marginTop: 4 }}>
                <Space direction="vertical" size={0}>
                   <Typography.Text type="secondary" style={{ fontSize: 11 }}>{fmtDateTime(a.created_at)}</Typography.Text>
                   {a.ticket_id && <Typography.Text type="link" style={{ fontSize: 10 }}>Ticket: {a.ticket_id.slice(0,8)}</Typography.Text>}
                </Space>
              </div>
            </div>
          </Flex>
        </div>
      ))}
      {items.length === 0 && (
        <div style={{ padding: 20 }}>
          <Empty description="No events found" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </div>
      )}
    </div>
  )
}

function RecentCommentsWidget({ config }: { config: any }) {
  const navigate = useNavigate()
  const { token } = antTheme.useToken()
  const { data, isLoading } = useQuery({
    queryKey: ['widgetComments', config.ticketId],
    queryFn: () => config.ticketId ? listComments(config.ticketId) : Promise.resolve({ items: [] }),
    enabled: !!config.ticketId
  })

  if (!config.ticketId) return <div style={{ padding: 20 }}><Empty description="Select a ticket to watch comments" /></div>
  if (isLoading) return <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>

  const items = (data?.items || []).slice(0, 10)

  return (
    <div style={{ padding: '4px 0' }}>
      {items.map((c: any) => (
        <div 
          key={c.id}
          style={{ padding: '8px 12px', cursor: 'pointer', borderBottom: `1px solid ${token.colorBorderSecondary}` }}
          onClick={() => navigate(`/tickets/${config.ticketId}`)}
          className="tickora-row-clickable"
        >
          <div style={{ display: 'grid', gap: 2 }}>
            <Typography.Text strong style={{ fontSize: 12 }}>{c.author_display || c.author_username}</Typography.Text>
            <div style={{ fontSize: 11, maxHeight: 40, overflow: 'hidden' }}>{c.body}</div>
          </div>
        </div>
      ))}
      {items.length === 0 && (
        <div style={{ padding: 20 }}>
          <Empty description="No comments yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </div>
      )}
    </div>
  )
}

function ProfileWidget({ config }: { config: any }) {
  const user = useSessionStore(s => s.user)
  const navigate = useNavigate()
  if (!user) return null
  
  const showSectors = config.showSectors !== false
  const showRoles = config.showRoles !== false

  return (
    <div style={{ padding: 16, height: '100%', overflow: 'auto' }}>
      <div style={{ textAlign: 'center', marginBottom: 16 }}>
        <Avatar size={64} icon={<UserOutlined />} style={{ margin: '0 auto 8px', background: '#1677ff' }} />
        <Typography.Title level={5} style={{ margin: 0 }}>{user.username}</Typography.Title>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>{user.email}</Typography.Text>
      </div>
      
      {showSectors && (
        <div style={{ marginBottom: 12 }}>
           <Typography.Text type="secondary" strong style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>SECTORS</Typography.Text>
           <Space wrap size={[0, 4]}>
              {(user.sectors || []).map(s => <Tag key={`${s.sectorCode}-${s.role}`} color="blue">{s.sectorCode}</Tag>)}
              {!user.sectors?.length && <Typography.Text type="secondary" italic style={{ fontSize: 12 }}>None</Typography.Text>}
           </Space>
        </div>
      )}

      {showRoles && (
        <div style={{ marginBottom: 12 }}>
           <Typography.Text type="secondary" strong style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>ROLES</Typography.Text>
           <Space wrap size={[0, 4]}>
              {(user.roles || []).map(r => <Tag key={r}>{r.replace('tickora_', '')}</Tag>)}
           </Space>
        </div>
      )}

      <Button block size="small" type="link" onClick={() => navigate('/profile')}>Full Profile</Button>
    </div>
  )
}

function ShortcutsWidget({ config }: { config: any }) {
  const navigate = useNavigate()
  const items = config.items || ['create', 'tickets', 'monitor']
  return (
    <div style={{ padding: 16, display: 'grid', gap: 8 }}>
      {items.includes('create') && <Button block icon={<PlusOutlined />} onClick={() => navigate('/create')}>Create Ticket</Button>}
      {items.includes('tickets') && <Button block icon={<UnorderedListOutlined />} onClick={() => navigate('/tickets')}>View Queue</Button>}
      {items.includes('monitor') && <Button block icon={<SendOutlined />} onClick={() => navigate('/monitor')}>Monitor</Button>}
      {items.includes('admin') && <Button block icon={<SettingOutlined />} onClick={() => navigate('/admin')}>Admin</Button>}
    </div>
  )
}

function ClockWidget() {
  const [time, setTime] = useState(new Date())
  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  return (
    <div style={{ padding: 16, textAlign: 'center', height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
      <Typography.Title level={2} style={{ margin: 0, fontFamily: 'monospace' }}>
        {time.toLocaleTimeString()}
      </Typography.Title>
      <Typography.Text type="secondary">
        {time.toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
      </Typography.Text>
    </div>
  )
}

function SystemHealthWidget() {
  const { data, isLoading } = useQuery({
    queryKey: ['healthCheck'],
    queryFn: async () => {
        const { data } = await apiClient.get('/health')
        return data
    },
    refetchInterval: 30_000
  })

  if (isLoading) return <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>

  const checks = data?.checks || {}
  return (
    <div style={{ padding: 12 }}>
      <Flex vertical gap={12}>
        {Object.entries(checks).map(([service, status]) => (
          <Flex key={service} justify="space-between" align="center">
            <Typography.Text strong style={{ textTransform: 'capitalize' }}>{service}</Typography.Text>
            <Tag color={status === 'ok' ? 'success' : 'error'}>{String(status).toUpperCase()}</Tag>
          </Flex>
        ))}
        {!Object.keys(checks).length && <Empty description="No health data" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
      </Flex>
    </div>
  )
}

function WelcomeWidget() {
  const user = useSessionStore(s => s.user)
  return (
    <div style={{ padding: 16, height: '100%', display: 'flex', alignItems: 'center', gap: 16 }}>
      <SmileOutlined style={{ fontSize: 32, color: '#faad14' }} />
      <div>
        <Typography.Title level={4} style={{ margin: 0 }}>Hello, {user?.firstName || user?.username}!</Typography.Title>
        <Typography.Text type="secondary">Have a productive day at Tickora.</Typography.Text>
      </div>
    </div>
  )
}

function SlaOverviewWidget() {
  const { data } = useQuery({
    queryKey: ['monitorOverview'],
    queryFn: () => getMonitorOverview(),
  })
  
  return (
    <div style={{ padding: 16 }}>
      <Row gutter={16}>
        <Col span={12}>
           <Statistic title="Breached" value={data?.global?.kpis.sla_breached ?? 0} styles={{ content: { color: '#cf1322' } }} />
        </Col>
        <Col span={12}>
           <Statistic title="Critical" value={data?.distributor?.kpis.critical_pending ?? 0} styles={{ content: { color: '#d46b08' } }} />
        </Col>
      </Row>
    </div>
  )
}

function SectorStatsWidget({ config }: { config: any }) {
  const { data, isLoading } = useQuery({
    queryKey: ['monitorSector', config.sectorCode],
    queryFn: () => getMonitorSector(config.sectorCode!),
    enabled: !!config.sectorCode,
  })

  if (!config.sectorCode) return <div style={{ padding: 20 }}><Empty description="Configure sector" image={Empty.PRESENTED_IMAGE_SIMPLE} /></div>
  if (isLoading) return <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>
  if (!data) return <Empty />

  const chartData = config.groupBy === 'priority' ? data.by_priority : data.by_status
  
  const option = {
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 6 },
      label: { show: false },
      data: chartData.map(i => ({ value: i.count, name: i.key.replace(/_/g, ' ') }))
    }]
  }

  return <ReactECharts option={option} style={{ height: '100%', minHeight: 150 }} />
}

function UserWorkloadWidget({ config }: { config: any }) {
    const { data, isLoading } = useQuery({
      queryKey: ['monitorSector', config.sectorCode],
      queryFn: () => getMonitorSector(config.sectorCode!),
      enabled: !!config.sectorCode,
    })
  
    if (!config.sectorCode) return <div style={{ padding: 20 }}><Empty description="Configure sector" image={Empty.PRESENTED_IMAGE_SIMPLE} /></div>
    if (isLoading) return <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>
    
    const showDone = config.showDone !== false
    const showActive = config.showActive !== false

    return (
      <Table 
        size="small" 
        pagination={false} 
        dataSource={data?.workload || []} 
        rowKey="assignee_user_id"
        columns={[
          { title: 'Operator', dataIndex: 'username', render: (v: string) => v || 'Unassigned' },
          showActive && { title: 'Active', dataIndex: 'active', align: 'right' as const },
          showDone && { title: 'Done', dataIndex: 'done', align: 'right' as const },
        ].filter(Boolean) as any}
      />
    )
}

function StaleTicketsWidget({ config }: { config: any }) {
    const navigate = useNavigate()
    const { token } = antTheme.useToken()
    const { data, isLoading } = useQuery<any>({
        queryKey: ['monitorStale', config.sectorCode, config.hours],
        queryFn: () => config.sectorCode ? getMonitorSector(config.sectorCode) : getMonitorOverview(),
        staleTime: 60_000,
    })

    if (isLoading) return <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>

    const tickets = (config.sectorCode ? (data as any)?.stale_tickets : (data as any)?.stale_tickets) || []

    return (
        <div style={{ padding: '4px 0' }}>
            {tickets.map((t: any) => (
                <div
                    key={t.id}
                    style={{ padding: '8px 12px', cursor: 'pointer', borderBottom: `1px solid ${token.colorBorderSecondary}` }}
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
                </div>
            ))}
            {tickets.length === 0 && (
                <div style={{ padding: 20 }}>
                    <Empty description="No stale tickets" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                </div>
            )}
        </div>
    )
}

function NotReviewedWidget({ config }: { config: any }) {
    const navigate = useNavigate()
    const { token } = antTheme.useToken()
    const { data, isLoading } = useQuery({
        queryKey: ['monitorOverview'],
        queryFn: () => getMonitorOverview(),
        staleTime: 60_000,
    })

    if (isLoading) return <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>
    const tickets = (data?.distributor?.not_reviewed || []).slice(0, config.limit || 20)

    return (
        <div style={{ padding: '4px 0' }}>
            {tickets.map((t: any) => (
                <div
                    key={t.id}
                    style={{ padding: '8px 12px', cursor: 'pointer', borderBottom: `1px solid ${token.colorBorderSecondary}` }}
                    onClick={() => navigate(`/tickets/${t.id}`)}
                    className="tickora-row-clickable"
                >
                    <div style={{ display: 'grid', gap: 2, width: '100%' }}>
                        <Flex justify="space-between" align="center">
                            <Typography.Text strong ellipsis style={{ fontSize: 13 }}>{t.title || t.ticket_code}</Typography.Text>
                            <PriorityTag priority={t.priority} />
                        </Flex>
                        <Typography.Text type="secondary" style={{ fontSize: 11 }}>{t.ticket_code} · {fmtDateTime(t.created_at)}</Typography.Text>
                    </div>
                </div>
            ))}
            {tickets.length === 0 && (
                <div style={{ padding: 20 }}>
                    <Empty description="No pending tickets" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                </div>
            )}
        </div>
    )
}

function ReviewedTodayWidget({ config }: { config: any }) {
    const navigate = useNavigate()
    const { token } = antTheme.useToken()
    const { data, isLoading } = useQuery({
        queryKey: ['monitorOverview'],
        queryFn: () => getMonitorOverview(),
        staleTime: 60_000,
    })

    if (isLoading) return <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>
    const tickets = (data?.distributor?.reviewed_today || []).slice(0, config.limit || 20)

    return (
        <div style={{ padding: '4px 0' }}>
            {tickets.map((t: any) => (
                <div
                    key={t.id}
                    style={{ padding: '8px 12px', cursor: 'pointer', borderBottom: `1px solid ${token.colorBorderSecondary}` }}
                    onClick={() => navigate(`/tickets/${t.id}`)}
                    className="tickora-row-clickable"
                >
                    <div style={{ display: 'grid', gap: 2, width: '100%' }}>
                        <Flex justify="space-between" align="center">
                            <Typography.Text strong ellipsis style={{ fontSize: 13 }}>{t.title || t.ticket_code}</Typography.Text>
                            <StatusTag status={t.status} />
                        </Flex>
                        <Typography.Text type="secondary" style={{ fontSize: 11 }}>{t.ticket_code} · Reviewed recently</Typography.Text>
                    </div>
                </div>
            ))}
            {tickets.length === 0 && (
                <div style={{ padding: 20 }}>
                    <Empty description="No tickets reviewed today" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                </div>
            )}
        </div>
    )
}

function WorkloadBalancerWidget({ config }: { config: any }) {
    const { data, isLoading } = useQuery({
        queryKey: ['monitorSector', config.sectorCode],
        queryFn: () => getMonitorSector(config.sectorCode!),
        enabled: !!config.sectorCode,
        staleTime: 60_000,
    })

    if (!config.sectorCode) return <div style={{ padding: 20 }}><Empty description="Configure sector" image={Empty.PRESENTED_IMAGE_SIMPLE} /></div>
    if (isLoading) return <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>

    return <WorkloadChart data={data?.workload || []} height={200} />
}

function BottleneckWidget({ config }: { config: any }) {
    const { data, isLoading } = useQuery<any>({
        queryKey: ['monitorBottleneck', config.sectorCode],
        queryFn: () => config.sectorCode ? getMonitorSector(config.sectorCode) : getMonitorOverview(),
        staleTime: 60_000,
    })

    if (isLoading) return <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>

    const analysis = (config.sectorCode ? (data as any)?.bottleneck_analysis : (data as any)?.global?.bottleneck_analysis) || []
    const chartData = analysis.map((item: any) => ({
        key: item.status,
        count: item.avg_minutes
    }))

    return <BreakdownChart data={chartData} title="Avg. Minutes per Status" height={200} />
}

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
    HourglassOutlined: <HourglassOutlined />,
    CheckCircleOutlined: <CheckCircleOutlined />,
}

function getIconComponent(name: string | null | undefined) {
    if (!name) return <AppstoreOutlined />
    return ICON_MAP[name] || <AppstoreOutlined />
}

const WIDGET_TYPES = [
    { type: 'ticket_list', label: 'Ticket List', icon: <UnorderedListOutlined />, configurable: true },
    { type: 'monitor_kpi', label: 'KPI Statistic', icon: <BarChartOutlined />, configurable: true },
    { type: 'audit_stream', label: 'Audit Log', icon: <AuditOutlined />, configurable: true },
    { type: 'profile_card', label: 'My Profile', icon: <UserOutlined />, configurable: true },
    { type: 'recent_comments', label: 'Recent Comments', icon: <MessageOutlined />, configurable: true },
    { type: 'sector_stats', label: 'Sector Chart', icon: <PieChartOutlined />, configurable: true },
    { type: 'user_workload', label: 'User Workload', icon: <TeamOutlined />, configurable: true },
    { type: 'stale_tickets', label: 'Stale Tickets', icon: <HistoryOutlined />, configurable: true },
    { type: 'workload_balancer', label: 'Workload Balancer', icon: <BarChartOutlined />, configurable: true },
    { type: 'bottleneck_analysis', label: 'Bottleneck Analysis', icon: <LineChartOutlined />, configurable: true },
    { type: 'not_reviewed', label: 'Not Yet Reviewed', icon: <HourglassOutlined />, configurable: true },
    { type: 'reviewed_today', label: 'Reviewed Today', icon: <CheckCircleOutlined />, configurable: true },
    { type: 'shortcuts', label: 'Quick Links', icon: <SendOutlined />, configurable: true },
    { type: 'clock', label: 'Clock', icon: <FieldTimeOutlined />, configurable: false },
    { type: 'system_health', label: 'System Health', icon: <DatabaseOutlined />, configurable: false },
    { type: 'sla_overview', label: 'SLA Overview', icon: <CarryOutOutlined />, configurable: false },
    { type: 'welcome_banner', label: 'Welcome Banner', icon: <SmileOutlined />, configurable: false },
]

/**
 * A registry component that maps widget types to their respective implementation components.
 * It acts as a dispatcher for rendering different types of widgets based on the provided configuration.
 * 
 * @param {Object} props - The component props.
 * @param {DashboardWidgetDto} props.widget - The widget data and configuration to render.
 */
function WidgetRenderer({ widget }: { widget: DashboardWidgetDto }) {
  if (widget.type === 'ticket_list') return <TicketListWidget config={widget.config} />
  if (widget.type === 'monitor_kpi') return <KpiWidget config={widget.config} />
  if (widget.type === 'audit_stream') return <AuditWidget config={widget.config} />
  if (widget.type === 'profile_card') return <ProfileWidget config={widget.config} />
  if (widget.type === 'shortcuts') return <ShortcutsWidget config={widget.config} />
  if (widget.type === 'clock') return <ClockWidget />
  if (widget.type === 'system_health') return <SystemHealthWidget />
  if (widget.type === 'welcome_banner') return <WelcomeWidget />
  if (widget.type === 'sla_overview') return <SlaOverviewWidget />
  if (widget.type === 'sector_stats') return <SectorStatsWidget config={widget.config} />
  if (widget.type === 'user_workload') return <UserWorkloadWidget config={widget.config} />
  if (widget.type === 'recent_comments') return <RecentCommentsWidget config={widget.config} />
  if (widget.type === 'stale_tickets') return <StaleTicketsWidget config={widget.config} />
  if (widget.type === 'workload_balancer') return <WorkloadBalancerWidget config={widget.config} />
  if (widget.type === 'bottleneck_analysis') return <BottleneckWidget config={widget.config} />
  if (widget.type === 'not_reviewed') return <NotReviewedWidget config={widget.config} />
  if (widget.type === 'reviewed_today') return <ReviewedTodayWidget config={widget.config} />

  return <Empty description={`Widget type ${widget.type} coming soon`} image={Empty.PRESENTED_IMAGE_SIMPLE} />
}

// ── Dashboard Detail ────────────────────────────────────────────────────────

const CONFIGURABLE_TYPES = [
    'ticket_list', 'monitor_kpi', 'audit_stream', 'profile_card', 'shortcuts', 
    'sector_stats', 'user_workload', 'workload_balancer', 'bottleneck_analysis', 
    'stale_tickets', 'recent_comments', 'not_reviewed', 'reviewed_today'
]

/**
 * Component for viewing and editing the details of a specific custom dashboard.
 * Manages the grid layout, widget lifecycle (add, remove, configure), and title editing.
 * Uses react-grid-layout for a responsive and draggable/resizable dashboard experience.
 * 
 * @param {Object} props - The component props.
 * @param {string} props.dashboardId - The unique identifier of the dashboard to display.
 * @param {() => void} props.onBack - Callback function to navigate back to the dashboard list.
 */
function DashboardDetail({ dashboardId, onBack }: { dashboardId: string, onBack: () => void }) {
  const { token } = antTheme.useToken()
  const qc = useQueryClient()
  const [editingTitle, setEditingTitle] = useState(false)
  const [editingWidget, setEditingWidget] = useState<DashboardWidgetDto | null>(null)
  const [isAddingWidget, setIsAddingWidget] = useState(false)
  const [autoConfigMode, setAutoConfigMode] = useState<'append' | 'replace'>('replace')
  const [form] = Form.useForm()
  
  const { data: dashboard, isLoading } = useQuery({
    queryKey: ['customDashboard', dashboardId],
    queryFn: () => getDashboard(dashboardId),
  })

  const { data: adminWidgets } = useQuery({
    queryKey: ['adminWidgets'],
    queryFn: listAdminWidgets,
    staleTime: 300_000,
  })

  const widgetDefs = useMemo(() => {
    if (!adminWidgets?.items) return WIDGET_TYPES
    return adminWidgets.items.filter(w => w.is_active).map(w => ({
        type: w.type,
        label: w.display_name,
        icon: getIconComponent(w.icon),
        configurable: CONFIGURABLE_TYPES.includes(w.type)
    }))
  }, [adminWidgets])

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
    mutationFn: (type: string) => {
        const typeInfo = widgetDefs.find(t => t.type === type)
        const payload = {
            type,
            title: typeInfo?.label,
            x: 0, y: 0, w: 4, h: 6,
            config: {}
        }
        return upsertWidget(dashboardId, payload)
    },
    onSuccess: (w) => {
      setIsAddingWidget(false)
      qc.invalidateQueries({ queryKey: ['customDashboard', dashboardId] })
      message.success('Widget added')
      // Auto-open config if configurable
      const typeInfo = widgetDefs.find(t => t.type === w.type)
      if (typeInfo?.configurable) {
          setEditingWidget(w)
      }
    }
  })

  const saveConfig = useMutation({
      mutationFn: (values: any) => upsertWidget(dashboardId, { ...values, id: editingWidget?.id }),
      onSuccess: () => {
          setEditingWidget(null)
          qc.invalidateQueries({ queryKey: ['customDashboard', dashboardId] })
          message.success('Configuration saved')
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

  const autoArrange = useMutation({
    mutationFn: async () => {
        const widgets = dashboard?.widgets || []
        const cols = 3
        const w_val = 4
        const h_val = 6
        for (let i = 0; i < widgets.length; i++) {
            const w = widgets[i]
            const x = (i % cols) * w_val
            const y = Math.floor(i / cols) * h_val
            await upsertWidget(dashboardId, { id: w.id, x, y, w: w_val, h: h_val })
        }
    },
    onSuccess: () => {
        qc.invalidateQueries({ queryKey: ['customDashboard', dashboardId] })
        message.success('Widgets rearranged')
    }
  })

  const user = useSessionStore(s => s.user)

  /**
   * Mutation to automatically configure the dashboard widgets based on user roles and assignments.
   * Supports 'append' (add recommended widgets) or 'replace' (start from scratch) modes.
   */
  const autoConfig = useMutation({
    mutationFn: () => {
        const primarySector = user?.sectors?.[0]?.sectorCode
        return autoConfigureDashboard(dashboardId, autoConfigMode, primarySector)
    },
    onSuccess: () => {
        setIsAddingWidget(false)
        qc.invalidateQueries({ queryKey: ['customDashboard', dashboardId] })
        message.success(`Dashboard auto-configured (${autoConfigMode})`)
    },

    onError: (err: any) => {
        message.error(err.response?.data?.detail || 'Failed to auto-configure')
    }
  })

  useEffect(() => {
    if (editingWidget) {
        form.setFieldsValue({
            title: editingWidget.title,
            config: editingWidget.config,
        })
    }
  }, [editingWidget, form])

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
           <Button icon={<SettingOutlined />} loading={autoArrange.isPending} onClick={() => autoArrange.mutate()}>Auto-arrange</Button>
           <Button icon={<AppstoreAddOutlined />} type="primary" onClick={() => { setEditingWidget(null); setIsAddingWidget(true) }}>Add Widget</Button>
           <Button icon={<ReloadOutlined />} onClick={() => qc.invalidateQueries({ queryKey: ['customDashboard', dashboardId] })} />
        </Space>
      </Flex>

      <div style={{ background: 'rgba(0,0,0,0.02)', borderRadius: 12, minHeight: 'calc(100vh - 200px)', padding: 8 }}>
        <ResponsiveGridLayout
          key={dashboard.widgets?.length} 
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
                <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, flex: 1 }}>
                    <Typography.Text strong style={{ fontSize: 12, lineHeight: '1.2' }} ellipsis>{w.title || w.type}</Typography.Text>
                    {w.config.legend && (
                        <Typography.Text type="secondary" style={{ fontSize: 10, lineHeight: '1.2' }} ellipsis>
                           {w.config.legend}
                        </Typography.Text>
                    )}
                </div>
                <Space size={2} style={{ flexShrink: 0 }}>
                  {CONFIGURABLE_TYPES.includes(w.type) && (
                    <Button 
                        size="small" type="text" icon={<SettingOutlined />} 
                        onMouseDown={e => e.stopPropagation()}
                        onClick={() => setEditingWidget(w)} 
                    />
                  )}
                  <Button 
                    size="small" type="text" danger icon={<DeleteOutlined />} 
                    onMouseDown={e => e.stopPropagation()}
                    onClick={() => removeWidget.mutate(w.id)} 
                  />
                </Space>
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

      <Modal 
        title="Add Widget" 
        open={isAddingWidget} 
        onCancel={() => setIsAddingWidget(false)} 
        footer={null} 
        width={700}
      >
        <Typography.Title level={5} style={{ marginBottom: 16 }}>Auto configuration</Typography.Title>
        <Flex gap={24} align="start" vertical>
           <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
              Let the magic wand setup your workspace based on your current roles and active assignments.
           </Typography.Paragraph>
           <Flex gap={16} align="center">
              <Radio.Group value={autoConfigMode} onChange={e => setAutoConfigMode(e.target.value)}>
                  <Space>
                      <Radio value="append">Append Recommended</Radio>
                      <Radio value="replace">Replace Existing</Radio>
                  </Space>
              </Radio.Group>
              <Button 
                type="primary" 
                icon={<ThunderboltOutlined />} 
                loading={autoConfig.isPending}
                onClick={() => autoConfig.mutate()}
                style={{ background: '#722ed1', borderColor: '#722ed1' }}
              >
                Auto-configure
              </Button>
           </Flex>
        </Flex>

        <Divider style={{ margin: '24px 0' }} />

        <Typography.Title level={5} style={{ marginBottom: 16 }}>Widgets zone</Typography.Title>
        <Row gutter={[12, 12]}>
          {widgetDefs.map(w => (
            <Col key={w.type} xs={12} sm={8} md={6}>
              <Card 
                size="small" 
                hoverable 
                onClick={() => addWidget.mutate(w.type)} 
                style={{ 
                  textAlign: 'center', 
                  height: '100%', 
                  display: 'flex', 
                  flexDirection: 'column', 
                  justifyContent: 'center' 
                }}
              >
                <div style={{ fontSize: 24, marginBottom: 4, color: token.colorPrimary }}>{w.icon}</div>
                <div style={{ fontSize: 13, fontWeight: 500 }}>{w.label}</div>
              </Card>
            </Col>
          ))}
        </Row>
      </Modal>

      <Modal 
        title={editingWidget ? "Configure Widget" : "Add Widget"} 
        open={!!editingWidget} 
        onCancel={() => { setEditingWidget(null); form.resetFields() }} 
        onOk={() => form.submit()}
      >
        <Form form={form} layout="vertical" onFinish={saveConfig.mutate}>
          <Form.Item name="title" label="Widget Title" rules={[{ required: true }]}>
            <Input />
          </Form.Item>

          <Form.Item name={['config', 'legend']} label="Legend / Description (Tooltip)">
             <Input.TextArea rows={2} placeholder="Briefly explain what this widget shows..." />
          </Form.Item>
          
          <Divider style={{ margin: '12px 0' }} />

          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.type !== cur.type}>
            {({ getFieldValue }) => {
              const type = editingWidget?.type
              
              if (type === 'ticket_list') {
                  return (
                    <>
                      <UserSelect name={['config', 'assignee_user_id']} label="Filter by Assignee" />
                      <SectorSelect name={['config', 'current_sector_code']} label="Filter by Sector" />
                      <Form.Item name={['config', 'status']} label="Ticket Status">
                        <Select allowClear options={STATUS_OPTIONS} />
                      </Form.Item>
                      <Form.Item name={['config', 'priority']} label="Ticket Priority">
                        <Select allowClear options={PRIORITY_OPTIONS} />
                      </Form.Item>
                      <Form.Item name={['config', 'limit']} label="Max Items">
                        <Select options={[5, 10, 20, 50].map(v => ({ value: v, label: v }))} />
                      </Form.Item>
                    </>
                  )
              }
              if (type === 'monitor_kpi') {
                  return (
                    <>
                      <Form.Item name={['config', 'path']} label="Data Point" rules={[{ required: true }]}>
                        <Select options={[
                            { value: 'personal.kpis.assigned_active', label: 'Personal: Active Assigned' },
                            { value: 'personal.beneficiary_kpis.active', label: 'Personal: My Active Requests' },
                            { value: 'global.kpis.total_tickets', label: 'Global: Total Tickets (System)' },
                            { value: 'global.kpis.active_tickets', label: 'Global: Active Total' },
                            { value: 'global.kpis.sla_breached', label: 'Global: SLA Breaches' },
                            { value: 'distributor.kpis.pending_review', label: 'Distribution: Pending Review' },
                        ]} />
                      </Form.Item>
                      <Form.Item name={['config', 'label']} label="Override Label">
                        <Input placeholder="Leave empty for default" />
                      </Form.Item>
                      <Form.Item name={['config', 'color']} label="Metric Color">
                        <Input placeholder="#hex or CSS name" />
                      </Form.Item>
                    </>
                  )
              }
              if (type === 'audit_stream') {
                  return (
                    <>
                      <TicketSelect name={['config', 'ticketId']} label="Filter by Ticket" />
                      <UserSelect name={['config', 'userId']} label="Filter by Actor" />
                      <Form.Item name={['config', 'limit']} label="Max Events">
                        <Select options={[5, 10, 20, 30].map(v => ({ value: v, label: v }))} />
                      </Form.Item>
                    </>
                  )
              }
              if (type === 'profile_card') {
                  return (
                    <>
                       <Form.Item name={['config', 'showSectors']} valuePropName="checked" label="Show My Sectors">
                          <Switch />
                       </Form.Item>
                       <Form.Item name={['config', 'showRoles']} valuePropName="checked" label="Show My Roles">
                          <Switch />
                       </Form.Item>
                    </>
                  )
              }
              if (type === 'shortcuts') {
                  return (
                    <Form.Item name={['config', 'items']} label="Enabled Shortcuts">
                        <Checkbox.Group options={[
                            { label: 'Create', value: 'create' },
                            { label: 'Queue', value: 'tickets' },
                            { label: 'Monitor', value: 'monitor' },
                            { label: 'Admin', value: 'admin' },
                        ]} />
                    </Form.Item>
                  )
              }
              if (type === 'sector_stats' || type === 'user_workload' || type === 'workload_balancer' || type === 'bottleneck_analysis' || type === 'not_reviewed' || type === 'reviewed_today') {
                 return (
                    <>
                        <SectorSelect name={['config', 'sectorCode']} label="Target Sector" />
                        {type === 'user_workload' && (
                            <>
                                <Form.Item name={['config', 'showActive']} valuePropName="checked" label="Show Active Count" initialValue={true}>
                                    <Switch />
                                </Form.Item>
                                <Form.Item name={['config', 'showDone']} valuePropName="checked" label="Show Done Count" initialValue={true}>
                                    <Switch />
                                </Form.Item>
                            </>
                        )}
                    </>
                 )
              }
              if (type === 'stale_tickets') {
                  return (
                    <>
                        <SectorSelect name={['config', 'sectorCode']} label="Target Sector (Optional)" />
                        <Form.Item name={['config', 'hours']} label="Inactivity Threshold (Hours)" initialValue={24}>
                            <Select options={[1, 4, 8, 12, 24, 48, 72].map(v => ({ value: v, label: `${v} hours` }))} />
                        </Form.Item>
                    </>
                  )
              }
              if (type === 'recent_comments') {
                  return (
                    <TicketSelect name={['config', 'ticketId']} label="Watch Ticket" />
                  )
              }
              return null
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
                <DeleteOutlined key="del" onMouseDown={e => e.stopPropagation()} onClick={(e) => { e.stopPropagation(); del.mutate(d.id) }} />
              ]}
              styles={{ body: { padding: 16 } }}
            >
              <Card.Meta 
                avatar={<AppstoreOutlined style={{ fontSize: 24, color: token.colorPrimary }} />}
                title={d.title} 
                description={
                  <div style={{ display: 'grid', gap: 4 }}>
                    <Typography.Text type="secondary" ellipsis={{ tooltip: d.description }} style={{ fontSize: 12 }}>
                      {d.description || 'No description'}
                    </Typography.Text>
                    <Flex justify="space-between" align="center" style={{ marginTop: 8 }}>
                       <Tag icon={<AppstoreOutlined />} color="blue" style={{ margin: 0 }}>
                         {d.widget_count} widgets
                       </Tag>
                       <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                         Updated {fmtDateTime(d.updated_at)}
                       </Typography.Text>
                    </Flex>
                  </div>
                }
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
          <Form.Item name="description" label="Description (optional)">
            <Input.TextArea placeholder="A brief summary of what this dashboard tracks" rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
