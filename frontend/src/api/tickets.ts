import { apiClient } from './client'

export interface SectorMembershipDto {
  sector_code: string
  role: 'member' | 'chief'
}

export interface MeDto {
  user_id: string
  keycloak_subject: string
  username?: string
  email?: string
  first_name?: string
  last_name?: string
  roles: string[]
  sectors: SectorMembershipDto[]
}

export interface TicketDto {
  id: string
  ticket_code: string
  status: string
  priority: 'low' | 'medium' | 'high' | 'critical'
  category?: string | null
  type?: string | null
  beneficiary_type: 'internal' | 'external'
  title?: string | null
  txt?: string
  resolution?: string | null
  current_sector_code?: string | null
  created_at?: string | null
  updated_at?: string | null
  done_at?: string | null
  closed_at?: string | null
  reopened_at?: string | null
  reopened_count: number
  sla_due_at?: string | null
  sla_status?: string | null
  assignee_user_id?: string | null
  requester_first_name?: string | null
  requester_last_name?: string | null
  requester_email?: string | null
  created_by_user_id?: string | null
  last_active_assignee_user_id?: string | null
  assigned_at?: string | null
  sector_assigned_at?: string | null
  first_response_at?: string | null
}

export interface TicketListResponse {
  items: TicketDto[]
  next_cursor?: string | null
}

export interface CommentDto {
  id: string
  ticket_id: string
  author_user_id?: string | null
  visibility: 'public' | 'private'
  comment_type: string
  body: string
  created_at?: string | null
  updated_at?: string | null
}

export interface AttachmentDto {
  id: string
  ticket_id: string
  comment_id?: string | null
  uploaded_by_user_id?: string | null
  file_name: string
  content_type?: string | null
  size_bytes: number
  visibility: 'public' | 'private'
  checksum_sha256?: string | null
  is_scanned: boolean
  scan_result?: string | null
  created_at?: string | null
}

export interface AuditEventDto {
  id: string
  actor_user_id?: string | null
  actor_username?: string | null
  action: string
  entity_type: string
  entity_id?: string | null
  ticket_id?: string | null
  old_value?: Record<string, unknown> | null
  new_value?: Record<string, unknown> | null
  metadata?: Record<string, unknown> | null
  correlation_id?: string | null
  created_at?: string | null
}

export interface ListTicketParams {
  status?: string
  priority?: string
  current_sector_code?: string
  cursor?: string
  limit?: number
}

export interface CreateTicketPayload {
  beneficiary_type: 'internal' | 'external'
  requester_first_name?: string
  requester_last_name?: string
  requester_email?: string
  requester_phone?: string
  organization_name?: string
  external_identifier?: string
  requester_ip?: string
  title?: string
  txt: string
}

export interface TicketOptionsDto {
  sectors: Array<{ id: string; code: string; name: string }>
  priorities: Array<TicketDto['priority']>
  categories: string[]
  types: string[]
  metadata_keys: Array<{ key: string; label: string }>
}

export interface TicketMetadataDto {
  key: string
  value: string
  label?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface AssignableUserDto {
  id: string
  username?: string | null
  email?: string | null
  first_name?: string | null
  last_name?: string | null
  sector_code: string
  membership_role: 'member' | 'chief'
}

export interface ReviewTicketPayload {
  sector_code?: string
  assignee_user_id?: string
  priority?: TicketDto['priority']
  category?: string
  type?: string
  private_comment?: string
  reason?: string
  close?: boolean
}

export interface DashboardBreakdown {
  key: string
  count: number
}

export interface DashboardOldTicket {
  id: string
  ticket_code: string
  title?: string | null
  status: string
  priority: TicketDto['priority']
  created_at?: string | null
}

export interface DashboardTimeseriesPoint {
  date: string
  created: number
  closed: number
}

export interface DashboardSector {
  sector_code: string
  sector_name: string
  kpis: Record<string, number | null>
  by_status: DashboardBreakdown[]
  by_priority: DashboardBreakdown[]
  by_category: DashboardBreakdown[]
  workload: Array<{ assignee_user_id: string; active: number; done: number }>
  oldest: DashboardOldTicket[]
}

export interface DashboardOverview {
  generated_at: string
  global?: {
    kpis: Record<string, number | null>
    by_status: DashboardBreakdown[]
    by_priority: DashboardBreakdown[]
    by_beneficiary_type: DashboardBreakdown[]
    by_category: DashboardBreakdown[]
    by_sector: Array<{ sector_code: string; sector_name: string; count: number }>
    top_backlog_sectors: Array<{ sector_code: string; sector_name: string; count: number }>
  } | null
  distributor?: {
    kpis: Record<string, number | null>
    by_priority: DashboardBreakdown[]
    by_category: DashboardBreakdown[]
    oldest: DashboardOldTicket[]
  } | null
  sectors: DashboardSector[]
  personal: {
    user_id: string
    username?: string | null
    email?: string | null
    kpis: Record<string, number | null>
    by_status: DashboardBreakdown[]
    oldest: DashboardOldTicket[]
  }
  beneficiary: {
    kpis: Record<string, number | null>
    by_status: DashboardBreakdown[]
  }
  timeseries: DashboardTimeseriesPoint[]
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

export const getDashboardOverview = async (): Promise<DashboardOverview> => {
  const { data } = await apiClient.get('/api/dashboard/overview')
  return data
}

export const getSectorDashboard = async (sectorCode: string): Promise<DashboardSector> => {
  const { data } = await apiClient.get(`/api/dashboard/sectors/${sectorCode}`)
  return data
}

export const getUserDashboard = async (userId: string): Promise<DashboardOverview['personal']> => {
  const { data } = await apiClient.get(`/api/dashboard/users/${userId}`)
  return data
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

export const markDone = async (ticketId: string, resolution: string): Promise<TicketDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/mark-done`, { resolution })
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

export const changePriority = async (ticketId: string, priority: TicketDto['priority'], reason?: string): Promise<TicketDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/change-priority`, {
    priority,
    reason: reason || undefined,
  })
  return data
}

export const listComments = async (ticketId: string): Promise<{ items: CommentDto[] }> => {
  const { data } = await apiClient.get(`/api/tickets/${ticketId}/comments`)
  return data
}

export const createComment = async (
  ticketId: string,
  body: string,
  visibility: CommentDto['visibility'],
): Promise<CommentDto> => {
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

export const listAttachments = async (ticketId: string): Promise<{ items: AttachmentDto[] }> => {
  const { data } = await apiClient.get(`/api/tickets/${ticketId}/attachments`)
  return data
}

export const requestAttachmentUpload = async (
  ticketId: string,
  file: File,
  visibility: AttachmentDto['visibility'],
): Promise<{ upload_url: string; storage_key: string; storage_bucket: string; expires_in: number }> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/attachments/upload-url`, {
    file_name: file.name,
    content_type: file.type || 'application/octet-stream',
    size_bytes: file.size,
    visibility,
  })
  return data
}

export const registerAttachment = async (
  ticketId: string,
  file: File,
  storageKey: string,
  visibility: AttachmentDto['visibility'],
): Promise<AttachmentDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/attachments`, {
    storage_key: storageKey,
    file_name: file.name,
    content_type: file.type || 'application/octet-stream',
    size_bytes: file.size,
    visibility,
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
  await apiClient.delete(`/api/tickets/${ticketId}/metadata`, { params: { key } })
}

export const updateTicket = async (ticketId: string, payload: { title?: string; txt?: string }): Promise<TicketDto> => {
  const { data } = await apiClient.patch(`/api/tickets/${ticketId}`, payload)
  return data
}

export const deleteTicket = async (ticketId: string): Promise<void> => {
  await apiClient.delete(`/api/tickets/${ticketId}`)
}
