import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { Job, JobKind } from '../api/types';

/** How often a running job is re-read. Fast enough to feel live, slow enough
 *  that a multi-minute run does not make thousands of requests. */
const POLL_MS = 1200;

interface UseJob {
  job: Job | null;
  error: string | null;
  /** True between pressing Run and the first response. */
  starting: boolean;
  start: (kind: JobKind, params?: Record<string, unknown>) => Promise<void>;
  cancel: () => Promise<void>;
  /** Re-attach to a job that was already running when the page opened. */
  attach: (id: string) => void;
  clear: () => void;
}

/**
 * Drives one background job: start it, poll while it runs, stop polling once
 * it reaches a terminal state.
 *
 * Polling rather than SSE/WebSocket because the whole backend is synchronous
 * FastAPI handlers over one SQLite file, and a 1.2s GET of a small JSON blob on
 * localhost costs nothing. It also survives a page reload for free — the job
 * lives in the server's registry, so `attach` picks it back up.
 */
export function useJob(): UseJob {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Guards against a poll that resolves after the component unmounted or the
  // operator moved on to a different job.
  const watching = useRef<string | null>(null);

  const stopTimer = useCallback(() => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  const poll = useCallback(
    async (id: string) => {
      try {
        const next = await api.job(id);
        if (watching.current !== id) return;
        setJob(next);
        if (next.status === 'queued' || next.status === 'running') {
          timer.current = setTimeout(() => void poll(id), POLL_MS);
        } else {
          watching.current = null;
        }
      } catch (e) {
        if (watching.current !== id) return;
        // A failed poll is not a failed job — the job keeps running on the
        // server. Surface it and stop polling rather than hammering a broken
        // connection; the operator can reload to re-attach.
        setError(e instanceof Error ? e.message : String(e));
        watching.current = null;
      }
    },
    []
  );

  const attach = useCallback(
    (id: string) => {
      stopTimer();
      watching.current = id;
      setError(null);
      void poll(id);
    },
    [poll, stopTimer]
  );

  const start = useCallback(
    async (kind: JobKind, params: Record<string, unknown> = {}) => {
      stopTimer();
      setStarting(true);
      setError(null);
      try {
        const started = await api.submitJob(kind, params);
        setJob(started);
        watching.current = started.id;
        timer.current = setTimeout(() => void poll(started.id), POLL_MS);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setStarting(false);
      }
    },
    [poll, stopTimer]
  );

  const cancel = useCallback(async () => {
    if (!job) return;
    try {
      setJob(await api.cancelJob(job.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [job]);

  const clear = useCallback(() => {
    stopTimer();
    watching.current = null;
    setJob(null);
    setError(null);
  }, [stopTimer]);

  useEffect(
    () => () => {
      // Unmount: drop the timer and disown the job so a late response is ignored.
      if (timer.current !== null) clearTimeout(timer.current);
      watching.current = null;
    },
    []
  );

  return { job, error, starting, start, cancel, attach, clear };
}
