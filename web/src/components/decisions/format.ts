export const money = (n: number | null | undefined) => n == null ? '—' : new Intl.NumberFormat('en-NP', { maximumFractionDigits: 2, minimumFractionDigits: 2 }).format(n);
