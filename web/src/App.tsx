import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { RootLayout } from './layouts/RootLayout';
import { DashboardPage } from './pages/Dashboard';
import { SymbolsPage } from './pages/Symbols';
import { SymbolDetailPage } from './pages/SymbolDetail';
import { PortfolioPage } from './pages/Portfolio';
import { BacktestPage } from './pages/Backtest';

export default function App() {
  return (
    <BrowserRouter>
      <RootLayout>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/symbols" element={<SymbolsPage />} />
          <Route path="/symbols/:symbol" element={<SymbolDetailPage />} />
          <Route path="/portfolio" element={<PortfolioPage />} />
          <Route path="/backtest" element={<BacktestPage />} />
        </Routes>
      </RootLayout>
    </BrowserRouter>
  );
}
