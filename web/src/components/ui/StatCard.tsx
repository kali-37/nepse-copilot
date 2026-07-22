interface Props {
  label: string;
  value: string | number;
  change?: string | number | null;
  changeType?: 'positive' | 'negative' | 'neutral';
  icon?: React.ReactNode;
}

export function StatCard({ label, value, change, changeType, icon }: Props) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-text-secondary uppercase tracking-wide">
          {label}
        </span>
        {icon && <span className="text-text-tertiary">{icon}</span>}
      </div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="text-2xl font-bold text-text-primary">{value}</span>
        {change !== undefined && change !== null && (
          <span
            className={`text-sm font-medium ${
              changeType === 'positive'
                ? 'text-positive'
                : changeType === 'negative'
                  ? 'text-negative'
                  : 'text-text-tertiary'
            }`}
          >
            {typeof change === 'number' ? `${change > 0 ? '+' : ''}${change}` : change}
          </span>
        )}
      </div>
    </div>
  );
}
