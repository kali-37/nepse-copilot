import { fetchJson } from './client';

interface ReliabilityBand {
  lower: number;
  upper: number;
  samples: number;
  mean_probability: number | null;
  observed_rate: number | null;
  interval_low: number | null;
  interval_high: number | null;
}

interface Interval {
  lower: number | null;
  upper: number | null;
}

interface ModelPartition {
  start: string;
  end: string;
  label_end: string;
  samples: number;
  distinct_dates: number;
}

export interface ModelSummary {
  id: string;
  horizon_days: number;
  created_at: string;
  data_as_of: string;
  status: 'candidate' | 'active' | 'rejected';
  gate: { passed: boolean; reasons: string[] };
  advisory_eligible?: boolean;
  advisory_block_reason?: string | null;
  metrics: {
    test_samples: number | null;
    test_dates: number | null;
    brier_score: number | null;
    baseline_brier_score: number | null;
    log_loss: number | null;
    baseline_log_loss: number | null;
    ece: number | null;
    auc: number | null;
    selected_trades: number | null;
    mean_net_return: number | null;
    coverage: number | null;
  };
  boundaries: { train_end: string | null; calibration_end: string | null; test_end: string | null };
  limitations: string[];
  event?: string;
  diagnostics?: {
    reliability: ReliabilityBand[];
    sampling: Record<string, number>;
    raw: { brier: number | null; log_loss: number | null; ece: number | null };
    chart_rule_baseline: { samples: number; mean_net_return_pct: number | null };
    matched_hold_mean_return_pct: number | null;
    calibration_base_rate?: { brier: number | null; log_loss: number | null };
    partitions?: Record<'train' | 'calibration' | 'test', ModelPartition>;
    dataset_fingerprint?: string;
    policy_fingerprint?: string;
    date_block_uncertainty?: {
      method: string;
      block_dates: number;
      full_blocks: number;
      replicates: number;
      brier_improvement_over_train: Interval;
      brier_improvement_over_calibration: Interval;
      selected_net_return_pct: Interval;
      selected_excess_return_pct: Interval;
    } | null;
  };
}

export interface ModelList {
  models: ModelSummary[];
  active: Record<string, string>;
}

export const modelValidationApi = {
  list: () => fetchJson<ModelList>('/research/models'),
  activate: (id: string) => fetchJson<ModelSummary>(`/research/models/${encodeURIComponent(id)}/activate`, { method: 'POST' }),
  disable: (horizonDays: number) => fetchJson<{ disabled: boolean }>(`/research/models/active/${horizonDays}`, { method: 'DELETE' }),
};
