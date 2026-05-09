import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import ReactECharts from 'echarts-for-react'
import {
  Alert, Button, Col, Empty, Flex, List, Row, Select, Space, Statistic, Table, Tabs, Tag,
  Typography, theme as antTheme, Spin,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ReloadOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import {
  getMonitorOverview, getMonitorSector, getTicketOptions, getMonitorUser,
  listAssignableUsers, type MonitorOldTicket,
  type MonitorSector,
} from '@/api/tickets'
import { useSessionStore } from '@/stores/sessionStore'
import { BreakdownChart, DoughnutChart, WorkloadChart, labelize } from '@/components/dashboard/DashboardCharts'

function KpiGrid({ values }: { values: Record<string, number | null | undefined> }) {
  const { token } = antTheme.useToken()
  return (
    <Row gutter={[12, 12]}>
      {Object.entries(values).map(([key, value]) => (
        <Col key={key} xs={12} md={8} xl={6}>
          <div style={{ background: token.colorBgContainer, border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8, padding: 14, minHeight: 94, boxShadow: token.boxShadowTertiary }}>
            <Statistic title={labelize(key)} value={value ?? '-'} precision={typeof value === 'number' && !Number.isInteger(value) ? 1 : 0} />
          </div>
        </Col>
      ))}
    </Row>
  )
}

function ChartPanel({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  const { token } = antTheme.useToken()
  return (
    <div style={{ background: token.colorBgContainer, border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8, padding: 16, minHeight: 286, boxShadow: token.boxShadowTertiary }}>
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

function OldestTickets({ tickets }: { tickets: MonitorOldTicket[] }) {
  const navigate = useNavigate()
  const { token } = antTheme.useToken()
  return (
    <div style={{ padding: '4px 0' }}>
      {tickets.map((ticket) => (
        <div 
          key={ticket.id}
          style={{ padding: '8px 12px', cursor: 'pointer', borderBottom: `1px solid ${token.colorBorderSecondary}` }} 
          onClick={() => navigate(`/tickets/${ticket.id}`)}
          className="tickora-row-clickable"
        >
          <div style={{ display: 'grid', gap: 4 }}>
            <Space><Typography.Text strong>{ticket.ticket_code}</Typography.Text><Tag>{ticket.status}</Tag><Tag color={ticket.priority === 'critical' ? 'red' : undefined}>{ticket.priority}</Tag></Space>
            <div style={{ color: token.colorTextDescription }}>{ticket.title || 'Untitled ticket'}</div>
          </div>
        </div>
      ))}
      {tickets.length === 0 && (
        <div style={{ padding: 20 }}>
          <Empty description="No active tickets" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </div>
      )}
    </div>
  )
}

/**
 * Displays operational metrics and charts for a specific sector.
 * Includes status and priority breakdowns, oldest tickets list, workload analysis,
 * and bottleneck insights for the selected sector.
 * 
 * @param {Object} props - The component props.
 * @param {MonitorSector} props.sector - The sector monitoring data.
 * @param {React.ReactNode} [props.controls] - Optional UI controls (e.g., sector/user selectors).
 */
function SectorPanel({ sector, controls }: { sector: MonitorSector; controls?: React.ReactNode }) {
  const columns: ColumnsType<MonitorSector['workload'][number]> = [
    { title: 'Assignee', dataIndex: 'assignee_user_id', ellipsis: true },
    { title: 'Active', dataIndex: 'active', width: 100 },
    { title: 'Done', dataIndex: 'done', width: 100 },
  ]
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <Flex justify="space-between" align="start" wrap="wrap" gap={12}>
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>{sector.sector_code} · {sector.sector_name}</Typography.Title>
          <Typography.Text type="secondary">Sector queue, SLA, and workload</Typography.Text>
        </div>
        {controls}
      </Flex>
      <KpiGrid values={sector.kpis} />
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={8}>
          <ChartPanel title="Status" description="Tickets currently routed to this sector, grouped by workflow status.">
            <BreakdownChart data={sector.by_status} title="Tickets" />
          </ChartPanel>
        </Col>
        <Col xs={24} xl={8}>
          <ChartPanel title="Priority" description="Tickets currently routed to this sector, grouped by priority.">
            <BreakdownChart data={sector.by_priority} title="Tickets" color="#fa8c16" />
          </ChartPanel>
        </Col>
        <Col xs={24} xl={8}>
          <ChartPanel title="Oldest Active" description="Oldest open tickets in this sector queue.">
            <OldestTickets tickets={sector.oldest} />
          </ChartPanel>
        </Col>
        {sector.bottleneck_analysis?.length ? (
          <Col xs={24} xl={12}>
            <ChartPanel title="Bottleneck Analysis" description="Average time spent in each status (minutes).">
              <BreakdownChart
                data={sector.bottleneck_analysis.map((b) => ({ key: b.status, count: b.avg_minutes }))}
                title="Avg Minutes"
                color="#eb2f96"
              />
            </ChartPanel>
          </Col>
        ) : null}
        <Col xs={24} lg={12}>
          <ChartPanel title="Workload Chart" description="Visual breakdown of active vs done tickets per user.">
            <WorkloadChart data={sector.workload} height={300} />
          </ChartPanel>
        </Col>
        <Col xs={24} lg={12}>
          <ChartPanel title="Workload Details" description="Tabular view of active and completed tickets.">
            <Table rowKey="assignee_user_id" size="small" pagination={false} columns={columns} dataSource={sector.workload} />
          </ChartPanel>
        </Col>
      </Row>
    </div>
  )
}

/**
 * The primary operational monitoring interface for Tickora.
 * Provides multiple views (Global, Distribution, Sector, User) depending on permissions.
 * Aggregates live metrics, historical trends, and workload distribution to give
 * supervisors and operators a high-level view of system health and performance.
 */
export function MonitorPage() {
  const { token } = antTheme.useToken()
  const user = useSessionStore((s) => s.user)
  const [sectorCode, setSectorCode] = useState<string | undefined>()
  const [userId, setUserId] = useState<string | undefined>()
  const [days, setDays] = useState<number>(30)

  const overview = useQuery({
    queryKey: ['monitorOverview', days],
    queryFn: () => getMonitorOverview(days),
    placeholderData: (prev) => prev,
    staleTime: 60_000,
  })
  const options = useQuery({
    queryKey: ['ticketOptions'],
    queryFn: getTicketOptions,
    staleTime: 300_000,
  })
  const users = useQuery({
    queryKey: ['monitorAssignableUsers', sectorCode],
    queryFn: () => listAssignableUsers(sectorCode),
    enabled: !!sectorCode && (
      !!user?.roles.some((role) => ['tickora_admin', 'tickora_auditor'].includes(role))
      || !!user?.sectors?.some((sector) => sector.sectorCode === sectorCode && sector.role === 'chief')
    ),
    staleTime: 60_000,
  })
  const selectedSector = useQuery({
    queryKey: ['monitorSector', sectorCode],
    queryFn: () => getMonitorSector(sectorCode!),
    enabled: !!sectorCode,
  })
  const selectedUser = useQuery({
    queryKey: ['monitorUser', userId],
    queryFn: () => getMonitorUser(userId!),
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

  if (overview.isLoading) return <div style={{ padding: 100, textAlign: 'center' }}><Spin size="large" /></div>

  const sectorControls = canSelectSector ? (
    <Space wrap>
      <Select
        allowClear
        showSearch
        placeholder="Sector"
        value={sectorCode}
        onChange={(value) => { setSectorCode(value); setUserId(undefined) }}
        optionFilterProp="label"
        style={{ width: 240 }}
        options={sectorOptions}
      />
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
    </Space>
  ) : null

  /**
   * Generates the ECharts configuration for the historical ticket volume chart.
   * Tracks 'Created' vs 'Closed' tickets over the selected time period.
   * Recalculates whenever the overview data changes.
   */
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
  }, [overview.data])

  const tabs = [
    overview.data?.global && {
      key: 'global',
      label: 'Global · all sectors',
      children: (
        <div style={{ display: 'grid', gap: 16 }}>
          <KpiGrid values={overview.data.global.kpis} />
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={8}>
              <ChartPanel title="Status" description="All non-deleted tickets grouped by workflow status.">
                <BreakdownChart data={overview.data.global.by_status} title="Tickets" />
              </ChartPanel>
            </Col>
            <Col xs={24} xl={8}>
              <ChartPanel title="Priority" description="All non-deleted tickets grouped by priority.">
                <BreakdownChart data={overview.data.global.by_priority} title="Tickets" color="#fa8c16" />
              </ChartPanel>
            </Col>
            <Col xs={24} xl={8}>
              <ChartPanel title="Beneficiary Type" description="All non-deleted tickets grouped by requester type.">
                <BreakdownChart data={overview.data.global.by_beneficiary_type} title="Tickets" color="#52c41a" />
              </ChartPanel>
            </Col>
            {overview.data.global.bottleneck_analysis?.length ? (
              <Col xs={24} xl={12}>
                <ChartPanel title="Bottleneck Analysis" description="Average time spent in each status across all sectors (minutes).">
                  <BreakdownChart
                    data={overview.data.global.bottleneck_analysis.map((b) => ({ key: b.status, count: b.avg_minutes }))}
                    title="Avg Minutes"
                    color="#eb2f96"
                  />
                </ChartPanel>
              </Col>
            ) : null}
            {overview.data.global.by_category?.length ? (
              <Col xs={24} xl={12}>
                <ChartPanel title="Categories" description="All non-deleted tickets grouped by category.">
                  <DoughnutChart data={overview.data.global.by_category} title="Tickets" />
                </ChartPanel>
              </Col>
            ) : null}
            {overview.data.global.by_sector?.length ? (
              <Col xs={24} xl={12}>
                <ChartPanel title="Total tickets by sector" description="All non-deleted tickets grouped by current sector, including open and closed tickets.">
                  <BreakdownChart
                    data={overview.data.global.by_sector.map((s) => ({ key: s.sector_code, count: s.count }))}
                    title="Tickets"
                    color="#13a8a8"
                  />
                </ChartPanel>
              </Col>
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
            <Col xs={24} xl={12}>
              <ChartPanel title="Pending Priority" description="Tickets waiting for distribution or sector assignment, grouped by priority.">
                <BreakdownChart data={overview.data.distributor.by_priority} title="Tickets" color="#fa8c16" />
              </ChartPanel>
            </Col>
            <Col xs={24} xl={12}>
              <ChartPanel title="Oldest Review Items" description="Oldest tickets still waiting in the distribution queue.">
                <OldestTickets tickets={overview.data.distributor.oldest} />
              </ChartPanel>
            </Col>
          </Row>
        </div>
      ),
    },
    activeSector && {
      key: 'sector',
      label: 'Sector',
      children: <SectorPanel sector={activeSector} controls={sectorControls} />,
    },
    personal && {
      key: 'personal',
      label: `User · ${personal.username || personal.email || personal.user_id}`,
      children: (
        <div style={{ display: 'grid', gap: 24 }}>
          <div>
            <Typography.Title level={5} style={{ fontSize: 14, marginBottom: 12 }}>Operator Role</Typography.Title>
            <KpiGrid values={personal.kpis} />
            <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
              <Col xs={24} xl={12}>
                <ChartPanel title="Operator Status" description="Tickets where this user is an assignee or primary sector responder.">
                  <BreakdownChart data={personal.by_status} title="Tickets" />
                </ChartPanel>
              </Col>
              <Col xs={24} xl={12}>
                <ChartPanel title="Oldest Assigned" description="Oldest active tickets assigned to this user.">
                  <OldestTickets tickets={personal.oldest} />
                </ChartPanel>
              </Col>
            </Row>
          </div>

          <div>
            <Typography.Title level={5} style={{ fontSize: 14, marginBottom: 12 }}>Requester Role</Typography.Title>
            <KpiGrid values={personal.beneficiary_kpis} />
            <div style={{ marginTop: 16 }}>
              <ChartPanel title="Requester Status" description="Tickets created by or linked to this user as beneficiary.">
                <BreakdownChart data={personal.beneficiary_by_status} title="Tickets" color="#52c41a" />
              </ChartPanel>
            </div>
          </div>
        </div>
      ),
    },
  ].filter(Boolean)

  return (
    <div style={{ padding: 24, display: 'grid', gap: 16 }}>
      <Flex justify="space-between" align="center" wrap="wrap" gap={12}>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>Monitor</Typography.Title>
          <Typography.Text type="secondary">Role-scoped operational metrics</Typography.Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => overview.refetch()} />
      </Flex>

      {overview.error && <Alert type="error" message={overview.error.message} showIcon />}
      {selectedSector.error && <Alert type="error" message={selectedSector.error.message} showIcon />}
      {selectedUser.error && <Alert type="error" message={selectedUser.error.message} showIcon />}

      <Tabs items={tabs as any} />

      {timeseriesOption && (
        <div style={{ background: token.colorBgContainer, border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8, padding: 16, minHeight: 280, boxShadow: token.boxShadowTertiary, marginTop: 16 }}>
          <Flex justify="space-between" align="center" style={{ marginBottom: 8 }}>
            <div>
              <Typography.Title level={5} style={{ margin: 0 }}>Created vs Closed · last {days} days</Typography.Title>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                Daily ticket creation and closure counts visible to your role.
              </Typography.Text>
            </div>
            <Select
              value={days}
              onChange={setDays}
              size="small"
              style={{ width: 120 }}
              options={[
                { value: 1, label: 'Last 24h' },
                { value: 7, label: 'Last 7 days' },
                { value: 30, label: 'Last 30 days' },
              ]}
            />
          </Flex>
          <ReactECharts option={timeseriesOption} style={{ height: 260 }} />
        </div>
      )}
    </div>
  )
}
