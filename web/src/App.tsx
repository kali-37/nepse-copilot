import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { RootLayout } from './layouts/RootLayout';
import { DashboardPage } from './pages/Dashboard';
import { SymbolsPage } from './pages/Symbols';
import { SymbolDetailPage } from './pages/SymbolDetail';
import { PortfolioPage } from './pages/Portfolio';
import { BacktestPage } from './pages/Backtest';
import { RashifalPage } from './pages/Rashifal';
import { MeroSharePage } from './pages/MeroShare';
import { ResearchPage } from './pages/Research';
import { SettingsPage } from './pages/Settings';
import { AuctionPage } from './pages/Auction';

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
          <Route path="/rashifal" element={<RashifalPage />} />
          <Route path="/auction" element={<AuctionPage />} />
          <Route path="/meroshare" element={<MeroSharePage />} />
          <Route path="/research" element={<ResearchPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </RootLayout>
    </BrowserRouter>
  );
}
