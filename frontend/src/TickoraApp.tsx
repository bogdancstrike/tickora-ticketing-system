import { useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import {
  ConfigProvider, Layout, Menu, theme as antTheme, Typography, Space, Button, Tooltip, Dropdown,
} from 'antd'
import {
  DashboardOutlined, UnorderedListOutlined, PlusOutlined, AuditOutlined, SettingOutlined,
  BgColorsOutlined, MenuFoldOutlined, MenuUnfoldOutlined, UserOutlined, LogoutOutlined,
} from '@ant-design/icons'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useKeycloak } from '@react-keycloak/web'
import { useThemeStore } from '@/stores/themeStore'
import { useSessionStore } from '@/stores/sessionStore'
import { TicketsPage } from '@/pages/TicketsPage'
import { AuditExplorerPage } from '@/pages/AuditExplorerPage'
import { CreateTicketPage } from '@/pages/CreateTicketPage'

const { Header, Sider, Content } = Layout
const { Text } = Typography

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

const NAV_ITEMS = [
  { key: '/dashboard', label: 'Dashboard',     icon: <DashboardOutlined /> },
  { key: '/tickets',   label: 'Tickets',       icon: <UnorderedListOutlined /> },
  { key: '/create',    label: 'Create Ticket', icon: <PlusOutlined /> },
  { key: '/audit',     label: 'Audit',         icon: <AuditOutlined /> },
  { key: '/admin',     label: 'Admin',         icon: <SettingOutlined /> },
]

function AppSidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { token } = antTheme.useToken()
  const [collapsed, setCollapsed] = useState(false)

  const selectedKey = NAV_ITEMS.find((n) => location.pathname.startsWith(n.key))?.key || '/dashboard'

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
        items={NAV_ITEMS}
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
            <Route path="/dashboard" element={<PlaceholderPage title="Dashboard" />} />
            <Route path="/tickets"   element={<TicketsPage />} />
            <Route path="/tickets/:ticketId" element={<TicketsPage />} />
            <Route path="/create"    element={<CreateTicketPage />} />
            <Route path="/audit"     element={<AuditExplorerPage />} />
            <Route path="/admin"     element={<PlaceholderPage title="Admin" />} />
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
