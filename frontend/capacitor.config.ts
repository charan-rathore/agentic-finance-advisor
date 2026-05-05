import type { CapacitorConfig } from '@capacitor/cli'

const DEPLOYED_URL = process.env.FINSIGHT_API_URL || ''

const config: CapacitorConfig = {
  appId: 'com.finsight.app',
  appName: 'Finsight',
  webDir: 'dist',
  ...(DEPLOYED_URL
    ? { server: { url: DEPLOYED_URL, cleartext: false } }
    : { server: { url: 'http://10.0.2.2:8000', cleartext: true } }
  ),
  plugins: {
    SplashScreen: {
      launchShowDuration: 2000,
      backgroundColor: '#0284c7',
      showSpinner: false,
    },
  },
}

export default config
