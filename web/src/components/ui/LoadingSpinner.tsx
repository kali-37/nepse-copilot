export function LoadingSpinner({ text = 'Loading...' }: { text?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-text-tertiary">
      <svg
        className="h-8 w-8 animate-spin"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      >
        <circle cx="12" cy="12" r="10" strokeDasharray="31.4 31.4" strokeDashoffset="6" />
      </svg>
      <span className="text-sm">{text}</span>
    </div>
  );
}
