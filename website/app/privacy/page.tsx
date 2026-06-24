import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';

export const metadata = { title: 'Privacy Policy', description: 'How My Funding Bank handles your data.' };

export default function PrivacyPage() {
  return (
    <main className="relative">
      <Navbar />
      <section className="pt-32 pb-20 px-6 md:px-10 lg:px-16">
        <div className="max-w-3xl mx-auto">
          <div className="eyebrow mb-3">Legal</div>
          <h1 className="heading-xl mb-3">Privacy Policy</h1>
          <p className="text-white/50 text-sm mb-10">Last updated: January 2026 • Effective: January 2026</p>

          <div className="prose prose-invert max-w-none space-y-8 text-white/75 leading-relaxed">
            <Sec h="1. Who we are" body={`My Funding Bank Private Limited (“MFB”, “we”, “us”) is a fintech platform incorporated in India offering investment, forex (demo), travel and AI-advisory services through the apps and websites at myfundingbank.com, app.myfundingbank.com and admin.myfundingbank.com.`} />
            <Sec h="2. Data we collect" body={`We collect (a) identity data — name, mobile, email, PAN, Aadhaar (for KYC); (b) financial data — bank account, transactions, holdings; (c) device & usage data — IP, device ID, OS, app activity; (d) optional data — photos for KYC, profile preferences. We do not collect data about your contacts, calls, SMS or location without explicit, contextual consent.`} />
            <Sec h="3. How we use your data" body={`To operate accounts, process transactions, meet KYC/AML obligations, personalise your experience (e.g. AI advisor), prevent fraud, send service notifications, comply with regulators (RBI, SEBI). We never sell data to advertisers.`} />
            <Sec h="4. Sharing & disclosure" body={`Only with: (a) regulated financial institutions for executing trades/transfers; (b) KYC/AML providers; (c) cloud infrastructure providers under strict DPAs; (d) regulators when legally compelled. All third parties are contractually bound by data-protection terms.`} />
            <Sec h="5. Security" body={`AES-256 encryption at rest, TLS 1.3 in transit, AWS/India region hosting, ISO 27001 controls, annual penetration testing, 24x7 fraud monitoring. PII is masked in internal dashboards.`} />
            <Sec h="6. Your rights (DPDP Act 2023)" body={`Access, correct, port or delete your personal data anytime from Settings → Privacy or by emailing privacy@myfundingbank.com. We will action requests within 30 days. You may also withdraw consent for non-essential processing.`} />
            <Sec h="7. Cookies & tracking" body={`We use first-party cookies for authentication and analytics. No third-party advertising cookies. You can clear cookies in your browser at any time.`} />
            <Sec h="8. Children" body={`Our services are not directed to anyone under 18. We do not knowingly collect minor data.`} />
            <Sec h="9. Changes" body={`We will notify material changes via app banner and email at least 14 days in advance.`} />
            <Sec h="10. Contact" body={`Grievance Officer: privacy@myfundingbank.com • +91 80 1234 5678 • BKC, Mumbai 400051. Response SLA: 15 days.`} />
          </div>
        </div>
      </section>
      <Footer />
    </main>
  );
}

function Sec({ h, body }: { h: string; body: string }) {
  return (
    <div className="glass p-6">
      <h2 className="text-xl font-display font-bold text-gold-400 mb-3">{h}</h2>
      <p>{body}</p>
    </div>
  );
}
