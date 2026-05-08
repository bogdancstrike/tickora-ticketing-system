import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'

dayjs.extend(relativeTime)

export function fmtDateTime(value?: string | null): string {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-'
}

export function fmtDate(value?: string | null): string {
  return value ? dayjs(value).format('YYYY-MM-DD') : '-'
}

export function fmtRelative(value?: string | null): string {
  return value ? dayjs(value).fromNow() : '-'
}

export function fmtBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}
