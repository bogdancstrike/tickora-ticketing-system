import { ReactNode } from 'react'
import { Result } from 'antd'
import { useSessionStore } from '@/stores/sessionStore'

interface Props {
  roles: string[]
  children: ReactNode
}

export function RequireRole({ roles, children }: Props) {
  const hasAny = useSessionStore((s) => s.hasAny)
  if (!hasAny(roles)) {
    return (
      <Result
        status="403"
        title="403"
        subTitle="You do not have access to this page."
      />
    )
  }
  return <>{children}</>
}
