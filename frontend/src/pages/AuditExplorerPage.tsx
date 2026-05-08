import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { Alert, Button, Empty, Flex, Form, Input, Space, Table, Tag, Typography, Descriptions, Card, theme as antTheme } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { listAudit, type AuditEventDto } from '@/api/tickets'

function fmt(value?: string | null) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'
}

function AuditValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <Typography.Text type="secondary">null</Typography.Text>
  if (typeof value === 'object') {
    return <pre style={{ margin: 0, fontSize: 12 }}>{JSON.stringify(value, null, 2)}</pre>
  }
  return String(value)
}

export function AuditExplorerPage() {
  const { token } = antTheme.useToken()
  const [filters, setFilters] = useState<Record<string, string>>({})
  const audit = useQuery({
    queryKey: ['audit', filters],
    queryFn: () => listAudit({ ...filters, limit: 200 }),
  })

  const columns: ColumnsType<AuditEventDto> = useMemo(() => [
    { title: 'Time', dataIndex: 'created_at', width: 180, render: fmt },
    { title: 'Action', dataIndex: 'action', width: 220, render: (v) => <Tag color="blue">{v}</Tag> },
    { title: 'Actor', dataIndex: 'actor_username', width: 170, render: (v, row) => v || row.actor_user_id || '-' },
    { title: 'Entity', width: 180, render: (_, row) => `${row.entity_type}:${row.entity_id || '-'}` },
    { title: 'Ticket', dataIndex: 'ticket_id', width: 240, ellipsis: true },
    { title: 'Correlation', dataIndex: 'correlation_id', width: 220, ellipsis: true },
  ], [])

  return (
    <div style={{ padding: 24, display: 'grid', gap: 16 }}>
      <Flex justify="space-between" align="center" wrap="wrap" gap={12}>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>Audit Explorer</Typography.Title>
          <Typography.Text type="secondary">Global audit ledger for admins and auditors</Typography.Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => audit.refetch()} />
      </Flex>

      <Form
        layout="inline"
        onFinish={(values) => {
          setFilters(Object.fromEntries(Object.entries(values).filter(([, v]) => !!v)) as Record<string, string>)
        }}
      >
        <Form.Item name="action"><Input allowClear placeholder="Action" /></Form.Item>
        <Form.Item name="actor_user_id"><Input allowClear placeholder="Actor user ID" /></Form.Item>
        <Form.Item name="ticket_id"><Input allowClear placeholder="Ticket ID" /></Form.Item>
        <Form.Item name="correlation_id"><Input allowClear placeholder="Correlation ID" /></Form.Item>
        <Form.Item>
          <Space>
            <Button htmlType="submit" type="primary" icon={<SearchOutlined />}>Filter</Button>
            <Button onClick={() => setFilters({})}>Clear</Button>
          </Space>
        </Form.Item>
      </Form>

      {audit.error && <Alert type="error" showIcon message={audit.error.message} />}
      <div style={{ border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 8, overflow: 'hidden' }}>
        <Table
          rowKey="id"
          loading={audit.isLoading}
          columns={columns}
          dataSource={audit.data?.items || []}
          expandable={{
            expandedRowRender: (row) => (
              <Card size="small" style={{ background: token.colorBgLayout }}>
                <Descriptions bordered size="small" column={1}>
                  {row.old_value && (
                    <Descriptions.Item label="Old Value">
                      <AuditValue value={row.old_value} />
                    </Descriptions.Item>
                  )}
                  {row.new_value && (
                    <Descriptions.Item label="New Value">
                      <AuditValue value={row.new_value} />
                    </Descriptions.Item>
                  )}
                  {row.metadata && (
                    <Descriptions.Item label="Metadata">
                      <AuditValue value={row.metadata} />
                    </Descriptions.Item>
                  )}
                  <Descriptions.Item label="Request Details">
                    <Space direction="vertical">
                      <Typography.Text type="secondary">IP: {row.metadata?.request_ip || '-'}</Typography.Text>
                      <Typography.Text type="secondary" style={{ fontSize: 11 }}>Agent: {row.metadata?.user_agent || '-'}</Typography.Text>
                    </Space>
                  </Descriptions.Item>
                </Descriptions>
              </Card>
            ),
          }}
          pagination={{ pageSize: 25 }}
          locale={{ emptyText: <Empty description="No audit events" /> }}
          scroll={{ x: 1200 }}
        />
      </div>
    </div>
  )
}
