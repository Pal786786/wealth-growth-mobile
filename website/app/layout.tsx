import type { Metadata } from 'next';
import { Inter, Playfair_Display } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'], variable: '--font-inter', display: 'swap' });
const playfair = Playfair_Display({ subsets: ['latin'], variable: '--font-playfair', display: 'swap' });

const SITE_BASE_PATH = process.env.SITE_BASE_PATH || '';

export const metadata: Metadata = {
  metadataBase: new URL('https://myfundingbank.com'),
  title: {
    default: 'My Funding Bank — Premium Fintech Super App for Wealth, Forex, Travel & AI',
    template: '%s | My Funding Bank',
  },
  description: 'India’s next-generation fintech super app. Invest in stocks, MFs, gold, FDs. Trade forex. Book travel. Get AI-powered financial advice. Bank-grade security. Built for HNI investors.',
  keywords: ['fintech', 'investment', 'forex trading', 'mutual funds', 'AI financial advisor', 'wealth management', 'India fintech', 'My Funding Bank'],
  authors: [{ name: 'My Funding Bank' }],
  openGraph: {
    type: 'website',
    locale: 'en_IN',
    url: 'https://myfundingbank.com',
    siteName: 'My Funding Bank',
    title: 'My Funding Bank — Premium Fintech Super App',
    description: 'Wealth. Forex. Travel. AI. One luxury fintech platform.',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'My Funding Bank — Premium Fintech Super App',
    description: 'Wealth. Forex. Travel. AI. One luxury fintech platform.',
  },
  robots: { index: true, follow: true },
  icons: {
    icon: `${SITE_BASE_PATH}/favicon.svg`,
  },
};

export const viewport = { themeColor: '#0A1428', width: 'device-width', initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${playfair.variable} dark`}>
      <body className="font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
