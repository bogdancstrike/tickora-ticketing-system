import { Tag } from 'antd'

const STATUS_COLORS: Record<string, string> = {
  pending: 'default',
  assigned_to_sector: 'processing',
  in_progress: 'blue',
  waiting_for_user: 'gold',
  on_hold: 'orange',
  done: 'green',
  closed: 'success',
  reopened: 'purple',
  cancelled: 'red',
  duplicate: 'red',
}

const STATUS_LABELS: Record<string, string> = {
  pending: 'Pending',
  assigned_to_sector: 'Assigned · Sector',
  in_progress: 'In Progress',
  waiting_for_user: 'Waiting · User',
  on_hold: 'On Hold',
  done: 'Done',
  closed: 'Closed',
  reopened: 'Reopened',
  cancelled: 'Cancelled',
  duplicate: 'Duplicate',
}

export function StatusTag({ status }: { status: string }) {
  return <Tag color={STATUS_COLORS[status] || 'default'}>{STATUS_LABELS[status] || status}</Tag>
}

export const STATUS_OPTIONS = Object.entries(STATUS_LABELS).map(([value, label]) => ({ value, label }))
