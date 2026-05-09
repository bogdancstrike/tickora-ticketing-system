import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import ReactECharts from 'echarts-for-react'
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

function BreakdownChart({ data, title, color = '#1677ff' }: { data: DashboardBreakdown[]; title: string; color?: string }) {
  if (!data.length) return <Empty description="No data" image={Empty.PRESENTED_IMAGE_SIMPLE} />

  const option = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { top: 0, data: [title] },
    grid: { left: '3%', right: '4%', bottom: '3%', top: 34, containLabel: true },
    xAxis: { type: 'category', data: data.map((i) => labelize(i.key)), axisTick: { alignWithLabel: true } },
    yAxis: { type: 'value' },
    series: [{ name: title, type: 'bar', barWidth: '60%', data: data.map((i) => i.count), itemStyle: { color, borderRadius: [4, 4, 0, 0] } }],
  }
  return <ReactECharts option={option} style={{ height: 240 }} />
}

function DoughnutChart({ data, title }: { data: DashboardBreakdown[]; title: string }) {
  if (!data.length) return <Empty description="No data" image={Empty.PRESENTED_IMAGE_SIMPLE} />
  const option = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, type: 'scroll' },
    series: [{
      name: title,
      type: 'pie',
      radius: ['45%', '70%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 4, borderColor: 'transparent', borderWidth: 2 },
      label: { show: false },
      labelLine: { show: false },
      data: data.map((i) => ({ name: labelize(i.key), value: i.count })),
    }],
  }
  return <ReactECharts option={option} style={{ height: 240 }} />
}

function ChartPanel({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  const { token } = antTheme.useToken()
  return (
    <div style={{ border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8, padding: 16, minHeight: 286 }}>
      <Typography.Title level={5} style={{ marginTop: 0 }}>{title}</Typography.Title>
      {description && (
        <Typography.Text type="secondary" style={{ display: 'block', marginTop: -4, marginBottom: 8, fontSize: 12 }}>
          {description}
        </Typography.Text>
      )}
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
        <Col xs={24} xl={8}><ChartPanel title="Status" description="Tickets currently routed to this sector, grouped by workflow status."><BreakdownChart data={sector.by_status} title="Tickets" /></ChartPanel></Col>
        <Col xs={24} xl={8}><ChartPanel title="Priority" description="Tickets currently routed to this sector, grouped by priority."><BreakdownChart data={sector.by_priority} title="Tickets" color="#fa8c16" /></ChartPanel></Col>
        <Col xs={24} xl={8}><ChartPanel title="Oldest Active" description="Oldest open tickets in this sector queue."><OldestTickets tickets={sector.oldest} /></ChartPanel></Col>
        <Col xs={24}><ChartPanel title="Workload" description="Active and completed tickets by assignee in this sector."><Table rowKey="assignee_user_id" size="small" pagination={false} columns={columns} dataSource={sector.workload} /></ChartPanel></Col>
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
    enabled: !!sectorCode && (
      !!user?.roles.some((role) => ['tickora_admin', 'tickora_auditor'].includes(role))
      || !!user?.sectors?.some((sector) => sector.sectorCode === sectorCode && sector.role === 'chief')
    ),
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

  const timeseriesOption = useMemo(() => {
    if (!overview.data?.timeseries) return null
    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross', label: { backgroundColor: '#6a7985' } }
      },
      legend: { data: ['Created', 'Closed'] },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: [{ type: 'category', boundaryGap: false, data: overview.data.timeseries.map(d => d.date) }],
      yAxis: [{ type: 'value' }],
      series: [
        {
          name: 'Created',
          type: 'line',
          stack: 'Total',
          areaStyle: {},
          emphasis: { focus: 'series' },
          data: overview.data.timeseries.map(d => d.created),
          itemStyle: { color: '#1677ff' }
        },
        {
          name: 'Closed',
          type: 'line',
          stack: 'Total',
          areaStyle: {},
          emphasis: { focus: 'series' },
          data: overview.data.timeseries.map(d => d.closed),
          itemStyle: { color: '#52c41a' }
        }
      ]
    }
  }, [overview.data?.timeseries])

  const tabs = [
    overview.data?.global && {
      key: 'global',
      label: 'Global · all sectors',
      children: (
        <div style={{ display: 'grid', gap: 16 }}>
          <KpiGrid values={overview.data.global.kpis} />
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={8}><ChartPanel title="Status" description="All non-deleted tickets grouped by workflow status."><BreakdownChart data={overview.data.global.by_status} title="Tickets" /></ChartPanel></Col>
            <Col xs={24} xl={8}><ChartPanel title="Priority" description="All non-deleted tickets grouped by priority."><BreakdownChart data={overview.data.global.by_priority} title="Tickets" color="#fa8c16" /></ChartPanel></Col>
            <Col xs={24} xl={8}><ChartPanel title="Beneficiary Type" description="All non-deleted tickets grouped by requester type."><BreakdownChart data={overview.data.global.by_beneficiary_type} title="Tickets" color="#52c41a" /></ChartPanel></Col>
            {overview.data.global.by_category?.length ? (
              <Col xs={24} xl={12}><ChartPanel title="Categories" description="All non-deleted tickets grouped by category."><DoughnutChart data={overview.data.global.by_category} title="Tickets" /></ChartPanel></Col>
            ) : null}
            {overview.data.global.by_sector?.length ? (
              <Col xs={24} xl={12}><ChartPanel title="Total tickets by sector" description="All non-deleted tickets grouped by current sector, including open and closed tickets.">
                <BreakdownChart
                  data={overview.data.global.by_sector.map((s) => ({ key: s.sector_code, count: s.count }))}
                  title="Tickets"
                  color="#13a8a8"
                />
              </ChartPanel></Col>
            ) : null}
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
            <Col xs={24} xl={12}><ChartPanel title="Pending Priority" description="Tickets waiting for distribution or sector assignment, grouped by priority."><BreakdownChart data={overview.data.distributor.by_priority} title="Tickets" color="#fa8c16" /></ChartPanel></Col>
            <Col xs={24} xl={12}><ChartPanel title="Oldest Review Items" description="Oldest tickets still waiting in the distribution queue."><OldestTickets tickets={overview.data.distributor.oldest} /></ChartPanel></Col>
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
            <Col xs={24} xl={12}><ChartPanel title="User Status" description="Visible tickets involving the selected user, grouped by status."><BreakdownChart data={personal.by_status} title="Tickets" /></ChartPanel></Col>
            <Col xs={24} xl={12}><ChartPanel title="Oldest Assigned" description="Oldest active tickets assigned to the selected user."><OldestTickets tickets={personal.oldest} /></ChartPanel></Col>
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
          <ChartPanel title="Requester Status" description="Tickets created by or linked to you as requester, grouped by status."><BreakdownChart data={overview.data.beneficiary.by_status} title="Tickets" /></ChartPanel>
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

      <Tabs items={tabs as any} />

      {timeseriesOption && (
        <div style={{ border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8, padding: 16, minHeight: 280 }}>
          <Typography.Title level={5} style={{ marginTop: 0 }}>Created vs Closed · last 30 days</Typography.Title>
          <Typography.Text type="secondary" style={{ display: 'block', marginTop: -4, marginBottom: 8, fontSize: 12 }}>
            Daily ticket creation and closure counts visible to your role.
          </Typography.Text>
          <ReactECharts option={timeseriesOption} style={{ height: 260 }} />
        </div>
      )}
    </div>
  )
}
