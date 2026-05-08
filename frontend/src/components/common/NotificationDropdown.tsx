import { useEffect, useState, useCallback } from 'react'
import { Badge, Button, Dropdown, Empty, List, Space, Tag, Typography, theme as antTheme } from 'antd'
import { BellOutlined, CheckOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useSessionStore } from '@/stores/sessionStore'
import { API_BASE, getToken } from '@/api/client'

export interface NotificationItem {
  id: string
  type: string
  title: string
  body: string
  ticket_id?: string | null
  created_at: string
  read?: boolean
}

const TYPE_COLOR: Record<string, string> = {
  ticket_created:    'blue',
  sector_assigned:   'cyan',
  ticket_assigned:   'purple',
  ticket_unassigned: 'orange',
  status_changed:    'green',
  comment_created:   'geekblue',
  sla_approaching:   'orange',
  sla_breached:      'red',
}

function destinationFor(item: NotificationItem, roles: string[]): string | null {
  if (!item.ticket_id) return null
  // Distributor / admin landing on a sector_assigned/ticket_created → review page
  if (
    (item.type === 'ticket_created' || item.type === 'sector_assigned') &&
    (roles.includes('tickora_admin') || roles.includes('tickora_distributor'))
  ) {
    return `/review/${item.ticket_id}`
  }
  return `/tickets/${item.ticket_id}`
}

export function NotificationDropdown() {
  const [notifications, setNotifications] = useState<NotificationItem[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const user = useSessionStore((s) => s.user)
  const navigate = useNavigate()
  const { token } = antTheme.useToken()

  // Initial load: fetch persisted notifications via REST
  useEffect(() => {
    if (!user?.id) return
    let cancelled = false
    fetch(`${API_BASE}/api/notifications`, {
      headers: { Authorization: `Bearer ${getToken() || ''}` },
    })
      .then((r) => (r.ok ? r.json() : { items: [] }))
      .then((data) => {
        if (cancelled) return
        const items: NotificationItem[] = data.items || []
        setNotifications(items.slice(0, 25))
        setUnreadCount(items.filter((n) => !n.read).length)
      })
      .catch(() => { /* silent */ })
    return () => { cancelled = true }
  }, [user?.id])

  // Live SSE
  useEffect(() => {
    const accessToken = getToken()
    if (!user?.id || !accessToken) return

    const es = new EventSource(`${API_BASE}/api/notifications/stream?access_token=${accessToken}`)

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as NotificationItem & { type: string }
        if (data.type === 'connection') return
        setNotifications((prev) => [{ ...data, read: false }, ...prev].slice(0, 25))
        setUnreadCount((prev) => prev + 1)
      } catch (e) {
        // ignore malformed SSE frames
      }
    }
    es.onerror = () => es.close()
    return () => es.close()
  }, [user?.id])

  const markAllRead = useCallback(async () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })))
    setUnreadCount(0)
    try {
      await fetch(`${API_BASE}/api/notifications/mark-read`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getToken() || ''}`,
        },
      })
    } catch { /* silent */ }
  }, [])

  const onClickItem = (item: NotificationItem) => {
    const dest = destinationFor(item, user?.roles || [])
    if (dest) navigate(dest)
  }

  const menu = (
    <div style={{
      width: 360,
      backgroundColor: token.colorBgElevated,
      boxShadow: token.boxShadowSecondary,
      borderRadius: 8,
      overflow: 'hidden',
      border: `1px solid ${token.colorBorderSecondary}`,
    }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '10px 14px', borderBottom: `1px solid ${token.colorBorderSecondary}`,
      }}>
        <Typography.Text strong>Notifications</Typography.Text>
        {notifications.length > 0 && (
          <Button type="text" size="small" icon={<CheckOutlined />} onClick={markAllRead}>
            Mark all read
          </Button>
        )}
      </div>
      <List
        size="small"
        dataSource={notifications}
        locale={{ emptyText: <Empty description="No notifications" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
        renderItem={(item) => (
          <List.Item
            onClick={() => onClickItem(item)}
            style={{
              padding: '10px 14px',
              cursor: item.ticket_id ? 'pointer' : 'default',
              background: item.read ? 'transparent' : token.colorPrimaryBg,
              borderInlineStart: item.read ? 'none' : `3px solid ${token.colorPrimary}`,
            }}
          >
            <List.Item.Meta
              title={
                <Space size={6}>
                  <Tag color={TYPE_COLOR[item.type] || 'default'}>{item.type.replace(/_/g, ' ')}</Tag>
                  <Typography.Text strong>{item.title}</Typography.Text>
                </Space>
              }
              description={
                <Space direction="vertical" size={0} style={{ width: '100%' }}>
                  <Typography.Text type="secondary">{item.body}</Typography.Text>
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                    {new Date(item.created_at).toLocaleString()}
                  </Typography.Text>
                </Space>
              }
            />
          </List.Item>
        )}
        style={{ maxHeight: 480, overflow: 'auto' }}
      />
    </div>
  )

  return (
    <Dropdown dropdownRender={() => menu} trigger={['click']} placement="bottomRight">
      <Badge count={unreadCount} offset={[-2, 10]} size="small">
        <Button type="text" icon={<BellOutlined />} onClick={() => { /* badge cleared via mark-read */ }} />
      </Badge>
    </Dropdown>
  )
}
