import { useQuery } from '@tanstack/react-query'
import { Card, Descriptions, Row, Col, Statistic, Tag, Typography, Space, List, Empty } from 'antd'
import { UserOutlined, MailOutlined, SafetyCertificateOutlined, TeamOutlined } from '@ant-design/icons'
import { useSessionStore } from '@/stores/sessionStore'
import { listTickets } from '@/api/tickets'

export function ProfilePage() {
  const user = useSessionStore(s => s.user)
  
  const myTickets = useQuery({
    queryKey: ['my-tickets-stats'],
    queryFn: () => listTickets({ assignee_user_id: user?.id, limit: 1 }),
    enabled: !!user?.id
  })

  if (!user) return <Empty description="Please log in" />

  return (
    <div style={{ padding: 24 }}>
      <Row gutter={[24, 24]}>
        <Col xs={24} md={8}>
          <Card 
            cover={
              <div style={{ 
                height: 160, 
                background: 'linear-gradient(135deg, #1677ff 0%, #003eb3 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                <UserOutlined style={{ fontSize: 64, color: '#fff' }} />
              </div>
            }
          >
            <Card.Meta 
              title={<Typography.Title level={4}>{user.firstName} {user.lastName}</Typography.Title>}
              description={
                <Space direction="vertical">
                  <Typography.Text><MailOutlined /> {user.email || 'No email'}</Typography.Text>
                  <Typography.Text type="secondary">ID: {user.id}</Typography.Text>
                </Space>
              }
            />
          </Card>
        </Col>
        
        <Col xs={24} md={16}>
          <div style={{ display: 'grid', gap: 24 }}>
            <Card title="Role & Permissions">
              <Space direction="vertical" style={{ width: '100%' }}>
                <div>
                  <Typography.Text strong><SafetyCertificateOutlined /> Global Roles</Typography.Text>
                  <div style={{ marginTop: 8 }}>
                    {user.roles.map(role => (
                      <Tag color="blue" key={role}>{role.replace('tickora_', '').toUpperCase()}</Tag>
                    ))}
                  </div>
                </div>
                
                <div style={{ marginTop: 16 }}>
                  <Typography.Text strong><TeamOutlined /> Sector Memberships</Typography.Text>
                  <div style={{ marginTop: 8 }}>
                    {user.sectors?.length ? user.sectors.map(m => (
                      <Tag color="cyan" key={m.sectorCode}>{m.sectorCode} ({m.role})</Tag>
                    )) : <Typography.Text type="secondary">No specific sector assignments</Typography.Text>}
                  </div>
                </div>
              </Space>
            </Card>

            <Card title="Activity Overview">
              <Row gutter={16}>
                <Col span={12}>
                  <Statistic 
                    title="Active Assignments" 
                    value={myTickets.data?.items?.length || 0} 
                    suffix={myTickets.isLoading ? '...' : ''}
                  />
                </Col>
              </Row>
            </Card>
          </div>
        </Col>
      </Row>
    </div>
  )
}
