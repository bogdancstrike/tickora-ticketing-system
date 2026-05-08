import { useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import {
  ConfigProvider, Layout, Menu, theme as antTheme, Typography, Space, Button, Tooltip, Dropdown,
} from 'antd'
import {
  DashboardOutlined, UnorderedListOutlined, CheckSquareOutlined, AuditOutlined, SettingOutlined,
  BgColorsOutlined, MenuFoldOutlined, MenuUnfoldOutlined, UserOutlined, LogoutOutlined,
} from '@ant-design/icons'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useKeycloak } from '@react-keycloak/web'
import { useThemeStore } from '@/stores/themeStore'
import { useSessionStore } from '@/stores/sessionStore'
import { TicketDetailPage, TicketsPage } from '@/pages/TicketsPage'
import { AuditExplorerPage } from '@/pages/AuditExplorerPage'
import { CreateTicketPage } from '@/pages/CreateTicketPage'
import { ReviewTicketsPage } from '@/pages/ReviewTicketsPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { RequireRole } from '@/auth/RequireRole'
import { NotificationDropdown } from '@/components/common/NotificationDropdown'

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
    roles: [ROLE_ADMIN],
  },
]

function AppSidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { token } = antTheme.useToken()
  const [collapsed, setCollapsed] = useState(false)
  const hasAny = useSessionStore((s) => s.hasAny)
  const visibleItems = NAV_ITEMS.filter((item) => !item.roles || hasAny(item.roles))

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
        items={visibleItems}
        onClick={({ key }) => navigate(key)}
        style={{ borderRight: 0 }}
      />
    </Sider>
  )
}

function AppHeader() {
  const { token }   = antTheme.useToken()
  const { mode, toggle } = useThemeStore()
  const { keycloak } = useKeycloak()
  const user = useSessionStore((s) => s.user)

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
            items: [{
              key: 'logout', icon: <LogoutOutlined />, label: 'Logout',
              onClick: () => keycloak.logout(),
            }],
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

function PlaceholderPage({ title }: { title: string }) {
  return (
    <div style={{ padding: 24 }}>
      <Typography.Title level={3}>{title}</Typography.Title>
      <Typography.Paragraph type="secondary">
        This page is under construction.
      </Typography.Paragraph>
    </div>
  )
}

function Shell() {
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
            <Route
              path="/review"
              element={<RequireRole roles={[ROLE_ADMIN, ROLE_DISTRIBUTOR]}><ReviewTicketsPage /></RequireRole>}
            />
            <Route
              path="/audit"
              element={<RequireRole roles={[ROLE_ADMIN, ROLE_AUDITOR]}><AuditExplorerPage /></RequireRole>}
            />
            <Route
              path="/admin"
              element={<RequireRole roles={[ROLE_ADMIN]}><PlaceholderPage title="Admin" /></RequireRole>}
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
