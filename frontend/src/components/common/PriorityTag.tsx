import { Tag } from 'antd'
import {
  ArrowDownOutlined, ArrowUpOutlined, FireOutlined, MinusOutlined,
} from '@ant-design/icons'

const PRIORITY: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  low:      { color: 'default', icon: <ArrowDownOutlined />, label: 'Low' },
  medium:   { color: 'blue',    icon: <MinusOutlined />,     label: 'Medium' },
  high:     { color: 'orange',  icon: <ArrowUpOutlined />,   label: 'High' },
  critical: { color: 'red',     icon: <FireOutlined />,      label: 'Critical' },
}

export const PRIORITY_OPTIONS = Object.keys(PRIORITY).map(key => ({
  label: PRIORITY[key].label,
  value: key
}))

export function PriorityTag({ priority }: { priority: string }) {
  const meta = PRIORITY[priority] || { color: 'default', icon: null, label: priority }
  return <Tag color={meta.color} icon={meta.icon}>{meta.label}</Tag>
}
