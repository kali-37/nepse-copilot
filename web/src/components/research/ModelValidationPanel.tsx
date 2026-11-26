import { useCallback, useEffect, useRef, useState } from 'react';
import { Play, RefreshCw } from 'lucide-react';
import { api } from '../../api/client';
import { modelValidationApi, type ModelList, type ModelSummary } from '../../api/modelValidation';
import { useJob } from '../../hooks/useJob';
import { ModelEvidence } from './ModelEvidence';

const buttonClass = 'inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-border px-4 py-2 text-sm font-medium text-text-primary hover:bg-surface-secondary disabled:cursor-not-allowed disabled:opacity-50';
const horizons = [{ days: 3, label: 'daily' }, { days: 22, label: 'monthly' }] as const;

export function ModelValidationPanel() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<ModelList | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const revision = useRef(0);
  const completedJob = useRef<string | null>(null);
  const { job, error: jobError, starting, start, cancel, attach, clear } = useJob();

  const invalidateReads = useCallback(() => { ++revision.current; }, []);
  const reload = useCallback(async (checkJobs = false) => {
    const requestRevision = ++revision.current;
    setLoading(true);
    setError(null);
    const [versions, jobs] = await Promise.allSettled([
      modelValidationApi.list(),
      checkJobs ? api.jobs() : null,
    ]);
    if (requestRevision !== revision.current) return;
    if (versions.status === 'fulfilled') setData(versions.value);
    else setError(String(versions.reason));
    if (jobs.status === 'fulfilled' && jobs.value) {
      if (jobs.value.running) attach(jobs.value.running);
      else clear();
    } else if (jobs.status === 'rejected' && versions.status === 'fulfilled') {
      setError(String(jobs.reason));
    }
    setLoading(false);
  }, [attach, clear]);

  useEffect(() => {
    if (!open) return;
    void reload(true);
    return invalidateReads;
  }, [open, reload, invalidateReads]);

  useEffect(() => {
    if (job?.kind === 'train-model' && job.status === 'done' && completedJob.current !== job.id) {
      completedJob.current = job.id;
      void reload();
    }
  }, [job, reload]);

  const jobRunning = job?.status === 'queued' || job?.status === 'running';
  const busy = loading || actionBusy || starting || jobRunning;
  const modelJob = job?.kind === 'train-model';
  const stage = job?.stages.find(item => item.status === 'running');
  const changeAdvisory = async (model: ModelSummary, activate: boolean) => {
    invalidateReads();
    setActionBusy(true);
    setLoading(false);
    setError(null);
    try {
      if (activate) {
        const confirmed = await modelValidationApi.activate(model.id);
        setData(current => current && {
          models: current.models.map(item => {
            if (item.id === confirmed.id) return confirmed;
            if (item.horizon_days !== confirmed.horizon_days || item.status !== 'active') return item;
            return { ...item, status: item.gate.passed ? 'candidate' : 'rejected' };
          }),
          active: { ...current.active, [String(confirmed.horizon_days)]: confirmed.id },
        });
      } else {
        await modelValidationApi.disable(model.horizon_days);
        setData(current => {
          if (!current) return current;
          const active = { ...current.active };
          delete active[String(model.horizon_days)];
          return {
            active,
            models: current.models.map(item => item.id === model.id
              ? { ...item, status: item.gate.passed ? 'candidate' : 'rejected' }
              : item),
          };
        });
      }
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setActionBusy(false);
    }
  };

  return (
    <details className="rounded-xl border border-border bg-surface p-5" onToggle={event => setOpen(event.currentTarget.open)}>
      <summary className="cursor-pointer text-base font-semibold text-text-primary">Trained model validation</summary>
      {open && (
        <div className="mt-4 space-y-4">
          <p className="text-sm leading-6 text-text-secondary">
            Evaluate a model on local price history using separate dates for training, calibration and final testing. Its probability estimates a net-positive modeled trade over the given horizon, conditional on the saved entry zone filling.
          </p>
          <div className="flex flex-wrap gap-2">
            {horizons.map(({ days, label }) => (
              <button className={buttonClass} disabled={busy} key={days} onClick={() => void start('train-model', { horizon_days: days, max_symbols: 150, max_sessions: 1000 })}>
                <Play size={16} aria-hidden="true" />
                Evaluate {label} model
              </button>
            ))}
            <button className={buttonClass} disabled={loading || actionBusy || starting} onClick={() => void reload(true)}>
              <RefreshCw size={16} aria-hidden="true" /> Refresh model list
            </button>
          </div>
          <p className="text-xs text-text-secondary">Enable a passing model to display its estimate alongside the evidence score on eligible buy ideas.</p>
          {(error || jobError || job?.error) && (
            <p className="rounded-lg border border-negative p-3 text-sm text-negative" role="alert">{error || jobError || job?.error}</p>
          )}
          {loading && <p className="text-sm text-text-secondary" role="status">Reading saved model versions…</p>}
          {(jobRunning || starting) && (
            <div className="rounded-lg bg-surface-secondary p-3 text-sm">
              <div role="status">
                <strong>{modelJob || starting ? stage?.label ?? 'Starting model evaluation' : 'A data job is running'}</strong>
                {stage?.detail && <p className="mt-1 text-text-secondary">{stage.detail}</p>}
                {stage && stage.total > 0 && <p className="mt-1 text-text-secondary">{stage.current} / {stage.total}</p>}
              </div>
              {modelJob && (
                <button className={`${buttonClass} mt-2`} disabled={job.cancel_requested} onClick={() => void cancel()}>
                  {job.cancel_requested ? 'Cancellation requested' : 'Cancel evaluation'}
                </button>
              )}
            </div>
          )}
          {modelJob && job.status === 'done' && (
            <p className="text-sm text-text-secondary" role="status">Evaluation complete. Review the held-out metrics and validation findings below.</p>
          )}
          {modelJob && job.status === 'cancelled' && (
            <p className="text-sm text-text-secondary" role="status">Model evaluation cancelled.</p>
          )}
          {data?.models.length === 0 && !loading && (
            <p className="rounded-lg bg-surface-secondary p-4 text-sm text-text-secondary">No trained versions yet. Evaluate a horizon to see held-out results.</p>
          )}
          {data?.models.map(model => (
            <ModelEvidence
              key={model.id}
              model={model}
              busy={busy}
              onActivate={() => void changeAdvisory(model, true)}
              onDisable={() => void changeAdvisory(model, false)}
              buttonClass={buttonClass}
            />
          ))}
        </div>
      )}
    </details>
  );
}
