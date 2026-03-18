import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'

// Custom theme matching the app — shared between FilesTab and FilesPage
export const codeTheme = {
  ...oneDark,
  'pre[class*="language-"]': {
    ...oneDark['pre[class*="language-"]'],
    background: '#0a0a0a',
    margin: '0',
    padding: '1rem',
    borderRadius: '0',
    fontSize: '0.9em',
  },
  'code[class*="language-"]': {
    ...oneDark['code[class*="language-"]'],
    background: 'transparent',
    fontFamily: "'SF Mono', 'Fira Code', 'JetBrains Mono', monospace",
  },
}
