import { Tag } from 'antd'
import { BankOutlined, GlobalOutlined, QuestionOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'

const TYPES: Record<string, { color: string; icon: React.ReactNode; key: string }> = {
  internal: { color: 'geekblue', icon: <BankOutlined />,   key: 'beneficiary_type.internal' },
  external: { color: 'magenta',  icon: <GlobalOutlined />, key: 'beneficiary_type.external' },
}

export const BENEFICIARY_TYPE_OPTIONS = [
  { label: 'Internal', value: 'internal' },
  { label: 'External', value: 'external' },
]

export function BeneficiaryTypeTag({ type }: { type: string | null | undefined }) {
  const { t } = useTranslation()
  if (!type) return null
  const meta = TYPES[type] || { color: 'default', icon: <QuestionOutlined />, key: '' }
  const label = meta.key ? t(meta.key) : type.toUpperCase()
  return <Tag color={meta.color} icon={meta.icon} style={{ textTransform: 'uppercase' }}>{label}</Tag>
}
