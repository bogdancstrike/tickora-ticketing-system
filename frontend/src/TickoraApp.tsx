import { useEffect, useState, useMemo } from 'react'
import type { ReactNode } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import {
  ConfigProvider, Layout, Menu, theme as antTheme, Typography, Space, Button, Tooltip, Dropdown, Grid, Drawer,
} from 'antd'
import {
  LineChartOutlined, UnorderedListOutlined, CheckSquareOutlined, AuditOutlined, SettingOutlined,
  BgColorsOutlined, MenuFoldOutlined, MenuUnfoldOutlined, UserOutlined, LogoutOutlined,
  IdcardOutlined, AppstoreOutlined, MenuOutlined,
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
import { MonitorPage } from '@/pages/MonitorPage'
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
  // Ticketing section
  { key: '/tickets', label: 'Tickets', icon: <UnorderedListOutlined />, section: 'ticketing' },
  {
    key: '/review',
    label: 'Review Tickets',
    icon: <CheckSquareOutlined />,
    roles: [ROLE_ADMIN, ROLE_DISTRIBUTOR],
    section: 'ticketing',
  },
  
  // Monitoring section
  { key: '/monitor', label: 'Monitor', icon: <LineChartOutlined />, section: 'monitoring' },
  { key: '/dashboard', label: 'Dashboard', icon: <AppstoreOutlined />, section: 'monitoring' },

  // Administration section
  {
    key: '/audit',
    label: 'Audit',
    icon: <AuditOutlined />,
    roles: [ROLE_ADMIN, ROLE_AUDITOR],
    section: 'admin',
  },
  {
    key: '/admin',
    label: 'Admin',
    icon: <SettingOutlined />,
    rootOnly: true,
    section: 'admin',
  },
]

function useNavigationItems() {
  const hasAny = useSessionStore((s) => s.hasAny)
  const user = useSessionStore((s) => s.user)
  
  const visibleItems = useMemo(() => {
    return NAV_ITEMS.filter((item) => {
      if ('rootOnly' in item && item.rootOnly) return !!user?.hasRootGroup
      if (item.key === '/dashboard' && user?.roles.includes('tickora_beneficiary') && !user?.roles.some(r => [ROLE_ADMIN, ROLE_DISTRIBUTOR, ROLE_AUDITOR].includes(r))) {
          // Hide customizable dashboard for pure beneficiaries
          return false
      }
      return !item.roles || hasAny(item.roles)
    })
  }, [user, hasAny])

  const menuItems = useMemo(() => {
    const ticketing = visibleItems.filter(i => i.section === 'ticketing')
    const monitoring = visibleItems.filter(i => i.section === 'monitoring')
    const admin = visibleItems.filter(i => i.section === 'admin')
    
    const items: any[] = []
    if (ticketing.length) {
      items.push(...ticketing.map(({ section: _, roles: __, rootOnly: ___, ...rest }) => rest))
    }
    if (ticketing.length && (monitoring.length || admin.length)) {
      items.push({ type: 'divider', key: 'div-1' })
    }
    if (monitoring.length) {
      items.push(...monitoring.map(({ section: _, roles: __, rootOnly: ___, ...rest }) => rest))
    }
    if (monitoring.length && admin.length) {
      items.push({ type: 'divider', key: 'div-2' })
    }
    if (admin.length) {
      items.push(...admin.map(({ section: _, roles: __, rootOnly: ___, ...rest }) => rest))
    }
    return items
  }, [visibleItems])

  return { visibleItems, menuItems }
}

function AppSidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { token } = antTheme.useToken()
  const [collapsed, setCollapsed] = useState(false)
  const screens = Grid.useBreakpoint()
  const { visibleItems, menuItems } = useNavigationItems()
  
  const isMobile = !screens.md
  const selectedKey = visibleItems.find((n) => location.pathname.startsWith(n.key))?.key || '/tickets'

  if (isMobile) return null

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
        height: 100, display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: '10px', borderBottom: `1px solid ${token.colorBorder}`,
      }}>
        {collapsed ? (
          <img src="/logo.png" alt="Tickora" style={{ width: 80, height: 80, cursor: 'pointer', objectFit: 'contain' }} onClick={() => navigate('/tickets')} />
        ) : (
          <img src="/logo_text.png" alt="Tickora" style={{ height: 80, maxWidth: '100%', cursor: 'pointer', objectFit: 'contain' }} onClick={() => navigate('/tickets')} />
        )}
      </div>
      <div style={{ padding: '4px 8px', textAlign: 'right' }}>
        <Button type="text" icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                onClick={() => setCollapsed(!collapsed)} />
      </div>
      <Menu
        mode="inline"
        selectedKeys={[selectedKey]}
        items={menuItems}
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
  const location = useLocation()
  const screens = Grid.useBreakpoint()
  const [drawerVisible, setDrawerDrawerVisible] = useState(false)
  const { visibleItems, menuItems } = useNavigationItems()

  const isMobile = !screens.md
  const selectedKey = visibleItems.find((n) => location.pathname.startsWith(n.key))?.key || '/tickets'

  return (
    <Header style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 16px', background: token.colorBgContainer,
      height: isMobile ? 100 : 64,
      borderBottom: `1px solid ${token.colorBorder}`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        {isMobile && (
          <>
            <Button type="text" icon={<MenuOutlined />} onClick={() => setDrawerDrawerVisible(true)} />
            <img src="/logo_text.png" alt="Tickora" style={{ height: 60, cursor: 'pointer' }} onClick={() => navigate('/tickets')} />
          </>
        )}
        {!isMobile && (
          <>
            <img src="/logo.png" alt="Tickora" style={{ height: 48, marginRight: 12 }} />
            <Text type="secondary">Ticketing · Tasking · Distribution</Text>
          </>
        )}
      </div>

      <Drawer
        title={<img src="/logo_text.png" alt="Tickora" style={{ height: 32 }} />}
        placement="left"
        onClose={() => setDrawerDrawerVisible(false)}
        open={drawerVisible}
        styles={{ body: { padding: 0 } }}
        size="default"
      >
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => {
            navigate(key)
            setDrawerDrawerVisible(false)
          }}
          style={{ borderRight: 0 }}
        />
      </Drawer>

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
            {!isMobile && (user?.username || user?.email || 'user')}
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
            <Route path="/"          element={<Navigate to="/tickets" replace />} />
            <Route path="/monitor"   element={<MonitorPage />} />
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
            <Route path="*"          element={<Navigate to="/tickets" replace />} />
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
