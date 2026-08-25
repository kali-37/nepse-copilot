import { useEffect, useRef } from 'react';
import { AlertTriangle, Ban, CheckCircle2, CircleSlash, Loader2, Minus } from 'lucide-react';
import type { Job, JobStage, JobStageStatus } from '../api/types';
import { Badge } from './ui/Badge';
import { Card } from './ui/Card';

const STAGE_ICON: Record<JobStageStatus, React.ReactNode> = {
  pending: <Minus className="h-4 w-4 text-text-tertiary" />,
  running: <Loader2 className="h-4 w-4 animate-spin text-nepse-600" />,
  ok: <CheckCircle2 className="h-4 w-4 text-positive" />,
  failed: <AlertTriangle className="h-4 w-4 text-negative" />,
  skipped: <CircleSlash className="h-4 w-4 text-text-tertiary" />,
};

const JOB_BADGE: Record<Job['status'], 'default' | 'info' | 'success' | 'danger' | 'warning'> = {
  queued: 'default',
  running: 'info',
  done: 'success',
  failed: 'danger',
  cancelled: 'warning',
};

function StageRow({ stage }: { stage: JobStage }) {
  const counted = stage.total > 0;
  const pct = counted ? Math.min(100, Math.round((stage.current / stage.total) * 100)) : 0;
  return (
    <li className="flex items-start gap-3 py-2">
      <span className="mt-0.5">{STAGE_ICON[stage.status]}</span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-sm font-medium text-text-primary">{stage.label}</span>
          {counted && (
            <span className="text-xs tabular-nums text-text-tertiary">
              {stage.current}/{stage.total}
            </span>
          )}
        </span>
        {stage.detail && (
          <span className="mt-0.5 block truncate text-xs text-text-secondary">{stage.detail}</span>
        )}
        {stage.status === 'running' && counted && (
          <span
            className="mt-1.5 block h-1 w-full overflow-hidden rounded-full bg-surface-tertiary"
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`${stage.label} progress`}
          >
            <span
              className="block h-full rounded-full bg-nepse-600 transition-all duration-300"
              style={{ width: `${pct}%` }}
            />
          </span>
        )}
      </span>
    </li>
  );
}

interface Props {
  job: Job;
  onCancel?: () => void;
  /** Rendered under the log once the job succeeds — the in-page result view. */
  children?: React.ReactNode;
}

/**
 * Live view of one background job: stage list, per-stage progress, and the tail
 * of the log. This is what replaces the CLI's spinner.
 */
export function JobConsole({ job, onCancel, children }: Props) {
  const logRef = useRef<HTMLPreElement>(null);
  const lines = job.log ?? [];

  // Follow the tail the way a terminal does.
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines.length]);

  const active = job.status === 'running' || job.status === 'queued';

  return (
    <Card
      title={`Job ${job.kind}`}
      actions={
        <div className="flex items-center gap-2">
          <Badge text={job.status} variant={JOB_BADGE[job.status]} />
          {active && onCancel && (
            <button
              onClick={onCancel}
              disabled={job.cancel_requested}
              className="inline-flex items-center gap-1.5 rounded border border-border px-2.5 py-1 text-xs font-medium text-text-secondary hover:bg-surface-tertiary disabled:opacity-50"
            >
              <Ban className="h-3.5 w-3.5" />
              {job.cancel_requested ? 'Stopping...' : 'Cancel'}
            </button>
          )}
        </div>
      }
    >
      <ul className="divide-y divide-border">
        {job.stages.map((stage) => (
          <StageRow key={stage.name} stage={stage} />
        ))}
      </ul>

      {job.error && (
        <p className="mt-3 rounded border border-negative/30 bg-negative/5 px-3 py-2 text-sm text-negative">
          {job.error}
        </p>
      )}

      {lines.length > 0 && (
        <pre
          ref={logRef}
          aria-label="Job log"
          className="mt-3 max-h-56 overflow-y-auto rounded bg-surface-tertiary p-3 text-xs leading-relaxed text-text-secondary"
        >
          {lines.join('\n')}
        </pre>
      )}

      {job.status === 'done' && children}
    </Card>
  );
}
