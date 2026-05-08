import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import dayjs from 'dayjs'
import { Alert, Button, Empty, Flex, Form, Input, Space, Table, Tag, Typography, Descriptions, Card, DatePicker, theme as antTheme } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import type { FilterValue, SorterResult } from 'antd/es/table/interface'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { listAudit, type AuditEventDto } from '@/api/tickets'

const { RangePicker } = DatePicker

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
  const [params, setParams] = useState<any>({ sort_by: 'created_at', sort_dir: 'desc' })
  const audit = useQuery({
    queryKey: ['audit', params],
    queryFn: () => listAudit({ ...params, limit: 200 }),
  })

  const columns: ColumnsType<AuditEventDto> = useMemo(() => [
    { 
      title: 'Time', 
      dataIndex: 'created_at', 
      width: 180, 
      render: fmt,
      sorter: true,
      defaultSortOrder: 'descend',
    },
    { title: 'Action', dataIndex: 'action', width: 220, render: (v) => <Tag color="blue">{v}</Tag>, sorter: true },
    { title: 'Actor', dataIndex: 'actor_username', width: 170, render: (v, row) => v || row.actor_user_id || '-', sorter: true },
    { title: 'Entity', width: 180, render: (_, row) => `${row.entity_type}:${row.entity_id || '-'}` },
    { 
      title: 'Ticket ID', 
      dataIndex: 'ticket_id', 
      width: 240, 
      ellipsis: true,
      render: (tid) => tid ? <Link to={`/tickets/${tid}`}>{tid}</Link> : '-'
    },
    { title: 'Correlation', dataIndex: 'correlation_id', width: 220, ellipsis: true },
  ], [])

  const handleTableChange = (
    _pagination: TablePaginationConfig,
    _filters: Record<string, FilterValue | null>,
    sorter: SorterResult<AuditEventDto> | SorterResult<AuditEventDto>[]
  ) => {
    const s = Array.isArray(sorter) ? sorter[0] : sorter
    if (s.field) {
      setParams((prev: any) => ({
        ...prev,
        sort_by: s.field,
        sort_dir: s.order === 'ascend' ? 'asc' : 'desc'
      }))
    }
  }

  const onFilter = (values: any) => {
    const { range, ...rest } = values
    const newParams = { ...params, ...rest }
    if (range) {
      newParams.created_after = range[0].startOf('day').toISOString()
      newParams.created_before = range[1].endOf('day').toISOString()
    } else {
      delete newParams.created_after
      delete newParams.created_before
    }
    // Remove empty strings
    Object.keys(newParams).forEach(k => {
      if (newParams[k] === '') delete newParams[k]
    })
    setParams(newParams)
  }

  return (
    <div style={{ padding: 24, display: 'grid', gap: 16 }}>
      <Flex justify="space-between" align="center" wrap="wrap" gap={12}>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>Audit Explorer</Typography.Title>
          <Typography.Text type="secondary">Global audit ledger for admins and auditors</Typography.Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => audit.refetch()} />
      </Flex>

      <Form layout="inline" onFinish={onFilter}>
        <Form.Item name="range"><RangePicker /></Form.Item>
        <Form.Item name="action"><Input allowClear placeholder="Action" /></Form.Item>
        <Form.Item name="actor_username"><Input allowClear placeholder="username" /></Form.Item>
        <Form.Item name="ticket_id"><Input allowClear placeholder="Ticket ID" /></Form.Item>
        <Form.Item>
          <Space>
            <Button htmlType="submit" type="primary" icon={<SearchOutlined />}>Filter</Button>
            <Button onClick={() => setParams({ sort_by: 'created_at', sort_dir: 'desc' })}>Clear</Button>
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
          onChange={handleTableChange}
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
