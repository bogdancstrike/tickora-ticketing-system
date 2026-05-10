import { useEffect, useMemo, useState } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
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
  getMonitorOverview, getMe, listAssignableUsers, listTickets, type AssignableUserDto,
} from '@/api/tickets'
import { StatusTag } from '@/components/common/StatusTag'
import { fmtDate, fmtRelative } from '@/components/common/format'
import { ProductTour, TourInfoButton } from '@/components/common/ProductTour'
import { useTranslation } from 'react-i18next'

function initials(first?: string, last?: string, fallback = '?') {
  return ((first?.[0] || '') + (last?.[0] || '')).toUpperCase() || fallback
}

function displayUser(user: AssignableUserDto) {
  return user.username || user.email || user.id
}

function TeamsILead({
  leadName,
  sectors,
}: {
  leadName: string
  sectors: Array<{ sectorCode: string; role: 'member' | 'chief' }>
}) {
  const { token } = antTheme.useToken()
  const [fullscreen, setFullscreen] = useState(false)
  const sectorCodes = useMemo(() => Array.from(new Set(sectors.map((s) => s.sectorCode))).sort(), [sectors])
  const memberQueries = useQueries({
    queries: sectorCodes.map((sectorCode) => ({
      queryKey: ['sectorMembers', sectorCode],
      queryFn: () => listAssignableUsers(sectorCode),
      staleTime: 60_000,
    })),
  })

  const sectorData = useMemo(() => sectorCodes.map((sectorCode, index) => {
    const items = memberQueries[index]?.data?.items || []
    return {
      sectorCode,
      items,
      chiefs: items.filter((u) => u.membership_role === 'chief'),
      members: items.filter((u) => u.membership_role !== 'chief'),
    }
  }), [memberQueries, sectorCodes])

  const totalUsers = useMemo(() => new Set(
    sectorData.flatMap((sector) => sector.items.map((u) => u.id)),
  ).size, [sectorData])

  const graphOption = (expanded: boolean) => {
    const rootId = 'lead:current-user'
    const userNode = (sectorCode: string, u: AssignableUserDto) => {
      const isChief = u.membership_role === 'chief'
      const nodeId = `user:${sectorCode}:${u.id}:${u.membership_role}`
      return {
        name: nodeId,
        value: displayUser(u),
        symbolSize: isChief ? (expanded ? 20 : 16) : (expanded ? 16 : 13),
        itemStyle: {
          color: isChief ? '#c47f17' : '#2f7d62',
          borderColor: isChief ? '#fff7e6' : '#f6ffed',
          borderWidth: 2,
        },
        label: { formatter: displayUser(u), color: token.colorText },
        tooltip: { formatter: `${displayUser(u)}<br/>${sectorCode} · ${u.membership_role}` },
      }
    }
    const treeData = {
      name: rootId,
      value: leadName,
      symbolSize: expanded ? 30 : 24,
      itemStyle: { color: '#123d36', borderColor: '#e6f4ff', borderWidth: 3 },
      label: { formatter: leadName, color: '#123d36', fontWeight: 700 },
      tooltip: { formatter: `${leadName}<br/>Me` },
      children: sectorData.map((sector) => ({
        name: `sector:${sector.sectorCode}`,
        value: sector.sectorCode,
        symbolSize: expanded ? 24 : 19,
        itemStyle: { color: '#2563eb', borderColor: '#eff6ff', borderWidth: 2 },
        label: { formatter: sector.sectorCode, color: '#1d4ed8', fontWeight: 700 },
        tooltip: { formatter: `${sector.sectorCode}<br/>Sector · ${sector.chiefs.length} chiefs · ${sector.members.length} members` },
        children: [
          ...sector.chiefs.map((u) => userNode(sector.sectorCode, u)),
          ...sector.members.map((u) => userNode(sector.sectorCode, u)),
        ],
      })),
    }
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'item' },
      series: [{
        type: 'tree',
        data: [treeData],
        orient: 'TB',
        edgeShape: 'polyline',
        expandAndCollapse: false,
        initialTreeDepth: -1,
        top: expanded ? 36 : 28,
        bottom: expanded ? 36 : 28,
        left: 24,
        right: 24,
        symbol: 'circle',
        label: {
          show: true,
          position: 'bottom',
          distance: expanded ? 9 : 7,
          fontSize: expanded ? 12 : 11,
          color: token.colorText,
        },
        leaves: {
          label: {
            position: 'bottom',
            distance: expanded ? 9 : 7,
            color: token.colorText,
          },
        },
        lineStyle: {
          color: token.colorBorder,
          width: 1.5,
          curveness: 0,
        },
      }],
    }
  }

  const content = (expanded: boolean) => (
    <div style={{
      display: expanded ? 'flex' : 'grid',
      flexDirection: expanded ? 'column' : undefined,
      gap: 16,
      height: expanded ? 'calc(100vh - 126px)' : undefined,
      minHeight: expanded ? 0 : undefined,
    }}>
      <Flex wrap="wrap" gap={10} align="center" style={{ flex: expanded ? '0 0 auto' : undefined }}>
        <Tag color="gold">{sectorCodes.length} led sectors</Tag>
        <Tag color="green">{totalUsers} visible users</Tag>
        {sectorData.map((s) => (
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
            <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>{s.chiefs.length} chiefs · {s.members.length} members</Typography.Text></div>
          </div>
        ))}
      </Flex>
      <div style={{
        minHeight: expanded ? 0 : 380,
        flex: expanded ? '1 1 auto' : undefined,
        border: `1px solid ${token.colorBorderSecondary}`,
        borderRadius: 8,
        background: 'linear-gradient(180deg, rgba(47,125,98,0.08), rgba(31,79,70,0.02))',
        overflow: 'hidden',
      }}>
        <ReactECharts option={graphOption(expanded)} style={{ height: expanded ? '100%' : 380 }} />
      </div>
      {sectorData.every((sector) => sector.items.length === 0) && (
        <Empty description="No visible team members yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}
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
          body: { height: '100vh', overflow: 'hidden' },
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
  const { t } = useTranslation()
  const { token } = antTheme.useToken()
  const user = useSessionStore((s) => s.user)
  const setUser = useSessionStore((s) => s.setUser)

  const me = useQuery({
    queryKey: ['me'],
    queryFn: getMe,
    staleTime: 60_000,
    enabled: !!user?.id,
  })

  useEffect(() => {
    if (!me.data) return
    setUser({
      id: me.data.user_id,
      username: me.data.username,
      email: me.data.email,
      firstName: me.data.first_name ?? undefined,
      lastName: me.data.last_name ?? undefined,
      createdAt: me.data.created_at,
      roles: me.data.roles,
      sectors: me.data.sectors.map((s) => ({ sectorCode: s.sector_code, role: s.role })),
      hasRootGroup: me.data.has_root_group,
    })
  }, [me.data, setUser])

  const recent = useQuery({
    queryKey: ['profile-recent', user?.id],
    queryFn: () => listTickets({ assignee_user_id: user?.id, limit: 5, sort_by: 'updated_at', sort_dir: 'desc' }),
    enabled: !!user?.id,
  })

  const overview = useQuery({
    queryKey: ['monitorOverview'],
    queryFn: () => getMonitorOverview(),
    staleTime: 60_000,
    enabled: !!user?.id,
  })

  if (!user) return <Empty description="Please log in" />

  const personal = overview.data?.personal
  const chiefSectors = Array.from(new Map(
    (user.sectors || [])
      .filter((s) => s.role === 'chief')
      .map((s) => [s.sectorCode, s]),
  ).values())

  return (
    <div style={{ padding: 24, display: 'grid', gap: 16 }}>
      <Flex justify="space-between" align="center">
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>Profile</Typography.Title>
          <Typography.Text type="secondary">Identity, roles, sectors, and personal workload</Typography.Text>
        </div>
        <TourInfoButton pageKey="profile" />
      </Flex>
      <Row gutter={[24, 24]}>
        {/* Identity card */}
        <Col xs={24} md={8} data-tour-id="profile-identity">
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
              <Descriptions.Item label="First Name">{user.firstName || '—'}</Descriptions.Item>
              <Descriptions.Item label="Last Name">{user.lastName || '—'}</Descriptions.Item>
              <Descriptions.Item label="Joined">{fmtDate(user.createdAt)}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>

        {/* Roles + KPIs */}
        <Col xs={24} md={16} data-tour-id="profile-roles">
          <div style={{ display: 'grid', gap: 24 }}>
            <Card title={<Space><SafetyCertificateOutlined /> Roles & Sectors</Space>}>
              <Space orientation="vertical" style={{ width: '100%' }} size={12}>
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
                          <Tag color={m.role === 'chief' ? 'gold' : 'cyan'} key={`${m.sectorCode}-${m.role}`}>
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
                <Col xs={12} md={6}><Statistic title="At-risk SLA" value={personal?.kpis?.sla_at_risk ?? '-'} styles={{ content: { color: '#fa8c16' } }} /></Col>
              </Row>
            </Card>
          </div>
        </Col>

        {/* Recent assignments */}
        <Col xs={24} lg={12} data-tour-id="profile-assignments">
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
        <Col xs={24} lg={12} data-tour-id="profile-status">
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
                    data: personal.by_status.map((b: { key: string; count: number }) => ({ name: b.key.replace(/_/g, ' '), value: b.count })),
                  }],
                }}
              />
            ) : <Empty description="No tickets yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
          </Card>
        </Col>

        {/* Chief-only: sector members graph */}
        {chiefSectors.length > 0 && (
          <Col xs={24}>
            <TeamsILead
              leadName={[user.firstName, user.lastName].filter(Boolean).join(' ') || user.username || 'You'}
              sectors={chiefSectors}
            />
          </Col>
        )}
      </Row>
      <ProductTour
        pageKey="profile"
        steps={[
          { target: '[data-tour-id="profile-identity"]', content: t('tour.profile.identity') },
          { target: '[data-tour-id="profile-roles"]', content: t('tour.profile.roles') },
          { target: '[data-tour-id="profile-assignments"]', content: t('tour.profile.assignments') },
          { target: '[data-tour-id="profile-status"]', content: t('tour.profile.status') },
        ]}
      />
    </div>
  )
}
