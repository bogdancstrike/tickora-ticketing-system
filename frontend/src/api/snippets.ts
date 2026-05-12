import { apiClient } from './client'

export interface SnippetAudience {
  kind: 'sector' | 'role' | 'beneficiary_type'
  value: string
}

export interface Snippet {
  id: string
  title: string
  body: string
  created_by_user_id: string
  audiences: SnippetAudience[]
  created_at: string | null
  updated_at: string | null
}

export const listSnippets = async (): Promise<{ items: Snippet[] }> => {
  const { data } = await apiClient.get('/api/snippets')
  return data
}

export const getSnippet = async (id: string): Promise<Snippet> => {
  const { data } = await apiClient.get(`/api/snippets/${id}`)
  return data
}

export const createSnippet = async (payload: {
  title: string
  body: string
  audiences: SnippetAudience[]
}): Promise<Snippet> => {
  const { data } = await apiClient.post('/api/snippets', payload)
  return data
}

export const updateSnippet = async (
  id: string,
  payload: { title?: string; body?: string; audiences?: SnippetAudience[] },
): Promise<Snippet> => {
  const { data } = await apiClient.patch(`/api/snippets/${id}`, payload)
  return data
}

export const deleteSnippet = async (id: string): Promise<void> => {
  await apiClient.delete(`/api/snippets/${id}`)
}
