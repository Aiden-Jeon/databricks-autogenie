/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  output: 'export',  // Static HTML export for Databricks Apps

  // Disable image optimization for static export
  images: {
    unoptimized: true,
  },

  // Trailing slashes for better static hosting
  trailingSlash: true,
}

module.exports = nextConfig
