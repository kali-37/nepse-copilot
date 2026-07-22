import { type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  className?: string;
  title?: string;
  actions?: ReactNode;
}

export function Card({ children, className = '', title, actions }: Props) {
  return (
    <div
      className={`rounded-xl border border-border bg-surface p-5 shadow-sm ${className}`}
    >
      {(title || actions) && (
        <div className="mb-4 flex items-center justify-between">
          {title && (
            <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wide">
              {title}
            </h3>
          )}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </div>
  );
}
