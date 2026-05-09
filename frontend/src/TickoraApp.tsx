import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import {
  ConfigProvider, Layout, Menu, theme as antTheme, Typography, Space, Button, Tooltip, Dropdown, Grid, Drawer,
} from 'antd'
import {
  DashboardOutlined, UnorderedListOutlined, CheckSquareOutlined, AuditOutlined, SettingOutlined,
  BgColorsOutlined, MenuFoldOutlined, MenuUnfoldOutlined, UserOutlined, LogoutOutlined,
  IdcardOutlined,
} from '@ant-design/icons'
import { useQuery, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useKeycloak } from '@react-keycloak/web'
import { useThemeStore } from '@/stores/themeStore'
import { useSessionStore } from '@/stores/sessionStore'
import { TicketDetailPage, TicketsPage } from '@/pages/TicketsPage'
import { AuditExplorerPage } from '@/pages/AuditExplorerPage'
import { CreateTicketPage } from '@/pages/CreateTicketPage'
import { ReviewTicketsPage } from '@/pages/ReviewTicketsPage'
import { ReviewTicketPage } from '@/pages/ReviewTicketPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { ProfilePage } from '@/pages/ProfilePage'
import { AdminPage } from '@/pages/AdminPage'
import { RequireRole } from '@/auth/RequireRole'
import { NotificationDropdown } from '@/components/common/NotificationDropdown'
import { getMe } from '@/api/tickets'

const { Header, Sider, Content } = Layout
const { Text } = Typography

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

const ROLE_ADMIN = 'tickora_admin'
const ROLE_AUDITOR = 'tickora_auditor'
const ROLE_DISTRIBUTOR = 'tickora_distributor'

const NAV_ITEMS = [
  { key: '/dashboard', label: 'Dashboard', icon: <DashboardOutlined /> },
  { key: '/tickets', label: 'Tickets', icon: <UnorderedListOutlined /> },
  {
    key: '/review',
    label: 'Review Tickets',
    icon: <CheckSquareOutlined />,
    roles: [ROLE_ADMIN, ROLE_DISTRIBUTOR],
  },
  {
    key: '/audit',
    label: 'Audit',
    icon: <AuditOutlined />,
    roles: [ROLE_ADMIN, ROLE_AUDITOR],
  },
  {
    key: '/admin',
    label: 'Admin',
    icon: <SettingOutlined />,
    rootOnly: true,
  },
]

function AppSidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { token } = antTheme.useToken()
  const [collapsed, setCollapsed] = useState(false)
  const hasAny = useSessionStore((s) => s.hasAny)
  const user = useSessionStore((s) => s.user)
  const visibleItems = NAV_ITEMS.filter((item) => {
    if ('rootOnly' in item && item.rootOnly) return !!user?.hasRootGroup
    return !item.roles || hasAny(item.roles)
  })

  const selectedKey = visibleItems.find((n) => location.pathname.startsWith(n.key))?.key || '/dashboard'

  return (
    <Sider
      collapsible
      collapsed={collapsed}
      onCollapse={setCollapsed}
      trigger={null}
      width={220}
      style={{ background: token.colorBgContainer, borderRight: `1px solid ${token.colorBorder}` }}
    >
      <div style={{
        height: 56, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 16px', borderBottom: `1px solid ${token.colorBorder}`,
      }}>
        {!collapsed && <Text strong style={{ fontSize: 18 }}>Tickora</Text>}
        <Button type="text" icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                onClick={() => setCollapsed(!collapsed)} />
      </div>
      <Menu
        mode="inline"
        selectedKeys={[selectedKey]}
        items={visibleItems.map(({ roles: _, rootOnly: __, ...rest }) => rest)}
        onClick={({ key }) => navigate(key)}
        style={{ borderRight: 0 }}
      />
    </Sider>
  )
}

function RequireRootGroup({ children }: { children: ReactNode }) {
  const user = useSessionStore((s) => s.user)
  if (!user?.hasRootGroup) {
    return <Typography.Title level={3} style={{ padding: 24 }}>403 · Root Tickora access required</Typography.Title>
  }
  return <>{children}</>
}

function AppHeader() {
  const { token }   = antTheme.useToken()
  const { mode, toggle } = useThemeStore()
  const { keycloak } = useKeycloak()
  const user = useSessionStore((s) => s.user)
  const navigate = useNavigate()

  return (
    <Header style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 16px', background: token.colorBgContainer,
      borderBottom: `1px solid ${token.colorBorder}`,
    }}>
      <Text type="secondary">Ticketing · Tasking · Distribution</Text>
      <Space>
        <NotificationDropdown />
        <Tooltip title={`Switch to ${mode === 'dark' ? 'light' : 'dark'} mode`}>
          <Button type="text" icon={<BgColorsOutlined />} onClick={toggle} />
        </Tooltip>
        <Dropdown
          menu={{
            items: [
              {
                key: 'profile', icon: <IdcardOutlined />, label: 'My Profile',
                onClick: () => navigate('/profile'),
              },
              { type: 'divider' as const },
              {
                key: 'logout', icon: <LogoutOutlined />, label: 'Logout',
                onClick: () => keycloak.logout(),
              },
            ],
          }}
        >
          <Button type="text" icon={<UserOutlined />}>
            {user?.username || user?.email || 'user'}
          </Button>
        </Dropdown>
      </Space>
    </Header>
  )
}

function useBackendSessionBootstrap() {
  const setUser = useSessionStore((s) => s.setUser)
  const query = useQuery({
    queryKey: ['me'],
    queryFn: getMe,
    staleTime: 60_000,
    retry: 1,
  })

  useEffect(() => {
    if (!query.data) return
    setUser({
      id: query.data.user_id,
      username: query.data.username,
      email: query.data.email,
      firstName: query.data.first_name,
      lastName: query.data.last_name,
      createdAt: query.data.created_at,
      roles: query.data.roles,
      sectors: query.data.sectors.map((s) => ({ sectorCode: s.sector_code, role: s.role })),
      hasRootGroup: query.data.has_root_group,
    })
  }, [query.data, setUser])
}

function Shell() {
  useBackendSessionBootstrap()
  return (
    <Layout style={{ height: '100vh' }}>
      <AppSidebar />
      <Layout>
        <AppHeader />
        <Content style={{ overflow: 'auto' }}>
          <Routes>
            <Route path="/"          element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/tickets"   element={<TicketsPage />} />
            <Route path="/tickets/:ticketId" element={<TicketDetailPage />} />
            <Route path="/create"    element={<CreateTicketPage />} />
            <Route path="/profile"   element={<ProfilePage />} />
            <Route
              path="/review"
              element={<RequireRole roles={[ROLE_ADMIN, ROLE_DISTRIBUTOR]}><ReviewTicketsPage /></RequireRole>}
            />
            <Route
              path="/review/:ticketId"
              element={<RequireRole roles={[ROLE_ADMIN, ROLE_DISTRIBUTOR]}><ReviewTicketPage /></RequireRole>}
            />
            <Route
              path="/audit"
              element={<RequireRole roles={[ROLE_ADMIN, ROLE_AUDITOR]}><AuditExplorerPage /></RequireRole>}
            />
            <Route
              path="/admin"
              element={<RequireRootGroup><AdminPage /></RequireRootGroup>}
            />
            <Route path="*"          element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}

export function TickoraApp() {
  const { mode } = useThemeStore()
  const { initialized } = useKeycloak()

  if (!initialized) {
    return (
      <div style={{ height: '100vh', display: 'grid', placeItems: 'center' }}>
        <Text type="secondary">Loading…</Text>
      </div>
    )
  }

  return (
    <ConfigProvider
      theme={{
        algorithm: mode === 'dark' ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm,
        token: { borderRadius: 6 },
      }}
    >
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Shell />
        </BrowserRouter>
      </QueryClientProvider>
    </ConfigProvider>
  )
}
