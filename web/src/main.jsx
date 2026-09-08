import React from 'react'
import { createRoot } from 'react-dom/client'

// Newsreader is the reading voice: headings and scripture. It has no Greek
// subset, so Source Serif 4 stands behind it for the interlinear -- same
// weight and colour, just there for the alphabet Newsreader doesn't cover.
import '@fontsource-variable/newsreader'
import '@fontsource-variable/source-serif-4'
// Pointed Hebrew falls back to whatever the device has unless something with
// niqqud is bundled alongside it.
import '@fontsource/noto-serif-hebrew/hebrew-400.css'
import './styles.css'

import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
