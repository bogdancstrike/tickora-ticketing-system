import { useEffect, useState } from 'react'
import { Badge, Button, Dropdown, List, Typography, Space, Empty } from 'antd'
import { BellOutlined } from '@ant-design/icons'
import { useSessionStore } from '@/stores/sessionStore'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5100'

export interface Notification {
  id: string
  type: string
  title: string
  body: string
  ticket_id?: string
  created_at: string
}

export function NotificationDropdown() {
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const user = useSessionStore(s => s.user)

  useEffect(() => {
    if (!user) return

    const eventSource = new EventSource(`${API_BASE}/api/notifications/stream`, {
      withCredentials: true,
    })

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'connection') return
      
      setNotifications(prev => [data, ...prev].slice(0, 10))
      setUnreadCount(prev => prev + 1)
    }

    eventSource.onerror = (err) => {
      console.error('SSE Error:', err)
      eventSource.close()
    }

    return () => {
      eventSource.close()
    }
  }, [user])

  const menu = (
    <div style={{
      width: 320,
      backgroundColor: 'var(--ant-color-bg-container)',
      boxShadow: '0 6px 16px 0 rgba(0, 0, 0, 0.08), 0 3px 6px -4px rgba(0, 0, 0, 0.12), 0 9px 28px 8px rgba(0, 0, 0, 0.05)',
      borderRadius: 8,
      overflow: 'hidden'
    }}>
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--ant-color-border-secondary)' }}>
        <Typography.Text strong>Notifications</Typography.Text>
      </div>
      <List
        size="small"
        dataSource={notifications}
        locale={{ emptyText: <Empty description="No new notifications" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
        renderItem={item => (
          <List.Item style={{ padding: '12px 16px' }}>
            <List.Item.Meta
              title={item.title}
              description={
                <Space direction="vertical" size={0}>
                  <Typography.Text type="secondary" size="small">{item.body}</Typography.Text>
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                    {new Date(item.created_at).toLocaleString()}
                  </Typography.Text>
                </Space>
              }
            />
          </List.Item>
        )}
        style={{ maxHeight: 400, overflow: 'auto' }}
      />
      {notifications.length > 0 && (
        <div style={{ padding: '8px 16px', borderTop: '1px solid var(--ant-color-border-secondary)', textAlign: 'center' }}>
          <Button type="link" size="small" onClick={() => { setNotifications([]); setUnreadCount(0); }}>
            Clear all
          </Button>
        </div>
      )}
    </div>
  )

  return (
    <Dropdown dropdownRender={() => menu} trigger={['click']} placement="bottomRight">
      <Badge count={unreadCount} offset={[-2, 10]} size="small">
        <Button type="text" icon={<BellOutlined />} onClick={() => setUnreadCount(0)} />
      </Badge>
    </Dropdown>
  )
}
