import { apiClient } from './client'

export interface SectorMembershipDto {
  sector_code: string
  sector_name: string
  role: 'member' | 'chief'
}

export interface MeDto {
  user_id: string
  username: string
  email: string
  first_name?: string | null
  last_name?: string | null
  roles: string[]
  sectors: SectorMembershipDto[]
  has_root_group: boolean
  created_at: string
}

export interface TicketDto {
  id: string
  ticket_code: string
  status: string
  priority: string
  category?: string | null
  type?: string | null
  beneficiary_type: 'internal' | 'external'
  title?: string | null
  txt?: string
  resolution?: string | null
  current_sector_code?: string | null
  beneficiary_user_id?: string | null
  /** All sectors this ticket is routed to (primary first). */
  sector_codes?: string[]
  /** All users assigned to this ticket (primary first). */
  assignee_user_ids?: string[]
  /** All usernames of users assigned to this ticket. */
  assignee_usernames?: string[]
  created_at?: string | null
  updated_at?: string | null
  done_at?: string | null
  closed_at?: string | null
  reopened_at?: string | null
  assigned_at?: string | null
  first_response_at?: string | null
  sla_status?: string | null
  sla_due_at?: string | null
  assignee_user_id?: string | null
  created_by_user_id?: string | null
  requester_first_name?: string | null
  requester_last_name?: string | null
  requester_email?: string | null
  requester_phone?: string | null
  requester_organization?: string | null
  metadata?: Record<string, { value: string; label: string }> | null
  request_ip?: string | null
  user_agent?: string | null
  correlation_id?: string | null
}

export interface ListTicketParams {
  status?: string
  priority?: string
  current_sector_code?: string
  assignee_user_id?: string
  search?: string
  sort_by?: string
  sort_dir?: 'asc' | 'desc'
  limit?: number
  cursor?: string
}

export interface TicketListResponse {
  items: TicketDto[]
  next_cursor?: string | null
}

export interface CreateTicketPayload {
  title: string
  txt: string
  priority?: string
  category?: string
  type?: string
  requester_first_name?: string
  requester_last_name?: string
  requester_email?: string
  requester_phone?: string
  requester_organization?: string
}

export interface ReviewTicketPayload {
  sector_code: string
  priority: string
  category?: string
  type?: string
  assignee_user_id?: string
  private_comment?: string
  reason?: string
  close?: boolean
}

export interface TicketOptionsDto {
  sectors: Array<{ code: string; name: string }>
  priorities: string[]
  categories: string[]
  types: string[]
  metadata_keys: Array<{
    key: string
    label: string
    value_type?: 'string' | 'enum'
    options?: string[] | null
    description?: string | null
  }>
}

export interface TicketMetadataDto {
  key: string
  value: string
  label?: string | null
  created_at: string
  updated_at: string
}

export interface AuditEventDto {
  id: string
  action: string
  entity_type: string
  entity_id: string
  ticket_id?: string | null
  actor_user_id: string
  actor_username: string
  created_at: string
  old_value?: any
  new_value?: any
  metadata?: any
}

export interface AssignableUserDto {
  id: string
  username: string
  email: string
  sector_code: string
  membership_role: string
}

export interface MonitorBreakdown {
  key: string
  count: number
}

export interface MonitorOldTicket {
  id: string
  ticket_code: string
  title: string | null
  status: string
  priority: string
  created_at: string | null
}

export interface MonitorBottleneck {
  status: string
  avg_minutes: number
  count: number
}

export interface MonitorSector {
  sector_code: string
  sector_name: string
  kpis: Record<string, number | null>
  by_status: MonitorBreakdown[]
  by_priority: MonitorBreakdown[]
  by_category: MonitorBreakdown[]
  workload: Array<{ assignee_user_id: string; username: string; active: number; done: number }>
  oldest: MonitorOldTicket[]
  stale_tickets?: MonitorOldTicket[]
  bottleneck_analysis?: MonitorBottleneck[]
}

export interface MonitorTimeseriesPoint {
  date: string
  created: number
  closed: number
}

export interface MonitorOverview {
  generated_at: string
  global?: {
    kpis: Record<string, number | null>
    by_status: MonitorBreakdown[]
    by_priority: MonitorBreakdown[]
    by_beneficiary_type: MonitorBreakdown[]
    by_category: MonitorBreakdown[]
    by_sector: Array<{ sector_code: string; sector_name: string; count: number }>
    top_backlog_sectors: Array<{ sector_code: string; sector_name: string; count: number }>
    stale_tickets?: MonitorOldTicket[]
    bottleneck_analysis?: MonitorBottleneck[]
  } | null
  distributor?: {
    kpis: Record<string, number | null>
    by_priority: MonitorBreakdown[]
    by_category: MonitorBreakdown[]
    oldest: MonitorOldTicket[]
  } | null
  sectors: MonitorSector[]
  personal: {
    user_id: string
    username?: string | null
    email?: string | null
    kpis: Record<string, number | null>
    beneficiary_kpis: Record<string, number | null>
    by_status: MonitorBreakdown[]
    beneficiary_by_status: MonitorBreakdown[]
    oldest: MonitorOldTicket[]
  }
  timeseries: MonitorTimeseriesPoint[]
  stale_tickets?: MonitorOldTicket[]
}

export interface DashboardWidgetDto {
  id: string
  type: string
  title?: string | null
  config: Record<string, any>
  x: number
  y: number
  w: number
  h: number
}

export interface CustomDashboardDto {
  id: string
  title: string
  description?: string | null
  widget_count: number
  is_default: boolean
  created_at: string
  updated_at: string
  widgets?: DashboardWidgetDto[]
}

export const getMe = async (): Promise<MeDto> => {
  const { data } = await apiClient.get('/api/me')
  return data
}

export const listTickets = async (params: ListTicketParams): Promise<TicketListResponse> => {
  const { data } = await apiClient.get('/api/tickets', { params })
  return data
}

export const getTicket = async (ticketId: string): Promise<TicketDto> => {
  const { data } = await apiClient.get(`/api/tickets/${ticketId}`)
  return data
}

export const createTicket = async (payload: CreateTicketPayload): Promise<TicketDto> => {
  const { data } = await apiClient.post('/api/tickets', payload)
  return data
}

export const getTicketOptions = async (): Promise<TicketOptionsDto> => {
  const { data } = await apiClient.get('/api/reference/ticket-options')
  return data
}

export const listAssignableUsers = async (sectorCode?: string): Promise<{ items: AssignableUserDto[] }> => {
  const { data } = await apiClient.get('/api/reference/assignable-users', {
    params: { sector_code: sectorCode || undefined },
  })
  return data
}

export const reviewTicket = async (ticketId: string, payload: ReviewTicketPayload): Promise<TicketDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/review`, payload)
  return data
}

export const changeTicketStatus = async (ticketId: string, status: string, reason?: string): Promise<TicketDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/change-status`, { status, reason })
  return data
}

export const getMonitorOverview = async (days?: number): Promise<MonitorOverview> => {
  const { data } = await apiClient.get('/api/monitor/overview', { params: { days } })
  return data
}

export const getMonitorSector = async (sectorCode: string): Promise<MonitorSector> => {
  const { data } = await apiClient.get(`/api/monitor/sectors/${sectorCode}`)
  return data
}

export const getMonitorUser = async (userId: string): Promise<MonitorOverview['personal']> => {
  const { data } = await apiClient.get(`/api/monitor/users/${userId}`)
  return data
}

export const listDashboards = async (): Promise<{ items: CustomDashboardDto[] }> => {
  const { data } = await apiClient.get('/api/dashboards')
  return data
}

export const getDashboard = async (id: string): Promise<CustomDashboardDto> => {
  const { data } = await apiClient.get(`/api/dashboards/${id}`)
  return data
}

export const createDashboard = async (payload: { title: string; description?: string; is_default?: boolean }): Promise<CustomDashboardDto> => {
  const { data } = await apiClient.post('/api/dashboards', payload)
  return data
}

export const updateDashboard = async (id: string, payload: Partial<CustomDashboardDto>): Promise<CustomDashboardDto> => {
  const { data } = await apiClient.patch(`/api/dashboards/${id}`, payload)
  return data
}

export const deleteDashboard = async (id: string): Promise<void> => {
  await apiClient.delete(`/api/dashboards/${id}`)
}

export const upsertWidget = async (dashboardId: string, payload: Partial<DashboardWidgetDto>): Promise<DashboardWidgetDto> => {
  const { data } = await apiClient.post(`/api/dashboards/${dashboardId}/widgets`, payload)
  return data
}

export const deleteWidget = async (dashboardId: string, widgetId: string): Promise<void> => {
  await apiClient.delete(`/api/dashboards/${dashboardId}/widgets/${widgetId}`)
}

export const autoConfigureDashboard = async (
  dashboardId: string,
  mode: 'append' | 'replace',
  primarySector?: string,
): Promise<void> => {
  await apiClient.post(`/api/dashboards/${dashboardId}/auto-configure`, {
    mode,
    primary_sector: primarySector || undefined,
  })
}

export const assignSector = async (ticketId: string, sectorCode: string, reason?: string): Promise<TicketDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/assign-sector`, {
    sector_code: sectorCode,
    reason: reason || undefined,
  })
  return data
}

export const assignToMe = async (ticketId: string): Promise<TicketDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/assign-to-me`)
  return data
}

export const assignToUser = async (ticketId: string, userId: string, reason?: string): Promise<TicketDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/assign-to-user`, {
    user_id: userId,
    reason: reason || undefined,
  })
  return data
}

export const addSector = async (ticketId: string, sectorCode: string): Promise<TicketDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/sectors/add`, {
    sector_code: sectorCode,
  })
  return data
}

export const removeSector = async (ticketId: string, sectorCode: string): Promise<TicketDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/sectors/remove`, {
    sector_code: sectorCode,
  })
  return data
}

export const addAssignee = async (ticketId: string, userId: string): Promise<TicketDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/assignees/add`, {
    user_id: userId,
  })
  return data
}

export const removeAssignee = async (ticketId: string, userId: string): Promise<TicketDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/assignees/remove`, {
    user_id: userId,
  })
  return data
}

export const changePriority = async (ticketId: string, priority: string, reason?: string): Promise<TicketDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/change-priority`, {
    priority,
    reason: reason || undefined,
  })
  return data
}

export const closeTicket = async (ticketId: string): Promise<TicketDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/close`)
  return data
}

export const reopenTicket = async (ticketId: string, reason: string): Promise<TicketDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/reopen`, { reason })
  return data
}

export const cancelTicket = async (ticketId: string, reason: string): Promise<TicketDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/cancel`, { reason })
  return data
}

export const markDone = async (ticketId: string, resolution?: string): Promise<TicketDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/mark-done`, {
    resolution: resolution || undefined,
  })
  return data
}

export const requestAttachmentUpload = async (
  ticketId: string,
  file: File,
): Promise<{ upload_url: string; storage_key: string; storage_bucket: string; expires_in: number }> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/attachments/upload-url`, {
    file_name: file.name,
    content_type: file.type || 'application/octet-stream',
    size_bytes: file.size,
  })
  return data
}

export const registerAttachment = async (
  ticketId: string,
  file: File,
  storageKey: string,
  commentId: string,
): Promise<AttachmentDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/attachments`, {
    storage_key: storageKey,
    file_name: file.name,
    content_type: file.type || 'application/octet-stream',
    size_bytes: file.size,
    comment_id: commentId,
  })
  return data
}

export const deleteAttachment = async (attachmentId: string): Promise<void> => {
  await apiClient.delete(`/api/attachments/${attachmentId}`)
}

export const downloadAttachmentUrl = (attachmentId: string): string =>
  `${apiClient.defaults.baseURL}/api/attachments/${attachmentId}/download`

export const listTicketAudit = async (ticketId: string): Promise<{ items: AuditEventDto[] }> => {
  const { data } = await apiClient.get(`/api/tickets/${ticketId}/audit`)
  return data
}

export const listAudit = async (params: {
  action?: string
  actor_user_id?: string
  actor_username?: string
  ticket_id?: string
  correlation_id?: string
  created_after?: string
  created_before?: string
  sort_by?: string
  sort_dir?: 'asc' | 'desc'
  limit?: number
}): Promise<{ items: AuditEventDto[] }> => {
  const { data } = await apiClient.get('/api/audit', { params })
  return data
}

export const listTicketMetadata = async (ticketId: string): Promise<{ items: TicketMetadataDto[] }> => {
  const { data } = await apiClient.get(`/api/tickets/${ticketId}/metadata`)
  return data
}

export const setTicketMetadata = async (
  ticketId: string,
  payload: { key: string; value: string; label?: string },
): Promise<TicketMetadataDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/metadata`, payload)
  return data
}

export const deleteTicketMetadata = async (ticketId: string, key: string): Promise<void> => {
  await apiClient.delete(`/api/tickets/${ticketId}/metadata/${key}`)
}

export interface AttachmentDto {
  id: string
  ticket_id: string
  comment_id: string
  uploaded_by_user_id: string | null
  file_name: string
  content_type: string | null
  size_bytes: number
  visibility: 'public' | 'private'
  checksum_sha256: string | null
  is_scanned: boolean
  scan_result: string | null
  created_at: string
}

export const listAttachments = async (ticketId: string): Promise<{ items: AttachmentDto[] }> => {
  const { data } = await apiClient.get(`/api/tickets/${ticketId}/attachments`)
  return data
}

export const listComments = async (ticketId: string): Promise<{ items: CommentDto[] }> => {
  const { data } = await apiClient.get(`/api/tickets/${ticketId}/comments`)
  return data
}

export interface CommentDto {
  id: string
  ticket_id: string
  author_user_id?: string | null
  author_display?: string | null
  author_username?: string | null
  author_email?: string | null
  visibility: 'public' | 'private'
  comment_type: string
  body: string
  created_at: string
  updated_at: string
}

export const createComment = async (ticketId: string, body: string, visibility: string): Promise<CommentDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/comments`, { body, visibility })
  return data
}

export const editComment = async (commentId: string, body: string): Promise<CommentDto> => {
  const { data } = await apiClient.patch(`/api/comments/${commentId}`, { body })
  return data
}

export const deleteComment = async (commentId: string): Promise<void> => {
  await apiClient.delete(`/api/comments/${commentId}`)
}

export const patchTicket = async (ticketId: string, payload: Partial<TicketDto>): Promise<TicketDto> => {
  const { data } = await apiClient.patch(`/api/tickets/${ticketId}`, payload)
  return data
}

export const deleteTicket = async (ticketId: string): Promise<void> => {
  await apiClient.delete(`/api/tickets/${ticketId}`)
}

export const markNotificationRead = async (notificationId: string): Promise<void> => {
  await apiClient.post(`/api/notifications/${notificationId}/mark-read`)
}

export const createStreamTicket = async (): Promise<{ ticket: string }> => {
  const { data } = await apiClient.post('/api/notifications/stream-ticket')
  return data
}
