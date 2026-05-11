import { apiClient } from './client'
import type { AuditEventDto, DashboardBreakdown } from './tickets'

export const ADMIN_ROLES = [
  'tickora_admin',
  'tickora_auditor',
  'tickora_distributor',
  'tickora_avizator',
  'tickora_internal_user',
  'tickora_external_user',
  'tickora_service_account',
] as const

export type AdminRole = typeof ADMIN_ROLES[number]
export type MembershipRole = 'member' | 'chief'

export interface AdminSector {
  id: string
  code: string
  name: string
  description?: string | null
  is_active: boolean
  membership_count?: number
  created_at?: string | null
  updated_at?: string | null
}

export interface AdminMembership {
  id: string
  user_id: string
  username?: string | null
  email?: string | null
  sector_id: string
  sector_code: string
  sector_name: string
  role: MembershipRole
  is_active: boolean
  created_at?: string | null
}

export interface AdminUser {
  id: string
  keycloak_subject: string
  username?: string | null
  email?: string | null
  first_name?: string | null
  last_name?: string | null
  user_type: string
  is_active: boolean
  roles: AdminRole[]
  memberships: AdminMembership[]
}

export interface AdminMetadataKey {
  key: string
  label: string
  value_type: 'string' | 'enum'
  options: string[]
  description?: string | null
  is_active: boolean
}

export interface AdminTicketMetadata {
  id: string
  ticket_id: string
  ticket_code?: string | null
  ticket_title?: string | null
  key: string
  value: string
  label?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface AdminOverview {
  generated_at: string
  kpis: Record<string, number | null>
  by_status: DashboardBreakdown[]
  by_priority: DashboardBreakdown[]
  by_sector: Array<{ sector_code: string; count: number }>
  global_dashboard: {
    by_category: DashboardBreakdown[]
    top_backlog_sectors: Array<{ sector_code: string; sector_name: string; count: number }>
  }
  queues: Record<string, number>
  system: Record<string, number>
  recent_audit: AuditEventDto[]
}

export interface AdminTreeNode {
  key: string
  title: string
  children?: AdminTreeNode[]
}

export const getAdminOverview = async (): Promise<AdminOverview> => {
  const { data } = await apiClient.get('/api/admin/overview')
  return data
}

export const listAdminUsers = async (
  params: string | { search?: string; limit?: number; offset?: number } = {},
): Promise<{ items: AdminUser[]; total?: number }> => {
  const query = typeof params === 'string'
    ? { search: params || undefined, limit: 200 }
    : { ...params, limit: params.limit || 200 }
  const { data } = await apiClient.get('/api/admin/users', { params: query })
  return data
}

export const updateAdminUser = async (
  userId: string,
  payload: Partial<Pick<AdminUser, 'is_active' | 'roles' | 'user_type' | 'first_name' | 'last_name' | 'email' | 'username'>>,
): Promise<AdminUser> => {
  const { data } = await apiClient.patch(`/api/admin/users/${userId}`, payload)
  return data
}

export const listAdminSectors = async (): Promise<{ items: AdminSector[] }> => {
  const { data } = await apiClient.get('/api/admin/sectors')
  return data
}

export const createAdminSector = async (payload: Partial<AdminSector>): Promise<AdminSector> => {
  const { data } = await apiClient.post('/api/admin/sectors', payload)
  return data
}

export const updateAdminSector = async (sectorId: string, payload: Partial<AdminSector>): Promise<AdminSector> => {
  const { data } = await apiClient.patch(`/api/admin/sectors/${sectorId}`, payload)
  return data
}

export const listAdminMemberships = async (sectorCode?: string): Promise<{ items: AdminMembership[] }> => {
  const { data } = await apiClient.get('/api/admin/memberships', { params: { sector_code: sectorCode || undefined } })
  return data
}

export const grantMembership = async (payload: {
  user_id: string
  sector_code: string
  role: MembershipRole
}): Promise<AdminMembership> => {
  const { data } = await apiClient.post('/api/admin/memberships', payload)
  return data
}

export const revokeMembership = async (membershipId: string): Promise<void> => {
  await apiClient.delete(`/api/admin/memberships/${membershipId}`)
}

export const getGroupHierarchy = async (): Promise<AdminTreeNode> => {
  const { data } = await apiClient.get('/api/admin/group-hierarchy')
  return data
}

export const listAdminMetadataKeys = async (): Promise<{ items: AdminMetadataKey[] }> => {
  const { data } = await apiClient.get('/api/admin/metadata-keys')
  return data
}

export const upsertAdminMetadataKey = async (payload: AdminMetadataKey): Promise<AdminMetadataKey> => {
  const { data } = await apiClient.post('/api/admin/metadata-keys', payload)
  return data
}

export const listAdminTicketMetadatas = async (params: {
  search?: string
  ticket_code?: string
  key?: string
  limit?: number
  offset?: number
} = {}): Promise<{ items: AdminTicketMetadata[]; total: number }> => {
  const { data } = await apiClient.get('/api/admin/ticket-metadatas', {
    params: { ...params, limit: params.limit || 200 },
  })
  return data
}

export const upsertAdminTicketMetadata = async (
  payload: Partial<AdminTicketMetadata> & { ticket_id?: string; ticket_code?: string; key?: string; value?: string },
): Promise<AdminTicketMetadata> => {
  const { data } = await apiClient.post('/api/admin/ticket-metadatas', payload)
  return data
}

export const deleteAdminTicketMetadata = async (metadataId: string): Promise<void> => {
  await apiClient.delete(`/api/admin/ticket-metadatas/${metadataId}`)
}

export interface SystemSetting {
  key: string
  value: any
  description?: string | null
  updated_at?: string | null
}

export const listSystemSettings = async (): Promise<{ items: SystemSetting[] }> => {
  const { data } = await apiClient.get('/api/admin/system-settings')
  return data
}

export const upsertSystemSetting = async (payload: Partial<SystemSetting> & { key: string; value: any }): Promise<SystemSetting> => {
  const { data } = await apiClient.post('/api/admin/system-settings', payload)
  return data
}

export interface AdminWidgetDefinition {
  type: string
  display_name: string
  description?: string | null
  is_active: boolean
  icon?: string | null
  required_roles?: string[] | null
  created_at?: string | null
  updated_at?: string | null
}

export const listAdminWidgets = async (): Promise<{ items: AdminWidgetDefinition[] }> => {
  const { data } = await apiClient.get('/api/admin/widget-definitions')
  return data
}

export const upsertAdminWidget = async (payload: Partial<AdminWidgetDefinition> & { type: string }): Promise<AdminWidgetDefinition> => {
  const { data } = await apiClient.post('/api/admin/widget-definitions/upsert', payload)
  return data
}

// ── Background tasks (lifecycle rows from src.tasking) ──────────────────────

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface AdminTask {
  id: string
  task_name: string
  topic: string | null
  status: TaskStatus
  payload: Record<string, unknown> | null
  correlation_id: string | null
  attempts: number
  last_error: string | null
  created_at: string | null
  started_at: string | null
  completed_at: string | null
  last_heartbeat_at: string | null
}

export const listAdminTasks = async (params: {
  status?: TaskStatus
  task_name?: string
  limit?: number
} = {}): Promise<{ items: AdminTask[] }> => {
  const { data } = await apiClient.get('/api/tasks', { params })
  return data
}

export const getAdminTask = async (taskId: string): Promise<AdminTask> => {
  const { data } = await apiClient.get(`/api/tasks/${taskId}`)
  return data
}

export const syncAdminWidgets = async (): Promise<void> => {
  await apiClient.post('/api/admin/widget-definitions/sync')
}

// ── Taxonomy (categories / subcategories / dynamic fields) ──────────────────

export interface AdminSubcategoryField {
  id?: string
  subcategory_id?: string
  key: string
  label: string
  value_type: string
  options?: string[] | null
  is_required: boolean
  display_order?: number
  description?: string | null
}

export interface AdminSubcategory {
  id?: string
  category_id?: string
  code: string
  name: string
  description?: string | null
  display_order?: number
  is_active: boolean
  fields: AdminSubcategoryField[]
}

export interface AdminCategory {
  id?: string
  code: string
  name: string
  description?: string | null
  is_active: boolean
  subcategories: AdminSubcategory[]
}

export const listAdminCategories = async (): Promise<{ items: AdminCategory[] }> => {
  const { data } = await apiClient.get('/api/admin/categories')
  return data
}

export const upsertAdminCategory = async (payload: Partial<AdminCategory>): Promise<AdminCategory> => {
  const { data } = await apiClient.post('/api/admin/categories', payload)
  return data
}

export const deleteAdminCategory = async (categoryId: string): Promise<void> => {
  await apiClient.delete(`/api/admin/categories/${categoryId}`)
}

export const upsertAdminSubcategory = async (payload: Partial<AdminSubcategory>): Promise<AdminSubcategory> => {
  const { data } = await apiClient.post('/api/admin/subcategories', payload)
  return data
}

export const deleteAdminSubcategory = async (subcategoryId: string): Promise<void> => {
  await apiClient.delete(`/api/admin/subcategories/${subcategoryId}`)
}

export const upsertAdminSubcategoryField = async (payload: Partial<AdminSubcategoryField>): Promise<AdminSubcategoryField> => {
  const { data } = await apiClient.post('/api/admin/subcategory-fields', payload)
  return data
}

export const deleteAdminSubcategoryField = async (fieldId: string): Promise<void> => {
  await apiClient.delete(`/api/admin/subcategory-fields/${fieldId}`)
}
