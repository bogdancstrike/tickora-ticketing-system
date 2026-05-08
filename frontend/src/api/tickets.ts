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
  suggested_sector_code?: string
  category?: string
  type?: string
  priority: TicketDto['priority']
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
  entity_type?: string
  entity_id?: string
  ticket_id?: string
  correlation_id?: string
  limit?: number
}): Promise<{ items: AuditEventDto[] }> => {
  const { data } = await apiClient.get('/api/audit', { params })
  return data
}
