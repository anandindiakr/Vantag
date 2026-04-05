import axios from 'axios';
import {
  useQuery,
  useMutation,
  UseQueryResult,
  UseMutationResult,
  useQueryClient,
} from '@tanstack/react-query';
import {
  Store,
  Camera,
  RiskScore,
  HeatmapData,
  Incident,
  QueueStatus,
  WatchlistEntry,
  WatchlistMatch,
} from '../store/useVantagStore';

// ─── Axios Instance ───────────────────────────────────────────────────────────

const api = axios.create({
  baseURL: '/api',
  timeout: 15_000,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const message =
      (err.response?.data as { detail?: string })?.detail ??
      err.message ??
      'Unknown API error';
    return Promise.reject(new Error(message));
  }
);

// ─── Query Keys ───────────────────────────────────────────────────────────────

export const queryKeys = {
  stores:      ['stores']                              as const,
  store:       (id: string) => ['stores', id]          as const,
  riskScore:   (id: string) => ['risk', id]            as const,
  heatmap:     (id: string, w: number) => ['heatmap', id, w] as const,
  incidents:   (id: string, p: number) => ['incidents', id, p] as const,
  allIncidents:(p: number) => ['incidents', 'all', p]  as const,
  queueStatus: ['queueStatus']                         as const,
  watchlist:   ['watchlist']                           as const,
  watchlistMatches: ['watchlistMatches']               as const,
  cameras:     ['cameras']                             as const,
  storeCamera: (storeId: string) => ['cameras', storeId] as const,
};

// ─── API Functions ────────────────────────────────────────────────────────────

const fetchStores   = () => api.get<Store[]>('/stores').then((r) => r.data);
const fetchStore    = (id: string) => api.get<Store>(`/stores/${id}`).then((r) => r.data);
const fetchRisk     = (id: string) => api.get<RiskScore>(`/stores/${id}/risk`).then((r) => r.data);
const fetchHeatmap  = (id: string, w: number) =>
  api.get<HeatmapData>(`/stores/${id}/heatmap`, { params: { window: w } }).then((r) => r.data);
const fetchIncidents = (storeId: string | null, page: number) => {
  const url = storeId ? `/stores/${storeId}/incidents` : '/incidents';
  return api.get<{ items: Incident[]; total: number; page: number; pages: number }>(url, {
    params: { page, page_size: 25 },
  }).then((r) => r.data);
};
const fetchQueueStatus = () => api.get<QueueStatus[]>('/queue-status').then((r) => r.data);
const fetchWatchlist   = () => api.get<WatchlistEntry[]>('/watchlist').then((r) => r.data);
const fetchWatchlistMatches = () =>
  api.get<WatchlistMatch[]>('/watchlist/matches').then((r) => r.data);
const fetchCameras     = (storeId?: string) =>
  api
    .get<Camera[]>('/cameras', storeId ? { params: { store_id: storeId } } : undefined)
    .then((r) => r.data);

// ─── Hooks ────────────────────────────────────────────────────────────────────

export function useStores(): UseQueryResult<Store[]> {
  return useQuery({
    queryKey: queryKeys.stores,
    queryFn:  fetchStores,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

export function useStore(id: string): UseQueryResult<Store> {
  return useQuery({
    queryKey: queryKeys.store(id),
    queryFn:  () => fetchStore(id),
    enabled:  !!id,
    staleTime: 30_000,
  });
}

export function useRiskScore(storeId: string): UseQueryResult<RiskScore> {
  return useQuery({
    queryKey: queryKeys.riskScore(storeId),
    queryFn:  () => fetchRisk(storeId),
    enabled:  !!storeId,
    staleTime: 5_000,
    refetchInterval: 10_000,
  });
}

export function useHeatmap(
  storeId: string,
  windowMinutes: number
): UseQueryResult<HeatmapData> {
  return useQuery({
    queryKey: queryKeys.heatmap(storeId, windowMinutes),
    queryFn:  () => fetchHeatmap(storeId, windowMinutes),
    enabled:  !!storeId,
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
}

export function useIncidents(
  storeId: string | null,
  page: number
): UseQueryResult<{ items: Incident[]; total: number; page: number; pages: number }> {
  return useQuery({
    queryKey: storeId
      ? queryKeys.incidents(storeId, page)
      : queryKeys.allIncidents(page),
    queryFn:  () => fetchIncidents(storeId, page),
    staleTime: 10_000,
    refetchInterval: 30_000,
  });
}

export function useQueueStatus(): UseQueryResult<QueueStatus[]> {
  return useQuery({
    queryKey: queryKeys.queueStatus,
    queryFn:  fetchQueueStatus,
    staleTime: 5_000,
    refetchInterval: 10_000,
  });
}

export function useWatchlist(): UseQueryResult<WatchlistEntry[]> {
  return useQuery({
    queryKey: queryKeys.watchlist,
    queryFn:  fetchWatchlist,
    staleTime: 15_000,
  });
}

export function useWatchlistMatches(): UseQueryResult<WatchlistMatch[]> {
  return useQuery({
    queryKey: queryKeys.watchlistMatches,
    queryFn:  fetchWatchlistMatches,
    staleTime: 5_000,
    refetchInterval: 15_000,
  });
}

export function useCameras(storeId?: string): UseQueryResult<Camera[]> {
  return useQuery({
    queryKey: storeId ? queryKeys.storeCamera(storeId) : queryKeys.cameras,
    queryFn:  () => fetchCameras(storeId),
    staleTime: 30_000,
  });
}

// ─── Mutation Hooks ───────────────────────────────────────────────────────────

interface AddWatchlistPayload {
  name: string;
  alertLevel: string;
  notes: string;
  faceImage: File;
}

export function useAddWatchlistEntry(): UseMutationResult<
  WatchlistEntry,
  Error,
  AddWatchlistPayload
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ name, alertLevel, notes, faceImage }) => {
      const form = new FormData();
      form.append('name', name);
      form.append('alert_level', alertLevel);
      form.append('notes', notes);
      form.append('face_image', faceImage);
      const res = await api.post<WatchlistEntry>('/watchlist', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return res.data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.watchlist });
    },
  });
}

export function useDeleteWatchlistEntry(): UseMutationResult<void, Error, string> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/watchlist/${id}`);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.watchlist });
    },
  });
}

export function useGenerateReport(): UseMutationResult<Blob, Error, string> {
  return useMutation({
    mutationFn: async (incidentId: string) => {
      const res = await api.get(`/reports/generate/${incidentId}`, {
        responseType: 'blob',
      });
      return res.data as Blob;
    },
  });
}
