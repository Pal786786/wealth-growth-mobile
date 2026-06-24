// Brand constants—single source of truth across the marketing site.
export const BRAND = {
  name: 'My Funding Bank',
  tagline: 'Where Wealth Meets Intelligence',
  domains: {
    site: 'https://myfundingbank.com',
    app: 'https://app.myfundingbank.com',
    admin: 'https://admin.myfundingbank.com',
  },
  // While the official domains aren’t live, point CTAs to the Emergent prod URL
  liveLinks: {
    appPortal: 'https://wealth-growth-mobile.emergent.host',
    adminPortal: 'https://wealth-growth-mobile.emergent.host/api/admin-ui/',
    apkDownload: 'https://wealth-growth-mobile.emergent.host', // Replace with EAS APK URL once live
  },
  contact: {
    email: 'support@myfundingbank.com',
    phone: '+91 80 1234 5678',
    address: 'BKC, Mumbai, Maharashtra 400051, India',
  },
  social: {
    twitter: 'https://twitter.com/myfundingbank',
    linkedin: 'https://linkedin.com/company/myfundingbank',
    instagram: 'https://instagram.com/myfundingbank',
    youtube: 'https://youtube.com/@myfundingbank',
  },
  images: {
    hero: 'https://images.pexels.com/photos/18834566/pexels-photo-18834566.jpeg',
    investments: 'https://images.unsplash.com/photo-1660020619062-70b16c44bf0f',
    forex: 'https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3',
    travel: 'https://images.pexels.com/photos/2612117/pexels-photo-2612117.jpeg',
    ai: 'https://images.pexels.com/photos/37911407/pexels-photo-37911407.jpeg',
    security: 'https://images.unsplash.com/photo-1591439657848-9f4b9ce436b9',
    mobile: 'https://images.unsplash.com/photo-1645226880663-81561dcab0ae',
    testimonial: 'https://images.unsplash.com/photo-1564069114553-7215e1ff1890',
    global: 'https://images.pexels.com/photos/8159115/pexels-photo-8159115.jpeg',
  },
};
