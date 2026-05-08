import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Avatar, Button, Card, Col, Descriptions, Divider, Empty, Flex, Modal, Row, Statistic, Tag, Tooltip, Typography, Space,
  theme as antTheme,
} from 'antd'
import {
  CalendarOutlined, CrownOutlined, FullscreenExitOutlined, FullscreenOutlined,
  MailOutlined, SafetyCertificateOutlined, TeamOutlined, UserOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { useSessionStore } from '@/stores/sessionStore'
import {
  getDashboardOverview, listAssignableUsers, listTickets, type AssignableUserDto,
} from '@/api/tickets'
import { StatusTag } from '@/components/common/StatusTag'
import { fmtRelative } from '@/components/common/format'

function initials(first?: string, last?: string, fallback = '?') {
  return ((first?.[0] || '') + (last?.[0] || '')).toUpperCase() || fallback
}

function displayUser(user: AssignableUserDto) {
  return user.username || user.email || user.id
}

function ChiefSectorMembers({ sectorCode, name, expanded = false }: { sectorCode: string; name?: string; expanded?: boolean }) {
  const { token } = antTheme.useToken()
  const members = useQuery({
    queryKey: ['sectorMembers', sectorCode],
    queryFn: () => listAssignableUsers(sectorCode),
    staleTime: 60_000,
  })
  const items: AssignableUserDto[] = members.data?.items || []
  const chiefs = items.filter((u) => u.membership_role === 'chief')
  const regular = items.filter((u) => u.membership_role !== 'chief')

  // Build an org-graph: chief at the centre, members radiating out.
  const option = useMemo(() => {
    const rootName = name || sectorCode
    const root = {
      name: rootName,
      value: items.length,
      symbolSize: expanded ? 78 : 58,
      itemStyle: { color: '#1f4f46', borderColor: '#e6f4ff', borderWidth: 3 },
      label: { color: '#fff', fontWeight: 700 },
    }
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'item' },
      series: [{
        type: 'graph',
        layout: 'force',
        roam: true,
        emphasis: { focus: 'adjacency' },
        label: { show: true, position: 'right', fontSize: 11, color: token.colorText },
        force: { repulsion: expanded ? 520 : 280, edgeLength: expanded ? 135 : 88, gravity: 0.08 },
        data: [
          root,
          ...chiefs.map((u) => ({
            name: displayUser(u),
            symbolSize: expanded ? 48 : 34,
            itemStyle: { color: '#b7791f' },
            tooltip: { formatter: 'Chief · ' + (u.email || u.username) },
          })),
          ...regular.map((u) => ({
            name: displayUser(u),
            symbolSize: expanded ? 36 : 25,
            itemStyle: { color: '#2f7d62' },
            tooltip: { formatter: 'Member · ' + (u.email || u.username) },
          })),
        ],
        edges: items.map((u) => ({ source: rootName, target: displayUser(u) })),
        lineStyle: { color: 'source', curveness: 0.18, opacity: 0.38, width: 1.5 },
      }],
    }
  }, [chiefs, expanded, items, name, regular, sectorCode, token.colorText])

  return (
    <div style={{
      border: `1px solid ${token.colorBorderSecondary}`,
      borderRadius: 8,
      background: token.colorBgContainer,
      overflow: 'hidden',
    }}>
      <Flex justify="space-between" align="center" wrap="wrap" gap={12}
            style={{ padding: '12px 14px', borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
        <Space size={8}>
          <Typography.Title level={5} style={{ margin: 0 }}>{sectorCode}</Typography.Title>
          <Tag color="gold">{chiefs.length} chiefs</Tag>
          <Tag color="green">{regular.length} members</Tag>
        </Space>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>{items.length} visible users</Typography.Text>
      </Flex>
      <div style={{
        display: 'grid',
        gridTemplateColumns: expanded ? 'minmax(0, 1fr) 320px' : 'minmax(0, 1fr)',
        gap: expanded ? 16 : 0,
        padding: 12,
      }}>
        <div style={{
          minHeight: expanded ? 520 : 300,
          borderRadius: 8,
          background: 'linear-gradient(180deg, rgba(47,125,98,0.08), rgba(31,79,70,0.02))',
        }}>
          <ReactECharts option={option} style={{ height: expanded ? 520 : 300 }} />
        </div>
        <div style={{ display: expanded ? 'block' : 'none', minWidth: 0 }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>ROSTER</Typography.Text>
          <div style={{ display: 'grid', gap: 8, marginTop: 10, maxHeight: 500, overflow: 'auto' }}>
            {items.map((u) => (
              <Flex key={`${u.id}-${u.membership_role}`} align="center" justify="space-between" gap={8}
                    style={{ padding: 10, border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8 }}>
                <Space size={8} style={{ minWidth: 0 }}>
                  <Avatar size={30} style={{ background: u.membership_role === 'chief' ? '#b7791f' : '#2f7d62' }}>
                    {displayUser(u)[0]?.toUpperCase()}
                  </Avatar>
                  <div style={{ minWidth: 0 }}>
                    <Typography.Text strong ellipsis style={{ display: 'block', maxWidth: 190 }}>{displayUser(u)}</Typography.Text>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>{u.email || u.id}</Typography.Text>
                  </div>
                </Space>
                <Tag color={u.membership_role === 'chief' ? 'gold' : 'green'}>{u.membership_role}</Tag>
              </Flex>
            ))}
          </div>
        </div>
      </div>
      {items.length === 0 && <Empty description="No members yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
    </div>
  )
}

function TeamsILead({
  sectors,
}: {
  sectors: Array<{ sectorCode: string; role: 'member' | 'chief' }>
}) {
  const { token } = antTheme.useToken()
  const [fullscreen, setFullscreen] = useState(false)
  const content = (expanded: boolean) => (
    <div style={{ display: 'grid', gap: 16 }}>
      <Flex wrap="wrap" gap={10}>
        {sectors.map((s) => (
          <div key={s.sectorCode} style={{
            border: `1px solid ${token.colorBorderSecondary}`,
            borderRadius: 8,
            padding: '10px 12px',
            minWidth: 132,
            background: 'linear-gradient(180deg, rgba(183,121,31,0.10), rgba(47,125,98,0.04))',
          }}>
            <Space size={8}>
              <CrownOutlined style={{ color: '#b7791f' }} />
              <Typography.Text strong>{s.sectorCode}</Typography.Text>
            </Space>
            <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>Lead access</Typography.Text></div>
          </div>
        ))}
      </Flex>
      <Row gutter={[16, 16]}>
        {sectors.map((s) => (
          <Col xs={24} xl={expanded || sectors.length === 1 ? 24 : 12} key={s.sectorCode}>
            <ChiefSectorMembers sectorCode={s.sectorCode} name={s.sectorCode} expanded={expanded} />
          </Col>
        ))}
      </Row>
    </div>
  )

  return (
    <>
      <Card
        title={<Space><UserOutlined /> Teams I lead</Space>}
        extra={(
          <Tooltip title="Maximize">
            <Button type="text" icon={<FullscreenOutlined />} onClick={() => setFullscreen(true)} />
          </Tooltip>
        )}
      >
        {content(false)}
      </Card>
      <Modal
        open={fullscreen}
        footer={null}
        width="100vw"
        style={{ top: 0, maxWidth: '100vw', minHeight: '100vh', paddingBottom: 0 }}
        styles={{
          body: { height: 'calc(100vh - 84px)', overflow: 'auto' },
        }}
        closeIcon={null}
        onCancel={() => setFullscreen(false)}
        destroyOnHidden
      >
        <Flex justify="space-between" align="center" wrap="wrap" gap={12} style={{ marginBottom: 16 }}>
          <div>
            <Typography.Title level={3} style={{ margin: 0 }}>Teams I lead</Typography.Title>
            <Typography.Text type="secondary">Sector leadership map and visible roster</Typography.Text>
          </div>
          <Tooltip title="Minimize">
            <Button icon={<FullscreenExitOutlined />} onClick={() => setFullscreen(false)}>
              Minimize
            </Button>
          </Tooltip>
        </Flex>
        {content(true)}
      </Modal>
    </>
  )
}

export function ProfilePage() {
  const { token } = antTheme.useToken()
  const user = useSessionStore((s) => s.user)

  const recent = useQuery({
    queryKey: ['profile-recent', user?.id],
    queryFn: () => listTickets({ assignee_user_id: user?.id, limit: 5, sort_by: 'updated_at', sort_dir: 'desc' }),
    enabled: !!user?.id,
  })

  const overview = useQuery({
    queryKey: ['dashboardOverview'],
    queryFn: getDashboardOverview,
    staleTime: 60_000,
    enabled: !!user?.id,
  })

  if (!user) return <Empty description="Please log in" />

  const personal = overview.data?.personal
  const chiefSectors = (user.sectors || []).filter((s) => s.role === 'chief')

  return (
    <div style={{ padding: 24 }}>
      <Row gutter={[24, 24]}>
        {/* Identity card */}
        <Col xs={24} md={8}>
          <Card>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, padding: '8px 0' }}>
              <Avatar size={96} style={{
                background: 'linear-gradient(135deg, #1677ff 0%, #003eb3 100%)',
                fontSize: 32, fontWeight: 600,
              }}>{initials(user.firstName, user.lastName, user.username?.[0]?.toUpperCase())}</Avatar>
              <div style={{ textAlign: 'center' }}>
                <Typography.Title level={4} style={{ margin: 0 }}>
                  {[user.firstName, user.lastName].filter(Boolean).join(' ') || user.username || 'You'}
                </Typography.Title>
                <Typography.Text type="secondary"><MailOutlined /> {user.email || 'No email on file'}</Typography.Text>
              </div>
            </div>
            <Divider style={{ margin: '16px 0' }} />
            <Descriptions size="small" column={1}>
              <Descriptions.Item label="Username"><Typography.Text code>{user.username || '—'}</Typography.Text></Descriptions.Item>
              <Descriptions.Item label="User ID"><Typography.Text type="secondary" style={{ fontSize: 11 }}>{user.id}</Typography.Text></Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>

        {/* Roles + KPIs */}
        <Col xs={24} md={16}>
          <div style={{ display: 'grid', gap: 24 }}>
            <Card title={<Space><SafetyCertificateOutlined /> Roles & Sectors</Space>}>
              <Space direction="vertical" style={{ width: '100%' }} size={12}>
                <div>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>GLOBAL ROLES</Typography.Text>
                  <div style={{ marginTop: 6 }}>
                    {(user.roles || []).map((r) => (
                      <Tag color="blue" key={r}>{r.replace('tickora_', '').toUpperCase()}</Tag>
                    ))}
                    {!user.roles?.length && <Typography.Text type="secondary">None</Typography.Text>}
                  </div>
                </div>
                <div>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}><TeamOutlined /> SECTOR MEMBERSHIPS</Typography.Text>
                  <div style={{ marginTop: 6 }}>
                    {user.sectors?.length
                      ? user.sectors.map((m) => (
                          <Tag color={m.role === 'chief' ? 'gold' : 'cyan'} key={m.sectorCode}>
                            {m.sectorCode} · {m.role}
                          </Tag>
                        ))
                      : <Typography.Text type="secondary">No sector assignments</Typography.Text>}
                  </div>
                </div>
              </Space>
            </Card>

            <Card title="My activity">
              <Row gutter={[16, 16]}>
                <Col xs={12} md={6}><Statistic title="Active assignments" value={personal?.kpis?.active ?? '-'} /></Col>
                <Col xs={12} md={6}><Statistic title="Done · last 7d" value={personal?.kpis?.done_last_7d ?? '-'} /></Col>
                <Col xs={12} md={6}><Statistic title="Avg resolution (h)" value={personal?.kpis?.avg_resolution_hours ?? '-'} /></Col>
                <Col xs={12} md={6}><Statistic title="At-risk SLA" value={personal?.kpis?.sla_at_risk ?? '-'} valueStyle={{ color: '#fa8c16' }} /></Col>
              </Row>
            </Card>
          </div>
        </Col>

        {/* Recent assignments */}
        <Col xs={24} lg={12}>
          <Card title={<Space><CalendarOutlined /> Recent assignments</Space>}>
            {(recent.data?.items || []).length === 0
              ? <Empty description="Nothing assigned to you" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              : (
                <div style={{ display: 'grid', gap: 8 }}>
                  {(recent.data?.items || []).map((t) => (
                    <div key={t.id} style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      padding: '8px 12px', border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 6,
                    }}>
                      <Space size={8}>
                        <Typography.Text code>{t.ticket_code}</Typography.Text>
                        <StatusTag status={t.status} />
                      </Space>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {fmtRelative(t.updated_at)}
                      </Typography.Text>
                    </div>
                  ))}
                </div>
              )}
          </Card>
        </Col>

        {/* Status breakdown chart */}
        <Col xs={24} lg={12}>
          <Card title="Status breakdown">
            {personal?.by_status?.length ? (
              <ReactECharts
                style={{ height: 240 }}
                option={{
                  tooltip: { trigger: 'item' },
                  legend: { bottom: 0 },
                  series: [{
                    type: 'pie',
                    radius: ['45%', '70%'],
                    avoidLabelOverlap: false,
                    label: { show: false },
                    labelLine: { show: false },
                    data: personal.by_status.map((b) => ({ name: b.key.replace(/_/g, ' '), value: b.count })),
                  }],
                }}
              />
            ) : <Empty description="No tickets yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
          </Card>
        </Col>

        {/* Chief-only: sector members graph */}
        {chiefSectors.length > 0 && (
          <Col xs={24}>
            <TeamsILead sectors={chiefSectors} />
          </Col>
        )}
      </Row>
    </div>
  )
}
