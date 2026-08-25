import { useCallback, useEffect, useState } from 'react';
import { Archive, BookMarked, Gauge, ListChecks, Scale } from 'lucide-react';
import { api } from '../api/client';
import type { JournalEntry } from '../api/types';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { DataTable } from '../components/ui/DataTable';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { StatCard } from '../components/ui/StatCard';

const STATUS_VARIANT: Record<JournalEntry['status'], 'default' | 'info' | 'success' | 'warning'> = {
  open: 'info',
  scored: 'warning',
  reviewed: 'success',
  retired: 'default',
};

function money(value: number | null): string {
  if (value === null) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}`;
}

/** One prediction opened for review: write the honest post-mortem, then keep the
 *  one sentence worth remembering. Both are separate CLI subcommands. */
function ReviewPanel({
  entry,
  onDone,
}: {
  entry: JournalEntry;
  onDone: (updated: JournalEntry | null) => void;
}) {
  const [review, setReview] = useState(entry.review ?? '');
  const [lesson, setLesson] = useState(entry.lesson ?? '');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const act = async (name: string, run: () => Promise<JournalEntry | null>) => {
    setBusy(name);
    setError(null);
    try {
      onDone(await run());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card
      title={`${entry.symbol} · ${entry.horizon}`}
      actions={<Badge text={entry.status} variant={STATUS_VARIANT[entry.status]} />}
    >
      <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-3">
        <div className="flex justify-between gap-2">
          <dt className="text-text-tertiary">made on</dt>
          <dd className="text-text-primary">{entry.made_on}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-text-tertiary">deadline</dt>
          <dd className="text-text-primary">{entry.deadline}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-text-tertiary">action</dt>
          <dd className="text-text-primary">{entry.action}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-text-tertiary">expected</dt>
          <dd className="text-text-primary">{money(entry.expected_net_pnl)}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-text-tertiary">realized</dt>
          <dd
            className={
              entry.realized_net_pnl === null
                ? 'text-text-primary'
                : entry.realized_net_pnl >= 0
                  ? 'text-positive'
                  : 'text-negative'
            }
          >
            {money(entry.realized_net_pnl)}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-text-tertiary">outcome</dt>
          <dd className="text-text-primary">{entry.outcome ?? 'not scored'}</dd>
        </div>
      </dl>

      <p className="mt-3 text-xs text-text-tertiary">
        Said {(entry.confidence * 100).toFixed(0)}% confident ({entry.confidence_band}) because{' '}
        {entry.confidence_basis}.
      </p>

      <div className="mt-4 space-y-3">
        <label className="block text-sm">
          <span className="text-text-secondary">
            What actually happened, and what you would do differently
          </span>
          <textarea
            value={review}
            onChange={(e) => setReview(e.target.value)}
            rows={3}
            className="mt-1 w-full rounded border border-border bg-surface-secondary px-3 py-2 text-sm text-text-primary"
            placeholder="Entry was fine, the stop was too tight for this symbol's range."
          />
        </label>
        <label className="block text-sm">
          <span className="text-text-secondary">The one sentence worth keeping</span>
          <input
            value={lesson}
            onChange={(e) => setLesson(e.target.value)}
            className="mt-1 h-10 w-full rounded border border-border bg-surface-secondary px-3 text-sm text-text-primary"
            placeholder="Size stops off ATR, not a flat percent."
          />
        </label>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          disabled={busy !== null || !review.trim()}
          onClick={() =>
            void act('review', () => api.journalReview(entry.prediction_id, review.trim()))
          }
          className="inline-flex h-9 items-center gap-2 rounded bg-nepse-600 px-4 text-sm font-semibold text-white hover:bg-nepse-700 disabled:opacity-50"
        >
          <BookMarked className="h-4 w-4" />
          {busy === 'review' ? 'Saving...' : 'Save review'}
        </button>
        <button
          disabled={busy !== null || !lesson.trim()}
          onClick={() =>
            void act('distill', async () => {
              await api.journalDistill(entry.prediction_id, lesson.trim());
              return null;
            })
          }
          className="inline-flex h-9 items-center gap-2 rounded border border-border px-4 text-sm font-medium text-text-secondary hover:bg-surface-tertiary disabled:opacity-50"
        >
          <Scale className="h-4 w-4" />
          {busy === 'distill' ? 'Saving...' : 'Keep as lesson'}
        </button>
        <button
          disabled={busy !== null}
          onClick={() => void act('retire', () => api.journalRetire(entry.prediction_id))}
          className="inline-flex h-9 items-center gap-2 rounded border border-border px-4 text-sm font-medium text-text-secondary hover:bg-surface-tertiary disabled:opacity-50"
        >
          <Archive className="h-4 w-4" />
          {busy === 'retire' ? 'Retiring...' : 'Retire'}
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-negative">{error}</p>}
    </Card>
  );
}

export function JournalPage() {
  const [history, setHistory] = useState<JournalEntry[]>([]);
  const [queue, setQueue] = useState<JournalEntry[]>([]);
  const [calibration, setCalibration] = useState<Array<Record<string, unknown>>>([]);
  const [open, setOpen] = useState<JournalEntry | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [scoring, setScoring] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (status: string) => {
    const [nextHistory, nextQueue, nextCalibration] = await Promise.all([
      api.journalHistory({ status: status || undefined, limit: 200 }),
      api.journalReviewQueue(),
      api.journalCalibration(),
    ]);
    setHistory(nextHistory);
    setQueue(nextQueue);
    setCalibration(nextCalibration);
  }, []);

  useEffect(() => {
    load(statusFilter)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [load, statusFilter]);

  const score = async () => {
    setScoring(true);
    setNotice(null);
    setError(null);
    try {
      const scored = await api.journalScore(50);
      setNotice(
        scored.length === 0
          ? 'Nothing was due for scoring — every open prediction is still inside its horizon.'
          : `Scored ${scored.length} prediction${scored.length === 1 ? '' : 's'} against stored prices.`
      );
      await load(statusFilter);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setScoring(false);
    }
  };

  if (loading) return <LoadingSpinner text="Loading the journal..." />;
  if (error && history.length === 0) return <ErrorState message={error} />;

  const hits = history.filter((row) => row.hit === 1).length;
  const judged = history.filter((row) => row.hit !== null).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Journal</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Every prediction the advisor made, scored against what actually happened. This is the
          honest scoreboard &mdash; it is where confidence numbers earn or lose their credibility.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Predictions" value={history.length} icon={<BookMarked className="h-4 w-4" />} />
        <StatCard label="Awaiting review" value={queue.length} icon={<ListChecks className="h-4 w-4" />} />
        <StatCard
          label="Hit rate"
          value={judged === 0 ? '—' : `${((hits / judged) * 100).toFixed(0)}%`}
          change={judged === 0 ? null : `${hits}/${judged} judged`}
          changeType="neutral"
          icon={<Gauge className="h-4 w-4" />}
        />
        <StatCard label="Calibration buckets" value={calibration.length} icon={<Scale className="h-4 w-4" />} />
      </div>

      <Card
        title="Score what is due"
        actions={
          <button
            onClick={() => void score()}
            disabled={scoring}
            className="inline-flex h-9 items-center gap-2 rounded bg-nepse-600 px-4 text-sm font-semibold text-white hover:bg-nepse-700 disabled:opacity-50"
          >
            <Gauge className="h-4 w-4" />
            {scoring ? 'Scoring...' : 'Score now'}
          </button>
        }
      >
        <p className="text-sm text-text-secondary">
          Scoring compares each past-deadline prediction against the prices already in the database.
          It reads only stored data, so it is safe to run any time.
        </p>
        {notice && <p className="mt-2 text-sm text-text-primary">{notice}</p>}
        {error && <p className="mt-2 text-sm text-negative">{error}</p>}
      </Card>

      {open && (
        <ReviewPanel
          entry={open}
          onDone={(updated) => {
            setOpen(updated);
            void load(statusFilter).catch(() => undefined);
          }}
        />
      )}

      {calibration.length > 0 && (
        <Card title="Calibration">
          <p className="mb-3 text-sm text-text-secondary">
            Claimed confidence against realized hit rate. A well-calibrated band has both columns
            close together; a gap means the confidence number is lying to you.
          </p>
          <DataTable
            columns={Object.keys(calibration[0]).map((key) => ({
              key,
              label: key.replace(/_/g, ' '),
              render: (row: Record<string, unknown>) => {
                const value = row[key];
                if (value === null || value === undefined) return '—';
                if (typeof value === 'number') return Number(value.toFixed(3)).toString();
                return String(value);
              },
            }))}
            data={calibration}
            label="Calibration"
          />
        </Card>
      )}

      <Card
        title="All predictions"
        actions={
          <select
            aria-label="Status filter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="h-9 rounded border border-border bg-surface px-2 text-sm text-text-primary"
          >
            <option value="">Every status</option>
            <option value="open">Open</option>
            <option value="scored">Scored</option>
            <option value="reviewed">Reviewed</option>
            <option value="retired">Retired</option>
          </select>
        }
      >
        <DataTable
          columns={[
            { key: 'symbol', label: 'Symbol', sortable: true },
            { key: 'made_on', label: 'Made on' },
            { key: 'horizon', label: 'Horizon' },
            { key: 'deadline', label: 'Deadline' },
            { key: 'action', label: 'Action' },
            {
              key: 'confidence',
              label: 'Confidence',
              render: (row) => `${(row.confidence * 100).toFixed(0)}% ${row.confidence_band}`,
            },
            {
              key: 'realized_net_pnl',
              label: 'Realized',
              render: (row) => (
                <span
                  className={
                    row.realized_net_pnl === null
                      ? 'text-text-tertiary'
                      : row.realized_net_pnl >= 0
                        ? 'text-positive'
                        : 'text-negative'
                  }
                >
                  {money(row.realized_net_pnl)}
                </span>
              ),
            },
            {
              key: 'status',
              label: 'Status',
              render: (row) => <Badge text={row.status} variant={STATUS_VARIANT[row.status]} />,
            },
          ]}
          data={history}
          onRowClick={(row) => setOpen(row)}
          label="All predictions"
        />
        <p className="mt-3 border-t border-border pt-3 text-xs text-text-tertiary">
          Pick a row to review it, distill a lesson from it, or retire it.
        </p>
      </Card>
    </div>
  );
}
