/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  basePath: process.env.SITE_BASE_PATH || '',
  assetPrefix: process.env.SITE_BASE_PATH || undefined,
  images: { unoptimized: true },
  trailingSlash: true,
  reactStrictMode: true,
};

export default nextConfig;
