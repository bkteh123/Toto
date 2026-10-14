import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, qs } from "./client";
import type {
  BacktestJob,
  BacktestRequest,
  BaoResponse,
  CollectLog,
  DrawPage,
  GameInput,
  Game,
  GenerateResponse,
  ImportResponse,
  Method,
  MissingDraws,
  ScoreParams,
  StatsResponse,
  StoredConflict,
} from "./types";

const enc = encodeURIComponent;

export const useGames = () => useQuery({ queryKey: ["games"], queryFn: () => api.get<Game[]>("/games") });

export const useStats = (code: string | undefined, p: ScoreParams) =>
  useQuery({
    queryKey: ["stats", code, p],
    enabled: !!code,
    queryFn: () =>
      api.get<StatsResponse>(`/games/${enc(code!)}/stats${qs({ period: "all", ...p })}`),
  });

/** Newest first. */
export const useDraws = (code: string | undefined, limit: number) =>
  useQuery({
    queryKey: ["draws", code, limit],
    enabled: !!code,
    queryFn: () => api.get<DrawPage>(`/games/${enc(code!)}/draws${qs({ limit, offset: 0 })}`),
  });

export const useMissing = (code: string | undefined) =>
  useQuery({
    queryKey: ["missing", code],
    enabled: !!code,
    queryFn: () => api.get<MissingDraws>(`/games/${enc(code!)}/draws/missing`),
  });

export const useConflicts = (code: string | undefined) =>
  useQuery({
    queryKey: ["conflicts", code],
    enabled: !!code,
    queryFn: () => api.get<StoredConflict[]>(`/games/${enc(code!)}/conflicts`),
  });

/** Polls while a run is in progress so "Update now" can show its outcome. */
export const useCollectLogs = (code: string | undefined) =>
  useQuery({
    queryKey: ["logs", code],
    enabled: !!code,
    queryFn: () => api.get<CollectLog[]>(`/collect/logs${qs({ game: code, limit: 10 })}`),
    refetchInterval: (q) => (q.state.data?.some((l) => l.status === "running") ? 1500 : false),
  });

/** After any change to a game's data every derived view is stale. */
export function useInvalidateGameData(code: string | undefined) {
  const qc = useQueryClient();
  return () =>
    Promise.all(
      ["stats", "draws", "missing", "conflicts", "logs"].map((k) => qc.invalidateQueries({ queryKey: [k, code] })),
    );
}

export function useImportDraws(code: string | undefined) {
  const invalidate = useInvalidateGameData(code);
  return useMutation({
    mutationFn: (v: { file: File; skipLeading: number }) => {
      const form = new FormData();
      form.append("file", v.file);
      form.append("skip_leading", String(v.skipLeading));
      return api.upload<ImportResponse>(`/games/${enc(code!)}/draws/import`, form);
    },
    onSuccess: invalidate,
  });
}

export function useCollect(code: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.post<{ log_id: number; status: string }>(`/games/${enc(code!)}/collect`, { mode: "auto" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["logs", code] }),
  });
}

export const useGenerate = (code: string | undefined) =>
  useMutation({
    mutationFn: (v: { method: Method; count: number } & ScoreParams) =>
      api.post<GenerateResponse>(`/games/${enc(code!)}/generate`, v),
  });

export const useBao = (code: string | undefined) =>
  useMutation({
    mutationFn: (v: { size: number; window: number; end_draw_no: number | null }) =>
      api.post<BaoResponse>(`/games/${enc(code!)}/bao`, v),
  });

export function useCreateGame() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (g: GameInput) => api.post<Game>("/games", g),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["games"] }),
  });
}

export const useStartBacktest = (code: string | undefined) =>
  useMutation({
    mutationFn: (v: BacktestRequest) =>
      api.post<{ id: number; status: string; seed: number }>(`/games/${enc(code!)}/backtests`, v),
  });

export const useBacktest = (id: number | null) =>
  useQuery({
    queryKey: ["backtest", id],
    enabled: id !== null,
    queryFn: () => api.get<BacktestJob>(`/backtests/${id}`),
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "queued" || s === "running" ? 800 : false;
    },
  });
