import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';

export const metadata = { title: 'Terms & Conditions', description: 'Terms of using My Funding Bank.' };

export default function TermsPage() {
  return (
    <main className="relative">
      <Navbar />
      <section className="pt-32 pb-20 px-6 md:px-10 lg:px-16">
        <div className="max-w-3xl mx-auto">
          <div className="eyebrow mb-3">Legal</div>
          <h1 className="heading-xl mb-3">Terms & Conditions</h1>
          <p className="text-white/50 text-sm mb-10">Last updated: January 2026</p>

          <div className="space-y-8 text-white/75 leading-relaxed">
            <Sec h="1. Acceptance" body={`By accessing or using My Funding Bank services you agree to these Terms. If you do not agree, please discontinue use.`} />
            <Sec h="2. Eligibility" body={`You must be 18+, an Indian resident (or eligible NRI), and complete KYC. We may refuse service or close accounts at our discretion for KYC, AML, fraud or legal reasons.`} />
            <Sec h="3. Account & security" body={`You are responsible for safeguarding credentials. Enable 2FA and biometric login. Notify us immediately of any unauthorised activity. We are not liable for losses arising from your credential compromise unless we are at fault.`} />
            <Sec h="4. Investment services" body={`Investments through MFB are subject to market risks. Stocks, MFs, gold and government securities are held in your name (demat / folio). We are an execution and advisory platform; we do not guarantee returns.`} />
            <Sec id="risk" h="5. Risk disclosure" body={`Markets are volatile. Past performance does not guarantee future results. Forex is a leveraged product carrying risk of substantial loss; on MFB it is currently offered in demo / paper-trading mode only with no real money exposure. AI advice is informational, not a guarantee.`} />
            <Sec h="6. Fees" body={`Brokerage on equity delivery: ₹0. Mutual funds: zero commission (direct plans). FX live (Phase 2): per-trade spread. Travel: partner fees. All fees shown upfront before confirmation. GST as applicable.`} />
            <Sec h="7. Prohibited use" body={`No money-laundering, terror financing, market manipulation, insider trading, scraping, reverse-engineering, or use of our services for illegal purposes. Violation may lead to account closure and reporting to authorities.`} />
            <Sec h="8. Intellectual property" body={`All brand assets, software, content and trademarks belong to MFB or licensors. You may not copy, redistribute or create derivatives without written permission.`} />
            <Sec h="9. Limitation of liability" body={`To the extent permitted by law, MFB’s aggregate liability for any claim shall not exceed fees paid by you in the 12 months preceding the claim. We are not liable for indirect, incidental or consequential damages.`} />
            <Sec h="10. Governing law & jurisdiction" body={`These Terms are governed by Indian law. Exclusive jurisdiction: courts of Mumbai, Maharashtra.`} />
            <Sec id="grievance" h="11. Grievance redressal" body={`Step 1: in-app chat / support@myfundingbank.com. Step 2: escalate to Grievance Officer: grievance@myfundingbank.com (response in 15 days). Step 3: SEBI SCORES / RBI CMS portals for unresolved issues.`} />
            <Sec h="12. Changes" body={`We may update Terms by posting changes here with the “Last updated” date. Continued use after changes signifies acceptance.`} />
          </div>
        </div>
      </section>
      <Footer />
    </main>
  );
}

function Sec({ h, body, id }: { h: string; body: string; id?: string }) {
  return (
    <div id={id} className="glass p-6 scroll-mt-24">
      <h2 className="text-xl font-display font-bold text-gold-400 mb-3">{h}</h2>
      <p>{body}</p>
    </div>
  );
}
