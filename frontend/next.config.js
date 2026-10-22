/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: { proxyTimeout: 360000 },
  rewrites: async () => [
    { source: '/health', destination: 'http://127.0.0.1:8000/health' },
    { source: '/api/:path*', destination: 'http://127.0.0.1:8000/api/:path*' },
    { source: '/storage/:path*', destination: 'http://127.0.0.1:8000/storage/:path*' },
    { source: '/videos-browse', destination: 'http://127.0.0.1:8000/videos-browse' },
  ],
};
module.exports = nextConfig;
