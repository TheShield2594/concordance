import React from 'react'
import { createRoot } from 'react-dom/client'

import '@fontsource-variable/fraunces'
import '@fontsource-variable/source-serif-4'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
// Source Serif 4 ships the Greek subset, so the New Testament is already
// covered; pointed Hebrew is not, and falls back to whatever the device has
// unless something with niqqud is bundled alongside it.
import '@fontsource/noto-serif-hebrew/hebrew-400.css'
import './styles.css'

import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
