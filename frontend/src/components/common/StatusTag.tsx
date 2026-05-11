import { Tag } from 'antd'

const STATUS_COLORS: Record<string, string> = {
  pending: 'default',
  assigned_to_sector: 'processing',
  in_progress: 'blue',
  done: 'green',
  cancelled: 'red',
}

const STATUS_LABELS: Record<string, string> = {
  pending: 'Pending',
  assigned_to_sector: 'Assigned · Sector',
  in_progress: 'In Progress',
  done: 'Done',
  cancelled: 'Cancelled',
}

export function StatusTag({ status }: { status: string }) {
  return <Tag color={STATUS_COLORS[status] || 'default'}>{STATUS_LABELS[status] || status}</Tag>
}

export const STATUS_OPTIONS = Object.entries(STATUS_LABELS).map(([value, label]) => ({ value, label }))
