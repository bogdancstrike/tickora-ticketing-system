import { apiClient } from './client'

export type EndorsementStatus = 'pending' | 'approved' | 'rejected'

export interface EndorsementDto {
  id: string
  ticket_id: string
  requested_by_user_id: string
  assigned_to_user_id: string | null
  status: EndorsementStatus
  request_reason: string | null
  decided_by_user_id: string | null
  decision_reason: string | null
  decided_at: string | null
  created_at: string | null
  updated_at: string | null
  // Inbox-only (joined ticket fields):
  ticket_code?: string
  ticket_title?: string | null
  ticket_status?: string
  ticket_priority?: string
}

export const listEndorsementsForTicket = async (ticketId: string): Promise<{ items: EndorsementDto[] }> => {
  const { data } = await apiClient.get(`/api/tickets/${ticketId}/endorsements`)
  return data
}

export const requestEndorsement = async (
  ticketId: string,
  payload: { reason?: string; assigned_to_user_id?: string | null },
): Promise<EndorsementDto> => {
  const { data } = await apiClient.post(`/api/tickets/${ticketId}/endorsements`, payload)
  return data
}

export const decideEndorsement = async (
  endorsementId: string,
  payload: { decision: 'approved' | 'rejected'; reason?: string },
): Promise<EndorsementDto> => {
  const path = payload.decision === 'approved' ? 'approve' : 'reject'
  const { data } = await apiClient.post(`/api/endorsements/${endorsementId}/${path}`, { reason: payload.reason })
  return data
}

export const claimEndorsement = async (
  endorsementId: string,
): Promise<EndorsementDto> => {
  const { data } = await apiClient.post(`/api/endorsements/${endorsementId}/claim`)
  return data
}

export const listEndorsementInbox = async (params: {
  status?: EndorsementStatus
  limit?: number
} = {}): Promise<{ items: EndorsementDto[] }> => {
  const { data } = await apiClient.get('/api/endorsements', { params })
  return data
}
