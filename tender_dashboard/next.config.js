/** @type {import('next').NextConfig} */
const nextConfig = {
  // Allow API calls to localhost:8000 (our FastAPI backend)
  // In production, replace with your actual backend URL
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/:path*',
      },
    ]
  },
}

module.exports = nextConfig
