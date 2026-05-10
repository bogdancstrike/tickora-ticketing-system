/**
 * Watch / unwatch toggle for a ticket.
 *
 * Drops into any ticket toolbar; talks to `/api/tickets/<id>/watchers`.
 * Watchers receive the same notifications as assignees on visible
 * events. Visibility is RBAC-gated server-side, so adding yourself
 * doesn't grant new access — it just routes future updates to you.
 */
import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Tooltip, message } from 'antd'
import { EyeOutlined, EyeInvisibleOutlined } from '@ant-design/icons'

import { addWatcher, listWatchers, removeWatcher } from '@/api/tickets'
import { useSessionStore } from '@/stores/sessionStore'

interface WatchButtonProps {
  ticketId: string
  /** Show "Watching · 4" instead of just the icon. Defaults to true. */
  showCount?: boolean
}

export function WatchButton({ ticketId, showCount = true }: WatchButtonProps) {
  const user = useSessionStore((s) => s.user)
  const queryClient = useQueryClient()
  const [msg, holder] = message.useMessage()

  const watchers = useQuery({
    queryKey: ['watchers', ticketId],
    queryFn: () => listWatchers(ticketId),
    staleTime: 10_000,
  })

  const isWatching = useMemo(() => {
    if (!user?.id) return false
    return (watchers.data?.items ?? []).some((w) => w.user_id === user.id)
  }, [watchers.data, user?.id])

  const subscribe = useMutation({
    mutationFn: () => addWatcher(ticketId),
    onSuccess: async () => {
      msg.success('Subscribed — you will get notifications for this ticket.')
      await queryClient.invalidateQueries({ queryKey: ['watchers', ticketId] })
    },
    onError: (err) => msg.error(err.message),
  })

  const unsubscribe = useMutation({
    mutationFn: () => removeWatcher(ticketId, user!.id),
    onSuccess: async () => {
      msg.info('Unsubscribed.')
      await queryClient.invalidateQueries({ queryKey: ['watchers', ticketId] })
    },
    onError: (err) => msg.error(err.message),
  })

  const count = watchers.data?.items.length ?? 0
  const label = isWatching
    ? (showCount ? `Watching · ${count}` : 'Watching')
    : (showCount && count > 0 ? `Watch · ${count}` : 'Watch')

  return (
    <>
      {holder}
      <Tooltip title={isWatching
        ? 'You receive notifications when this ticket changes. Click to stop.'
        : 'Get notifications when this ticket changes.'}>
        <Button
          icon={isWatching ? <EyeOutlined /> : <EyeInvisibleOutlined />}
          loading={subscribe.isPending || unsubscribe.isPending || watchers.isLoading}
          onClick={() => (isWatching ? unsubscribe.mutate() : subscribe.mutate())}
          type={isWatching ? 'primary' : 'default'}
        >
          {label}
        </Button>
      </Tooltip>
    </>
  )
}
