import Navbar from '@/components/Navbar';
import Hero from '@/components/Hero';
import TickerBar from '@/components/TickerBar';
import Stats from '@/components/Stats';
import About from '@/components/About';
import Investments from '@/components/Investments';
import Forex from '@/components/Forex';
import Travel from '@/components/Travel';
import AIAdvisor from '@/components/AIAdvisor';
import Security from '@/components/Security';
import Calculator from '@/components/Calculator';
import LiveMarket from '@/components/LiveMarket';
import AppDownload from '@/components/AppDownload';
import Vision from '@/components/Vision';
import Testimonials from '@/components/Testimonials';
import FAQ from '@/components/FAQ';
import Contact from '@/components/Contact';
import Footer from '@/components/Footer';

export default function HomePage() {
  return (
    <main className="relative overflow-x-hidden">
      <Navbar />
      <Hero />
      <TickerBar />
      <Stats />
      <About />
      <Investments />
      <Forex />
      <Travel />
      <AIAdvisor />
      <Security />
      <Calculator />
      <LiveMarket />
      <AppDownload />
      <Vision />
      <Testimonials />
      <FAQ />
      <Contact />
      <Footer />
    </main>
  );
}
