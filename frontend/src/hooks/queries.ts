import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, request } from '@/lib/api'
import { ME_KEY } from '@/lib/queryClient'
import type {
  AdminUser,
  AuditEntry,
  CreatedInvite,
  Doctor,
  DoctorInput,
  DocumentInfo,
  Invite,
  Lab,
  LabInput,
  MedicalRecord,
  PrivacyInfo,
  RecordFilters,
  RecordInput,
  RecordPage,
  RecordType,
  StorageUse,
  SystemInfo,
  TagCount,
  YearCount,
  TimelineItem,
  User,
} from '@/lib/types'

export const PAGE_SIZE = 20

export const EMPTY_FILTERS: RecordFilters = { q: '', types: [], tags: [], dateFrom: '', dateTo: '', year: '', sort: 'newest' }

export function filtersToParams(filters: RecordFilters): URLSearchParams {
  const params = new URLSearchParams()
  if (filters.q.trim()) params.set('q', filters.q.trim())
  filters.types.forEach((type) => params.append('record_type', type))
  filters.tags.forEach((tag) => params.append('tag', tag))
  // A year narrows the date range; when both are set, the stricter bound wins.
  const yearFrom = filters.year ? `${filters.year}-01-01` : ''
  const yearTo = filters.year ? `${filters.year}-12-31` : ''
  const dateFrom = [filters.dateFrom, yearFrom].filter(Boolean).sort().pop()
  const dateTo = [filters.dateTo, yearTo].filter(Boolean).sort().shift()
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  if (filters.sort === 'oldest') params.set('sort', 'oldest')
  return params
}

// ------------------------------------------------------------------ session

export function useMe() {
  return useQuery({
    queryKey: ME_KEY,
    queryFn: async (): Promise<User | null> => {
      try {
        return await request<User>('/api/auth/me')
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null
        throw error
      }
    },
    staleTime: 5 * 60_000,
    retry: false,
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => request<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }),
    onSuccess: () => {
      queryClient.clear()
      queryClient.setQueryData(ME_KEY, null)
    },
  })
}

/** Ends every session of this account, on every device, including this one. */
export function useLogoutAll() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => request<{ ok: boolean }>('/api/auth/logout-all', { method: 'POST' }),
    onSuccess: () => {
      queryClient.clear()
      queryClient.setQueryData(ME_KEY, null)
    },
  })
}

// ------------------------------------------------------------------ privacy and the account

export function usePrivacyInfo() {
  return useQuery({ queryKey: ['privacy'], queryFn: ({ signal }) => request<PrivacyInfo>('/api/auth/privacy', { signal }), staleTime: Infinity })
}

export function useGiveConsent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (version: string) => request<void>('/api/account/consent', { method: 'POST', json: { version } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ME_KEY }),
  })
}

/** Permanently deletes the signed-in account and everything in it, then the session is gone. */
export function useDeleteMyAccount() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (confirmEmail: string) => request<{ ok: boolean }>('/api/account/delete', { method: 'POST', json: { confirm_email: confirmEmail } }),
    onSuccess: () => {
      queryClient.clear()
      queryClient.setQueryData(ME_KEY, null)
    },
  })
}

export function useAdminSystem() {
  return useQuery({ queryKey: ['admin', 'system'], queryFn: ({ signal }) => request<SystemInfo>('/api/admin/system', { signal }) })
}

export function useAuditLog() {
  return useInfiniteQuery({
    queryKey: ['admin', 'audit'],
    queryFn: ({ pageParam, signal }) => {
      const params = new URLSearchParams({ limit: '50' })
      if (pageParam) params.set('before', pageParam)
      return request<AuditEntry[]>(`/api/admin/audit?${params}`, { signal })
    },
    initialPageParam: '',
    getNextPageParam: (last) => (last.length === 50 ? last[last.length - 1]!.at : undefined),
  })
}

// ------------------------------------------------------------------ invites and admin

export function useInviteCheck(token: string | undefined) {
  return useQuery({
    queryKey: ['invite-check', token],
    queryFn: ({ signal }) => request<{ valid: boolean }>(`/api/auth/invite/${encodeURIComponent(token ?? '')}`, { signal }),
    enabled: Boolean(token),
    retry: false,
  })
}

const ADMIN_INVITES_KEY = ['admin', 'invites']
const ADMIN_USERS_KEY = ['admin', 'users']

export function useAdminInvites() {
  return useQuery({ queryKey: ADMIN_INVITES_KEY, queryFn: ({ signal }) => request<Invite[]>('/api/admin/invites', { signal }) })
}

export function useAdminUsers() {
  return useQuery({ queryKey: ADMIN_USERS_KEY, queryFn: ({ signal }) => request<AdminUser[]>('/api/admin/users', { signal }) })
}

export function useCreateInvite() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (email: string) => request<CreatedInvite>('/api/admin/invites', { method: 'POST', json: { email } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin'] }),
  })
}

export function useRevokeInvite() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => request<Invite>(`/api/admin/invites/${id}/revoke`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin'] }),
  })
}

export function useSetUserDisabled() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, disabled }: { id: string; disabled: boolean }) =>
      request<void>(`/api/admin/users/${id}/${disabled ? 'disable' : 'enable'}`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin'] }),
  })
}

export function useSetQuota() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, quotaMb }: { id: string; quotaMb: number | null }) =>
      request<void>(`/api/admin/users/${id}/quota`, { method: 'PUT', json: { quota_mb: quotaMb } }),
    onSuccess: () => Promise.all([queryClient.invalidateQueries({ queryKey: ['admin'] }), queryClient.invalidateQueries({ queryKey: ['storage'] })]),
  })
}

export function useDeleteUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, confirmEmail }: { id: string; confirmEmail: string }) =>
      request<void>(`/api/admin/users/${id}/delete`, { method: 'POST', json: { confirm_email: confirmEmail } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin'] }),
  })
}

// ------------------------------------------------------------------ records

export function useRecordList(filters: RecordFilters) {
  return useInfiniteQuery({
    queryKey: ['records', 'list', filters],
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) => {
      const params = filtersToParams(filters)
      params.set('limit', String(PAGE_SIZE))
      params.set('offset', String(pageParam))
      const path = filters.q.trim() ? '/api/search' : '/api/records'
      return request<RecordPage>(`${path}?${params}`, { signal })
    },
    getNextPageParam: (last) => (last.offset + last.items.length < last.total ? last.offset + last.limit : undefined),
  })
}

export function useRecentRecords(limit = 8) {
  return useQuery({
    queryKey: ['records', 'recent', limit],
    queryFn: ({ signal }) => request<RecordPage>(`/api/records?limit=${limit}`, { signal }),
  })
}

export function useRecord(id: string | undefined) {
  return useQuery({
    queryKey: ['record', id],
    queryFn: ({ signal }) => request<MedicalRecord>(`/api/records/${id}`, { signal }),
    enabled: Boolean(id),
  })
}

export function useInvalidateRecordData() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all(
      [['records'], ['record'], ['timeline'], ['tags'], ['years'], ['doctors'], ['labs'], ['storage']].map((queryKey) =>
        queryClient.invalidateQueries({ queryKey }),
      ),
    )
}

export function useCreateRecord() {
  const invalidate = useInvalidateRecordData()
  return useMutation({
    mutationFn: (input: RecordInput) => request<MedicalRecord>('/api/records', { method: 'POST', json: input }),
    onSuccess: invalidate,
  })
}

export function useUpdateRecord(id: string) {
  const invalidate = useInvalidateRecordData()
  return useMutation({
    mutationFn: (input: RecordInput) => request<MedicalRecord>(`/api/records/${id}`, { method: 'PUT', json: input }),
    onSuccess: invalidate,
  })
}

export function useDeleteRecord() {
  const queryClient = useQueryClient()
  const invalidate = useInvalidateRecordData()
  return useMutation({
    mutationFn: (id: string) => request<void>(`/api/records/${id}`, { method: 'DELETE' }),
    onSuccess: (_data, id) => {
      // Drop the deleted record first so the open detail page does not refetch it and flash a 404.
      queryClient.removeQueries({ queryKey: ['record', id] })
      return invalidate()
    },
  })
}

// ------------------------------------------------------------------ documents

export function uploadDocument(recordId: string, file: File): Promise<DocumentInfo[]> {
  const form = new FormData()
  form.append('files', file, file.name)
  return request<DocumentInfo[]>(`/api/records/${recordId}/documents`, { method: 'POST', form })
}

export function useUploadDocuments(recordId: string) {
  const invalidate = useInvalidateRecordData()
  return useMutation({
    mutationFn: async (files: File[]) => {
      const failures: string[] = []
      for (const file of files) {
        try {
          await uploadDocument(recordId, file)
        } catch (error) {
          failures.push(`${file.name}: ${error instanceof Error ? error.message : 'could not upload'}`)
        }
      }
      if (failures.length) throw new Error(failures.join('\n'))
    },
    onSettled: invalidate,
  })
}

export function useDeleteDocument() {
  const invalidate = useInvalidateRecordData()
  return useMutation({
    mutationFn: (id: string) => request<void>(`/api/documents/${id}`, { method: 'DELETE' }),
    onSuccess: invalidate,
  })
}

export function useDocument(id: string | undefined) {
  return useQuery({
    queryKey: ['document', id],
    queryFn: ({ signal }) => request<DocumentInfo>(`/api/documents/${id}`, { signal }),
    enabled: Boolean(id),
  })
}

// ------------------------------------------------------------------ directories, tags, timeline

export function useDoctors() {
  return useQuery({ queryKey: ['doctors'], queryFn: ({ signal }) => request<Doctor[]>('/api/doctors', { signal }) })
}

export function useLabs() {
  return useQuery({ queryKey: ['labs'], queryFn: ({ signal }) => request<Lab[]>('/api/labs', { signal }) })
}

export function useSaveDoctor() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, input }: { id?: string; input: DoctorInput }) =>
      id
        ? request<Doctor>(`/api/doctors/${id}`, { method: 'PUT', json: input })
        : request<Doctor>('/api/doctors', { method: 'POST', json: input }),
    onSuccess: () => Promise.all([queryClient.invalidateQueries({ queryKey: ['doctors'] }), queryClient.invalidateQueries({ queryKey: ['record'] })]),
  })
}

export function useDeleteDoctor() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => request<void>(`/api/doctors/${id}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['doctors'] }),
  })
}

export function useSaveLab() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, input }: { id?: string; input: LabInput }) =>
      id
        ? request<Lab>(`/api/labs/${id}`, { method: 'PUT', json: input })
        : request<Lab>('/api/labs', { method: 'POST', json: input }),
    onSuccess: () => Promise.all([queryClient.invalidateQueries({ queryKey: ['labs'] }), queryClient.invalidateQueries({ queryKey: ['record'] })]),
  })
}

export function useDeleteLab() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => request<void>(`/api/labs/${id}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['labs'] }),
  })
}

export function useTags() {
  return useQuery({ queryKey: ['tags'], queryFn: ({ signal }) => request<TagCount[]>('/api/tags', { signal }) })
}

export function useYears() {
  return useQuery({ queryKey: ['years'], queryFn: ({ signal }) => request<YearCount[]>('/api/years', { signal }) })
}

export function useTimeline(types: RecordType[]) {
  return useQuery({
    queryKey: ['timeline', types],
    queryFn: ({ signal }) => {
      const params = new URLSearchParams()
      types.forEach((type) => params.append('record_type', type))
      return request<TimelineItem[]>(`/api/timeline?${params}`, { signal })
    },
  })
}

export function useStorageUse() {
  return useQuery({ queryKey: ['storage'], queryFn: ({ signal }) => request<StorageUse>('/api/storage', { signal }) })
}

export interface AppConfig {
  max_upload_mb: number
  allowed_extensions: string[]
}

export function useAppConfig() {
  return useQuery({
    queryKey: ['config'],
    queryFn: ({ signal }) => request<AppConfig>('/api/config', { signal }),
    staleTime: Infinity,
  })
}
