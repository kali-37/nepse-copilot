interface Props {
  message?: string;
  onRetry?: () => void;
}

export function ErrorState({
  message = 'Something went wrong',
  onRetry,
}: Props) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-text-tertiary">
      <svg
        className="h-10 w-10 text-negative"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
      >
        <circle cx="12" cy="12" r="10" />
        <path d="M12 8v4M12 16h.01" strokeLinecap="round" />
      </svg>
      <span className="text-sm text-text-secondary">{message}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-2 rounded-lg bg-surface-tertiary px-4 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-border"
        >
          Retry
        </button>
      )}
    </div>
  );
}
