import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AreaChart, Area, BarChart, Bar, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import {
  Alert, Button, Col, Empty, Flex, List, Row, Select, Space, Statistic, Table, Tabs, Tag,
  Typography, theme as antTheme,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ReloadOutlined } from '@ant-design/icons'
import {
  getDashboardOverview, getSectorDashboard, getTicketOptions, getUserDashboard,
  listAssignableUsers, type DashboardBreakdown, type DashboardOldTicket,
  type DashboardSector,
} from '@/api/tickets'
import { useSessionStore } from '@/stores/sessionStore'

function labelize(value: string) {
  return value.split('_').join(' ')
}

function KpiGrid({ values }: { values: Record<string, number | null | undefined> }) {
  const { token } = antTheme.useToken()
  return (
    <Row gutter={[12, 12]}>
      {Object.entries(values).map(([key, value]) => (
        <Col key={key} xs={12} md={8} xl={6}>
          <div style={{ border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8, padding: 14, minHeight: 94 }}>
            <Statistic title={labelize(key)} value={value ?? '-'} precision={typeof value === 'number' && !Number.isInteger(value) ? 1 : 0} />
          </div>
        </Col>
      ))}
    </Row>
  )
}

function BreakdownChart({ data, color = '#1677ff' }: { data: DashboardBreakdown[]; color?: string }) {
  if (!data.length) return <Empty description="No data" image={Empty.PRESENTED_IMAGE_SIMPLE} />
  return (
    <div style={{ height: 220 }}>
      <ResponsiveContainer>
        <BarChart data={data.map((item) => ({ ...item, key: labelize(item.key) }))}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="key" tick={{ fontSize: 12 }} />
          <YAxis allowDecimals={false} />
          <Tooltip />
          <Bar dataKey="count" fill={color} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function ChartPanel({ title, children }: { title: string; children: React.ReactNode }) {
  const { token } = antTheme.useToken()
  return (
    <div style={{ border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8, padding: 16, minHeight: 286 }}>
      <Typography.Title level={5} style={{ marginTop: 0 }}>{title}</Typography.Title>
      {children}
    </div>
  )
}

function OldestTickets({ tickets }: { tickets: DashboardOldTicket[] }) {
  return (
    <List
      dataSource={tickets}
      locale={{ emptyText: <Empty description="No active tickets" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
      renderItem={(ticket) => (
        <List.Item>
          <List.Item.Meta
            title={<Space><Typography.Text strong>{ticket.ticket_code}</Typography.Text><Tag>{ticket.status}</Tag><Tag color={ticket.priority === 'critical' ? 'red' : undefined}>{ticket.priority}</Tag></Space>}
            description={ticket.title || 'Untitled ticket'}
          />
        </List.Item>
      )}
    />
  )
}

function SectorPanel({ sector }: { sector: DashboardSector }) {
  const columns: ColumnsType<DashboardSector['workload'][number]> = [
    { title: 'Assignee', dataIndex: 'assignee_user_id', ellipsis: true },
    { title: 'Active', dataIndex: 'active', width: 100 },
    { title: 'Done', dataIndex: 'done', width: 100 },
  ]
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div>
        <Typography.Title level={4} style={{ margin: 0 }}>{sector.sector_code} · {sector.sector_name}</Typography.Title>
        <Typography.Text type="secondary">Sector queue, SLA, and workload</Typography.Text>
      </div>
      <KpiGrid values={sector.kpis} />
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={8}><ChartPanel title="Status"><BreakdownChart data={sector.by_status} /></ChartPanel></Col>
        <Col xs={24} xl={8}><ChartPanel title="Priority"><BreakdownChart data={sector.by_priority} color="#fa8c16" /></ChartPanel></Col>
        <Col xs={24} xl={8}><ChartPanel title="Oldest Active"><OldestTickets tickets={sector.oldest} /></ChartPanel></Col>
        <Col xs={24}><ChartPanel title="Workload"><Table rowKey="assignee_user_id" size="small" pagination={false} columns={columns} dataSource={sector.workload} /></ChartPanel></Col>
      </Row>
    </div>
  )
}

export function DashboardPage() {
  const { token } = antTheme.useToken()
  const user = useSessionStore((s) => s.user)
  const [sectorCode, setSectorCode] = useState<string | undefined>()
  const [userId, setUserId] = useState<string | undefined>()
  const overview = useQuery({
    queryKey: ['dashboardOverview'],
    queryFn: getDashboardOverview,
    staleTime: 60_000,
  })
  const options = useQuery({
    queryKey: ['ticketOptions'],
    queryFn: getTicketOptions,
    staleTime: 300_000,
  })
  const users = useQuery({
    queryKey: ['dashboardAssignableUsers', sectorCode],
    queryFn: () => listAssignableUsers(sectorCode),
    enabled: !!sectorCode && !!user?.roles.some((role) => ['tickora_admin', 'tickora_auditor', 'tickora_sector_chief'].includes(role)),
    staleTime: 60_000,
  })
  const selectedSector = useQuery({
    queryKey: ['dashboardSector', sectorCode],
    queryFn: () => getSectorDashboard(sectorCode!),
    enabled: !!sectorCode,
  })
  const selectedUser = useQuery({
    queryKey: ['dashboardUser', userId],
    queryFn: () => getUserDashboard(userId!),
    enabled: !!userId,
  })

  const canSelectSector = !!overview.data?.global || !!user?.sectors?.length
  const sectorOptions = useMemo(() => {
    if (overview.data?.global) {
      return (options.data?.sectors || []).map((s) => ({ value: s.code, label: `${s.code} · ${s.name}` }))
    }
    return (overview.data?.sectors || []).map((s) => ({ value: s.sector_code, label: `${s.sector_code} · ${s.sector_name}` }))
  }, [options.data?.sectors, overview.data?.global, overview.data?.sectors])

  const activeSector = selectedSector.data || overview.data?.sectors[0]
  const personal = selectedUser.data || overview.data?.personal

  const tabs = [
    overview.data?.global && {
      key: 'global',
      label: 'Global',
      children: (
        <div style={{ display: 'grid', gap: 16 }}>
          <KpiGrid values={overview.data.global.kpis} />
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={8}><ChartPanel title="Status"><BreakdownChart data={overview.data.global.by_status} /></ChartPanel></Col>
            <Col xs={24} xl={8}><ChartPanel title="Priority"><BreakdownChart data={overview.data.global.by_priority} color="#fa8c16" /></ChartPanel></Col>
            <Col xs={24} xl={8}><ChartPanel title="Beneficiary Type"><BreakdownChart data={overview.data.global.by_beneficiary_type} color="#52c41a" /></ChartPanel></Col>
          </Row>
        </div>
      ),
    },
    overview.data?.distributor && {
      key: 'distribution',
      label: 'Distribution',
      children: (
        <div style={{ display: 'grid', gap: 16 }}>
          <KpiGrid values={overview.data.distributor.kpis} />
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}><ChartPanel title="Pending Priority"><BreakdownChart data={overview.data.distributor.by_priority} color="#fa8c16" /></ChartPanel></Col>
            <Col xs={24} xl={12}><ChartPanel title="Oldest Review Items"><OldestTickets tickets={overview.data.distributor.oldest} /></ChartPanel></Col>
          </Row>
        </div>
      ),
    },
    activeSector && {
      key: 'sector',
      label: 'Sector',
      children: <SectorPanel sector={activeSector} />,
    },
    personal && {
      key: 'personal',
      label: 'User',
      children: (
        <div style={{ display: 'grid', gap: 16 }}>
          <Typography.Text type="secondary">{personal.username || personal.email || personal.user_id}</Typography.Text>
          <KpiGrid values={personal.kpis} />
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}><ChartPanel title="User Status"><BreakdownChart data={personal.by_status} /></ChartPanel></Col>
            <Col xs={24} xl={12}><ChartPanel title="Oldest Assigned"><OldestTickets tickets={personal.oldest} /></ChartPanel></Col>
          </Row>
        </div>
      ),
    },
    overview.data?.beneficiary && {
      key: 'beneficiary',
      label: 'Requester',
      children: (
        <div style={{ display: 'grid', gap: 16 }}>
          <KpiGrid values={overview.data.beneficiary.kpis} />
          <ChartPanel title="Requester Status"><BreakdownChart data={overview.data.beneficiary.by_status} /></ChartPanel>
        </div>
      ),
    },
  ].filter(Boolean)

  return (
    <div style={{ padding: 24, display: 'grid', gap: 16 }}>
      <Flex justify="space-between" align="center" wrap="wrap" gap={12}>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>Dashboard</Typography.Title>
          <Typography.Text type="secondary">Role-scoped operational metrics</Typography.Text>
        </div>
        <Space wrap>
          {canSelectSector && (
            <Select
              allowClear
              showSearch
              placeholder="Sector"
              value={sectorCode}
              onChange={(value) => { setSectorCode(value); setUserId(undefined) }}
              optionFilterProp="label"
              style={{ width: 220 }}
              options={sectorOptions}
            />
          )}
          {sectorCode && (
            <Select
              allowClear
              showSearch
              placeholder="User"
              value={userId}
              onChange={setUserId}
              optionFilterProp="label"
              loading={users.isLoading}
              style={{ width: 260 }}
              options={(users.data?.items || []).map((u) => ({
                value: u.id,
                label: `${u.username || u.email || u.id} · ${u.membership_role}`,
              }))}
            />
          )}
          <Button icon={<ReloadOutlined />} onClick={() => overview.refetch()} />
        </Space>
      </Flex>

      {overview.error && <Alert type="error" message={overview.error.message} showIcon />}
      {selectedSector.error && <Alert type="error" message={selectedSector.error.message} showIcon />}
      {selectedUser.error && <Alert type="error" message={selectedUser.error.message} showIcon />}

      {overview.data?.timeseries && (
        <div style={{ border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8, padding: 16, height: 260 }}>
          <Typography.Title level={5} style={{ marginTop: 0 }}>Created vs Closed</Typography.Title>
          <ResponsiveContainer>
            <AreaChart data={overview.data.timeseries}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Area type="monotone" dataKey="created" stroke="#1677ff" fill="#1677ff" fillOpacity={0.16} />
              <Area type="monotone" dataKey="closed" stroke="#52c41a" fill="#52c41a" fillOpacity={0.12} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      <Tabs items={tabs} />
    </div>
  )
}
