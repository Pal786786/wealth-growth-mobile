'use client';
import Reveal from './Reveal';
import { useEffect, useRef } from 'react';

export default function LiveMarket() {
  const widgetRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!widgetRef.current || widgetRef.current.dataset.loaded === '1') return;
    const s = document.createElement('script');
    s.src = 'https://s3.tradingview.com/external-embedding/embed-widget-market-overview.js';
    s.async = true;
    s.innerHTML = JSON.stringify({
      colorTheme: 'dark',
      dateRange: '12M',
      showChart: true,
      locale: 'en',
      width: '100%',
      height: 540,
      isTransparent: true,
      showSymbolLogo: true,
      showFloatingTooltip: true,
      tabs: [
        { title: 'Indices', symbols: [
          { s: 'BSE:SENSEX', d: 'SENSEX' }, { s: 'NSE:NIFTY', d: 'NIFTY 50' },
          { s: 'NSE:BANKNIFTY', d: 'BANK NIFTY' }, { s: 'SP:SPX', d: 'S&P 500' },
          { s: 'NASDAQ:NDX', d: 'NASDAQ 100' },
        ], originalTitle: 'Indices' },
        { title: 'Forex', symbols: [
          { s: 'FX:EURUSD' }, { s: 'FX:GBPUSD' }, { s: 'FX:USDJPY' },
          { s: 'FX_IDC:USDINR' }, { s: 'FX:AUDUSD' },
        ], originalTitle: 'Forex' },
        { title: 'Crypto', symbols: [
          { s: 'COINBASE:BTCUSD' }, { s: 'COINBASE:ETHUSD' },
          { s: 'COINBASE:SOLUSD' }, { s: 'BINANCE:BNBUSDT' },
        ], originalTitle: 'Crypto' },
        { title: 'Commodities', symbols: [
          { s: 'TVC:GOLD' }, { s: 'TVC:SILVER' },
          { s: 'TVC:USOIL' }, { s: 'TVC:NATURALGAS' },
        ], originalTitle: 'Commodities' },
      ],
    });
    widgetRef.current.appendChild(s);
    widgetRef.current.dataset.loaded = '1';
  }, []);

  return (
    <section id="markets" className="relative section-pad">
      <div className="max-w-7xl mx-auto">
        <Reveal>
          <div className="text-center mb-10">
            <div className="eyebrow justify-center mb-3">Live Markets</div>
            <h2 className="heading-lg">The world’s markets, <span className="gold-text">at a glance.</span></h2>
          </div>
        </Reveal>
        <Reveal delay={0.1}>
          <div className="glass p-3 md:p-5">
            <div ref={widgetRef} className="tradingview-widget-container rounded-xl overflow-hidden min-h-[540px]" />
            <p className="text-[10px] text-white/30 text-center mt-2">Powered by TradingView</p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
