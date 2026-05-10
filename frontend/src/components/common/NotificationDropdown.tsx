import { useEffect, useState, useCallback, useMemo } from 'react'
import { Badge, Button, Dropdown, Empty, Space, Tag, Tooltip, Typography, theme as antTheme, notification } from 'antd'
import { BellOutlined, CheckOutlined, ThunderboltOutlined } from '@ant-design/icons'
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

/**
 * A global component for receiving and managing real-time notifications.
 * It maintains a persistent SSE (Server-Sent Events) connection to the backend to
 * receive live updates. It also handles notification persistence, read status tracking,
 * and provides navigation to relevant ticket pages.
 */
export function NotificationDropdown() {
  const [notifications, setNotifications] = useState<NotificationItem[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const user = useSessionStore((s) => s.user)
  const navigate = useNavigate()
  const { token } = antTheme.useToken()
  const [api, contextHolder] = notification.useNotification()

  const alertSound = useMemo(() => new Audio('/alert.mp3'), [])

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
    if (!user?.id) return

    let es: EventSource | null = null
    let cancelled = false

    /**
     * Establishes and manages the Server-Sent Events (SSE) connection for real-time notifications.
     * Uses a two-step handshake:
     * 1. POST to /stream-ticket to obtain a short-lived SSE token.
     * 2. Initialize EventSource with the obtained token.
     * Handles incoming messages, updates local state, and triggers UI alerts (notifications/sound).
     */
    const connectSSE = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/notifications/stream-ticket`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${getToken() || ''}` },
        })
        if (!response.ok || cancelled) return
        const { ticket } = await response.json()
        if (!ticket || cancelled) return

        es = new EventSource(`${API_BASE}/api/notifications/stream?sse_ticket=${ticket}`)

        es.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data) as NotificationItem & { type: string }
            if (data.type === 'connection') return
            
            setNotifications((prev) => [{ ...data, read: false }, ...prev].slice(0, 25))
            setUnreadCount((prev) => prev + 1)

            // Alert for new tickets (Distributors/Admins)
            if (data.type === 'ticket_created') {
              alertSound.play().catch(() => { /* user interaction required for some browsers */ })
              api.info({
                message: data.title || 'New Ticket',
                description: data.body,
                icon: <ThunderboltOutlined style={{ color: '#722ed1' }} />,
                placement: 'topRight',
                duration: 8,
                onClick: () => {
                   const dest = destinationFor(data, user?.roles || [])
                   if (dest) navigate(dest)
                }
              })
            }
          } catch (e) {
            // ignore malformed SSE frames
          }
        }
        es.onerror = () => {
          if (es) {
            es.close()
            es = null
          }
        }
      } catch (e) {
        // silent fail on connection errors
      }
    }

    connectSSE()

    return () => {
      cancelled = true
      if (es) es.close()
    }
  }, [user?.id, alertSound, api, navigate])

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

  const markOneRead = useCallback(async (item: NotificationItem) => {
    if (item.read) return
    setNotifications((prev) => prev.map((n) => n.id === item.id ? { ...n, read: true } : n))
    setUnreadCount((prev) => Math.max(0, prev - 1))
    try {
      await fetch(`${API_BASE}/api/notifications/${item.id}/mark-read`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getToken() || ''}`,
        },
      })
    } catch { /* silent */ }
  }, [])

  const onClickItem = (item: NotificationItem) => {
    markOneRead(item)
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
      <div style={{ maxHeight: 480, overflow: 'auto' }}>
        {notifications.map((item) => (
          <div
            key={item.id}
            onClick={() => onClickItem(item)}
            className="tickora-row-clickable"
            style={{
              padding: '10px 14px',
              cursor: item.ticket_id ? 'pointer' : 'default',
              background: item.read ? 'transparent' : token.colorPrimaryBg,
              borderInlineStart: item.read ? 'none' : `3px solid ${token.colorPrimary}`,
              borderBottom: `1px solid ${token.colorBorderSecondary}`,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'start',
              gap: 12
            }}
          >
            <div style={{ flex: 1 }}>
              <div style={{ marginBottom: 4 }}>
                <Space size={6} wrap>
                  <Tag color={TYPE_COLOR[item.type] || 'default'}>{item.type.replace(/_/g, ' ')}</Tag>
                  <Typography.Text strong>{item.title}</Typography.Text>
                </Space>
              </div>
              <div style={{ display: 'grid', gap: 2 }}>
                <Typography.Text type="secondary" style={{ fontSize: 13 }}>{item.body}</Typography.Text>
                <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                  {new Date(item.created_at).toLocaleString()}
                </Typography.Text>
              </div>
            </div>
            {!item.read && (
              <Tooltip key="read" title="Mark as read">
                <Button
                  size="small"
                  type="text"
                  icon={<CheckOutlined />}
                  onClick={(event) => {
                    event.stopPropagation()
                    markOneRead(item)
                  }}
                />
              </Tooltip>
            )}
          </div>
        ))}
        {notifications.length === 0 && (
          <div style={{ padding: 20 }}>
            <Empty description="No notifications" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          </div>
        )}
      </div>
    </div>
  )

  return (
    <>
      {contextHolder}
      <Dropdown popupRender={() => menu} trigger={['click']} placement="bottomRight">
        <Badge count={unreadCount} offset={[-2, 10]} size="small">
          <Button type="text" icon={<BellOutlined />} onClick={() => { /* badge cleared via mark-read */ }} />
        </Badge>
      </Dropdown>
    </>
  )
}
