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
  Severity,
  HeatmapData,
  Incident,
  QueueStatus,
  WatchlistEntry,
  WatchlistMatch,
} from '../store/useVantagStore';

// ─── Axios Instance ───────────────────────────────────────────────────────────

export const api = axios.create({
  baseURL: '/api',
  timeout: 15_000,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('vantag_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    // 401 Unauthorized → token expired / invalid → force re-login
    if (err.response?.status === 401) {
      localStorage.removeItem('vantag_token');
      localStorage.removeItem('vantag_tenant');
      // Avoid infinite loop if already on login page
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login?reason=session_expired';
      }
    }
    const message =
      (err.response?.data as { detail?: string })?.detail ??
      err.message ??
      'Unknown API error';
    return Promise.reject(new Error(message));
  }
);

// ─── Helpers ──────────────────────────────────────────────────────────────────

// Normalise severity from backend lowercase → frontend uppercase union type
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const normSeverity = (v: any): Severity =>
  ((v ?? 'low') as string).toUpperCase() as Severity;

// ─── Response Normalizers (backend snake_case → frontend camelCase) ───────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const normCamera = (r: any): Camera => ({
  id:         r.camera_id  ?? r.id         ?? '',
  storeId:    r.store_id   ?? r.storeId    ?? '',
  name:       r.name       ?? r.camera_id  ?? '',
  location:   r.location   ?? '',
  streamUrl:  r.rtsp_url   ?? r.streamUrl  ?? '',
  online:     r.status === 'online' || r.online === true,
  fps:        r.fps_target ?? r.fps        ?? 15,
  resolution: r.resolution_width
                ? `${r.resolution_width}x${r.resolution_height}`
                : (r.resolution ?? '1920x1080'),
  zones:      r.zones      ?? [],
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const normStore = (r: any): Store => ({
  id:          r.store_id ?? r.id      ?? '',
  name:        r.name     ?? r.store_id ?? '',
  location:    r.location ?? '',
  address:     r.address  ?? r.location ?? '',
  cameraCount: r.camera_count  ?? r.cameraCount  ?? 0,
  active:      r.status === 'active' || r.active !== false,
  timezone:    r.timezone ?? 'Asia/Kolkata',
  openHours:   r.open_hours
                 ? { open: r.open_hours.split('-')[0] ?? '09:00', close: r.open_hours.split('-')[1] ?? '21:00' }
                 : (r.openHours ?? { open: '09:00', close: '21:00' }),
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const normRisk = (r: any): RiskScore => ({
  storeId:    r.store_id   ?? r.storeId   ?? '',
  score:      r.score      ?? r.risk_score ?? 0,
  severity:   normSeverity(r.severity ?? r.risk_severity),
  factors:    r.factors    ?? [],
  history:    r.history    ?? [],
  computedAt: r.computed_at ?? r.computedAt ?? new Date().toISOString(),
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const normIncident = (r: any): Incident => ({
  id:          r.incident_id ?? r.id           ?? '',
  storeId:     r.store_id    ?? r.storeId      ?? '',
  storeName:   r.store_name  ?? r.storeName    ?? r.store_id ?? '',
  cameraId:    r.camera_id   ?? r.cameraId     ?? '',
  cameraName:  r.camera_name ?? r.cameraName   ?? r.camera_id ?? '',
  type:        r.event_type  ?? r.type         ?? 'system',
  severity:    normSeverity(r.severity),
  riskScore:   r.risk_score  ?? r.riskScore    ?? 0,
  description: r.description ?? '',
  ts:          r.occurred_at ?? r.ts           ?? r.timestamp ?? new Date().toISOString(),
  resolvedAt:  r.resolved_at ?? r.resolvedAt   ?? undefined,
  resolved:    r.acknowledged ?? r.resolved    ?? false,
  reportUrl:   r.report_url  ?? r.reportUrl    ?? undefined,
  snapshotUrl: r.snapshot_url ?? r.snapshotUrl ?? undefined,
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const normWatchlistEntry = (r: any): WatchlistEntry => ({
  id:           r.entry_id   ?? r.id           ?? '',
  name:         r.name       ?? '',
  alertLevel:   normSeverity(r.alert_level ?? r.alertLevel ?? 'medium'),
  faceImageUrl: r.image_url  ?? r.faceImageUrl ?? undefined,
  notes:        r.notes      ?? '',
  addedAt:      r.created_at ?? r.addedAt      ?? new Date().toISOString(),
  lastMatchAt:  r.last_match_at ?? r.lastMatchAt ?? undefined,
  matchCount:   r.match_count ?? r.matchCount   ?? 0,
  active:       r.active      ?? true,
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const normWatchlistMatch = (r: any): WatchlistMatch => ({
  id:           r.match_id    ?? r.id           ?? '',
  entryId:      r.entry_id    ?? r.entryId      ?? '',
  entryName:    r.entry_name  ?? r.entryName    ?? '',
  storeId:      r.store_id    ?? r.storeId      ?? '',
  cameraId:     r.camera_id   ?? r.cameraId     ?? '',
  cameraName:   r.camera_name ?? r.cameraName   ?? r.camera_id ?? '',
  confidence:   r.confidence  ?? 0,
  thumbnailUrl: r.snapshot_url ?? r.thumbnailUrl ?? undefined,
  ts:           r.matched_at  ?? r.ts            ?? new Date().toISOString(),
});

// ─── Query Keys ───────────────────────────────────────────────────────────────

export const queryKeys = {
  stores:           ['stores']                                as const,
  store:            (id: string) => ['stores', id]            as const,
  riskScore:        (id: string) => ['risk', id]              as const,
  heatmap:          (id: string, w: number) => ['heatmap', id, w] as const,
  incidents:        (id: string, p: number) => ['incidents', id, p] as const,
  allIncidents:     (p: number) => ['incidents', 'all', p]    as const,
  queueStatus:      ['queueStatus']                           as const,
  watchlist:        ['watchlist']                             as const,
  watchlistMatches: ['watchlistMatches']                      as const,
  cameras:          ['cameras']                               as const,
  storeCamera:      (storeId: string) => ['cameras', storeId] as const,
};

// ─── API Fetch Functions (with normalization) ─────────────────────────────────

const fetchStores = () =>
  api.get<unknown[]>('/stores').then((r) =>
    (Array.isArray(r.data) ? r.data : [r.data]).map(normStore)
  );

const fetchStore = (id: string) =>
  api.get<unknown>(`/stores/${id}`).then((r) => normStore(r.data));

const fetchRisk = (id: string) =>
  api.get<unknown>(`/stores/${id}/risk`).then((r) => normRisk(r.data));

const fetchHeatmap = (id: string, w: number) =>
  api.get<HeatmapData>(`/stores/${id}/heatmap`, { params: { window: w } }).then((r) => r.data);

// When storeId is provided fetch that store's incidents.
// When storeId is null and storeIds[] is given, query each in parallel then merge.
const fetchIncidents = async (
  storeId: string | null,
  page: number,
  storeIds: string[] = [],
  typeFilter: string = 'all',
): Promise<{ items: Incident[]; total: number; page: number; pages: number }> => {
  const PAGE_SIZE = 25;

  // Build server-side filter params
  const filterParams: Record<string, unknown> = { page, page_size: PAGE_SIZE };
  if (typeFilter && typeFilter !== 'all') filterParams.event_type = typeFilter;

  if (storeId) {
    // Single-store path
    const r = await api.get<unknown>(`/stores/${storeId}/incidents`, {
      params: filterParams,
    });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const raw = r.data as any;
    const arr = raw.incidents ?? raw.items ?? raw.events ?? (Array.isArray(raw) ? raw : []);
    const items: Incident[] = arr.map(normIncident);
    const pg = raw.pagination ?? {};
    return {
      items,
      total: pg.total ?? pg.total_count ?? raw.total ?? items.length,
      page:  pg.page  ?? raw.page       ?? 1,
      pages: pg.pages ?? pg.total_pages ?? raw.pages ?? 1,
    };
  }

  // All-stores path: query every store in parallel and merge
  // Use a larger page_size so all incidents are fetched and server-side type filter works.
  const ids = storeIds.length ? storeIds : [];
  if (ids.length === 0) {
    return { items: [], total: 0, page: 1, pages: 1 };
  }

  const allStoreParams: Record<string, unknown> = { page: 1, page_size: 200 };
  if (typeFilter && typeFilter !== 'all') allStoreParams.event_type = typeFilter;

  const responses = await Promise.allSettled(
    ids.map((sid) =>
      api
        .get<unknown>(`/stores/${sid}/incidents`, { params: allStoreParams })
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        .then((r) => {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const raw = r.data as any;
          const arr = raw.incidents ?? raw.items ?? raw.events ?? (Array.isArray(raw) ? raw : []);
          return (arr as unknown[]).map(normIncident);
        })
    )
  );

  const all: Incident[] = [];
  for (const res of responses) {
    if (res.status === 'fulfilled') all.push(...res.value);
  }

  // Sort newest first
  all.sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime());

  const total = all.length;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const start = (page - 1) * PAGE_SIZE;
  const items = all.slice(start, start + PAGE_SIZE);

  return { items, total, page, pages };
};

const fetchQueueStatus = () =>
  api.get<unknown>('/queue-status').then((r) =>
    Array.isArray(r.data) ? r.data : []
  );

// Fix 1: parse {entries:[...], total:N} envelope
const fetchWatchlist = () =>
  api.get<unknown>('/watchlist').then((r) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const raw = r.data as any;
    const arr = raw.entries ?? (Array.isArray(raw) ? raw : []);
    return (arr as unknown[]).map(normWatchlistEntry);
  });

// Fix 2: normalise match response fields
const fetchWatchlistMatches = () =>
  api.get<unknown>('/watchlist/matches').then((r) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const raw = r.data as any;
    const arr = raw.matches ?? raw.events ?? (Array.isArray(raw) ? raw : []);
    return (arr as unknown[]).map(normWatchlistMatch);
  });

const fetchCameras = (storeId?: string) =>
  api
    .get<unknown[]>('/cameras', storeId ? { params: { store_id: storeId } } : undefined)
    .then((r) => (Array.isArray(r.data) ? r.data : []).map(normCamera));

// ─── Hooks ────────────────────────────────────────────────────────────────────

export function useStores(): UseQueryResult<Store[]> {
  return useQuery({
    queryKey:        queryKeys.stores,
    queryFn:         fetchStores,
    staleTime:       30_000,
    refetchInterval: 60_000,
  });
}

export function useStore(id: string): UseQueryResult<Store> {
  return useQuery({
    queryKey:  queryKeys.store(id),
    queryFn:   () => fetchStore(id),
    enabled:   !!id,
    staleTime: 30_000,
  });
}

export function useRiskScore(storeId: string): UseQueryResult<RiskScore> {
  return useQuery({
    queryKey:        queryKeys.riskScore(storeId),
    queryFn:         () => fetchRisk(storeId),
    enabled:         !!storeId,
    staleTime:       5_000,
    refetchInterval: 10_000,
  });
}

export function useHeatmap(storeId: string, windowMinutes: number): UseQueryResult<HeatmapData> {
  return useQuery({
    queryKey:        queryKeys.heatmap(storeId, windowMinutes),
    queryFn:         () => fetchHeatmap(storeId, windowMinutes),
    enabled:         !!storeId,
    staleTime:       15_000,
    refetchInterval: 30_000,
  });
}

export function useIncidents(
  storeId: string | null,
  page: number,
  storeIds: string[] = [],
  typeFilter: string = 'all',
): UseQueryResult<{ items: Incident[]; total: number; page: number; pages: number }> {
  return useQuery({
    queryKey:        storeId
                       ? [...queryKeys.incidents(storeId, page), typeFilter]
                       : [...queryKeys.allIncidents(page), storeIds.join(','), typeFilter],
    queryFn:         () => fetchIncidents(storeId, page, storeIds, typeFilter),
    staleTime:       10_000,
    refetchInterval: 15_000,
    // Only run when we have data to query
    enabled:         storeId !== null || storeIds.length > 0,
  });
}

export function useQueueStatus(): UseQueryResult<QueueStatus[]> {
  return useQuery({
    queryKey:        queryKeys.queueStatus,
    queryFn:         fetchQueueStatus,
    staleTime:       5_000,
    refetchInterval: 10_000,
  });
}

export function useWatchlist(): UseQueryResult<WatchlistEntry[]> {
  return useQuery({
    queryKey:  queryKeys.watchlist,
    queryFn:   fetchWatchlist,
    staleTime: 15_000,
  });
}

export function useWatchlistMatches(): UseQueryResult<WatchlistMatch[]> {
  return useQuery({
    queryKey:        queryKeys.watchlistMatches,
    queryFn:         fetchWatchlistMatches,
    staleTime:       5_000,
    refetchInterval: 15_000,
  });
}

export function useCameras(storeId?: string): UseQueryResult<Camera[]> {
  return useQuery({
    queryKey:        storeId ? queryKeys.storeCamera(storeId) : queryKeys.cameras,
    queryFn:         () => fetchCameras(storeId),
    staleTime:       30_000,
    refetchInterval: 60_000,
  });
}

// ─── Mutation Hooks ───────────────────────────────────────────────────────────

interface AddWatchlistPayload {
  name: string;
  alertLevel: string;
  notes: string;
  faceImage: File;
}

export function useAddWatchlistEntry(): UseMutationResult<WatchlistEntry, Error, AddWatchlistPayload> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ name, alertLevel, notes, faceImage }) => {
      const form = new FormData();
      form.append('name', name);
      form.append('alert_level', alertLevel.toLowerCase()); // backend expects lowercase
      form.append('notes', notes);
      form.append('face_image', faceImage);
      const res = await api.post<unknown>('/watchlist', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return normWatchlistEntry(res.data);
    },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: queryKeys.watchlist }); },
  });
}

export function useDeleteWatchlistEntry(): UseMutationResult<void, Error, string> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => { await api.delete(`/watchlist/${id}`); },
    onSuccess:  () => { void qc.invalidateQueries({ queryKey: queryKeys.watchlist }); },
  });
}

export function useGenerateReport(): UseMutationResult<Blob, Error, string> {
  return useMutation({
    mutationFn: async (incidentId: string) => {
      const res = await api.get(`/reports/generate/${incidentId}`, { responseType: 'blob' });
      return res.data as Blob;
    },
  });
}
